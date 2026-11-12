# SQL 安全防护 设计文档

日期：2026-11-12
状态：待审批

## 背景与意图

data-agent 是 Text-to-SQL Agent，LLM 生成的 SQL 经 `validate_sql`(EXPLAIN) 校验后由
`DWMySQLRepository.run()` 直接在数仓执行，当前没有任何安全限制。需要增加四层防护：
只读限制、黑名单关键字、查询超时、结果行数限制。

## 已确认的决策

| 决策点 | 结论 |
|--------|------|
| 解析方式 | sqlglot AST（新增依赖）+ 关键字黑名单双层防御 |
| 违规处理 | 直接抛异常终止本次查询，不走 correct_sql 修复 |
| 默认值 | 超时 30 秒，最多返回 1000 行，均可配置 |

## 方案选择

- **方案 A（选用）：仓储层集中检查。** 所有安全检查封装为独立模块，在
  `DWMySQLRepository.validate()` 和 `run()` 入口处强制执行。任何调用路径
  （包括 `correct_sql → run_sql` 这条跳过 validate_sql 节点的路径）都无法绕过。
- 方案 B（否决）：只在 `validate_sql` 图节点检查。correct_sql 修正后的 SQL
  直接进 run_sql，存在绕过漏洞。
- 方案 C（否决）：在 run_sql 节点检查。validate 的 EXPLAIN 路径覆盖不到，
  且安全检查散落在节点层，与"数据库访问统一封装在仓储层"的现有架构不符。

## 设计

### 新模块 `app/core/sql_safety.py`

- `SqlSafetyError(Exception)`：安全违规专用异常，携带中文可读信息。
- `SqlSafetyChecker`，读取配置，提供：
  - `check(sql)`：
    1. sqlglot 以 mysql 方言解析：必须恰好 1 条语句，且语句类型必须是
       SELECT（含 WITH...SELECT、UNION）；其余一律抛 `SqlSafetyError`。
       AST 解析天然覆盖注释伪装、多语句注入（`;`）等绕过手段。
    2. 黑名单关键字扫描（大小写不敏感、单词边界匹配）作为第二层防御，
       默认名单：`INSERT UPDATE DELETE DROP TRUNCATE ALTER CREATE RENAME
       GRANT REVOKE CALL EXECUTE LOAD HANDLER OUTFILE DUMPFILE LOAD_FILE
       SLEEP BENCHMARK`，可通过配置覆盖/追加。
  - `apply_row_limit(sql) -> str`：用 sqlglot 改写 SQL——无 LIMIT 则追加
    `LIMIT max_rows`；已有 LIMIT 但超过 max_rows 则收紧为 max_rows。

### 配置

`conf/app_config.yaml` 新增（`app/conf/app_config.py` 增加对应 dataclass）：

```yaml
sql_safety:
  enabled: true
  timeout_seconds: 30
  max_rows: 1000
  # blacklisted_keywords 不配置时使用代码内默认名单
```

### 仓储层改造 `dw_mysql_repository.py`

- `validate(sql)`：先 `checker.check(sql)`；执行 EXPLAIN 前设置
  `SET SESSION max_execution_time = {timeout_seconds*1000}`（MySQL 服务端
  超时，只对 SELECT 生效，与本功能只读约束吻合）。
- `run(sql)`：
  1. `checker.check(sql)`；
  2. `sql = checker.apply_row_limit(sql)`；
  3. 设置 `max_execution_time` 会话变量，并用 `asyncio.wait_for(..., timeout_seconds)`
     包裹执行作为客户端兜底；
  4. 结果用 `fetchmany(max_rows)` 截断，作为行数限制的最后一道保险。

### 节点层微调 `validate_sql.py`

现有逻辑捕获所有异常写入 `state["error"]` 转 correct_sql。改为：
`SqlSafetyError` 单独捕获并**直接向上抛出**（终止图执行、前端收到 error 事件），
其他异常维持原语法纠错流程不变。

### 依赖

`pyproject.toml` 新增 `sqlglot`。

## 边界与已知取舍

- 黑名单在原始文本上做词边界匹配，字符串字面量中恰好出现黑名单单词
  （如 `where remark = 'delete'`）会误杀。取舍：宁可误杀（安全优先），
  名单可配置以应对实际误报；AST 只读校验才是主防线。
- `MAX_EXECUTION_TIME` 是 MySQL 5.7.8+ 特性；`asyncio.wait_for` 兜底超时后
  取消的是客户端等待，服务端查询由 MAX_EXECUTION_TIME 终止。
- 元数据库（meta）访问路径不加限制——它执行的是代码内固定 SQL，
  本功能只约束 LLM 生成、面向数仓(dw)的 SQL。

## 不做的事（YAGNI）

- 不做表级/列级权限控制、脱敏。
- 不做违规后自动修复重试（已确认直接报错）。
- 不改 correct_sql → run_sql 的图结构（仓储层检查已覆盖该路径）。

## 验收标准

1. 单条 SELECT 正常执行，结果不超过 max_rows 行。
2. 含写操作（INSERT/UPDATE/DELETE/DROP 等）、多语句、非 SELECT 的 SQL
   在 validate 和 run 两个入口均被拒绝并抛 `SqlSafetyError`，图执行终止，
   前端收到 error 事件。
3. 超过 max_rows 的查询结果被截断到 max_rows；SQL 中已有更小 LIMIT 时保留原值。
4. 慢查询在 timeout_seconds 内被终止并报错。
5. `sql_safety.enabled: false` 时全部检查跳过（逃生口）。
6. sql_safety 模块有单元测试覆盖上述规则（RED-GREEN-REFACTOR）。
