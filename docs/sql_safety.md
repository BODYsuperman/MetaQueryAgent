# SQL 安全防护

对 LLM 生成、面向数仓（dw）执行的 SQL 提供四层防护。所有检查在仓储层
`DWMySQLRepository.validate()/run()` 入口强制执行，任何调用路径（包括
`correct_sql → run_sql`）都无法绕过。设计细节见
[设计文档](superpowers/specs/*.md)。

## 四层防护

| 防护 | 实现 | 说明 |
|------|------|------|
| 只读限制 | sqlglot AST 解析 | 必须恰好 1 条语句，且为 SELECT（含 WITH/UNION/EXCEPT/INTERSECT） |
| 黑名单关键字 | 词边界正则（大小写不敏感） | 默认名单：INSERT、UPDATE、DELETE、DROP、TRUNCATE、ALTER、CREATE、RENAME、GRANT、REVOKE、CALL、EXECUTE、LOAD、HANDLER、OUTFILE、DUMPFILE、LOAD_FILE、SLEEP、BENCHMARK |
| 查询超时 | MySQL `MAX_EXECUTION_TIME`（服务端）+ `asyncio.wait_for`（客户端兜底） | 默认 30 秒 |
| 行数限制 | sqlglot 改写 LIMIT + `fetchmany` 截断 | 默认 1000 行；已有更小 LIMIT 时保留原值 |

## 配置

`conf/app_config.yaml`：

```yaml
sql_safety:
  enabled: true          # false 时跳过所有检查（逃生口）
  timeout_seconds: 30
  max_rows: 1000
  # blacklisted_keywords: [...]  # 不配置时使用上面的默认名单
```

## 违规时的行为

安全检查未通过时抛出 `SqlSafetyError`（`app/core/sql_safety.py`），
本次查询直接终止，前端通过 SSE 收到 `status: "error"` 进度事件；
**不会**进入 correct_sql 纠错流程。普通语法错误仍走原有纠错流程不变。

## 已知取舍

- 黑名单在原始文本上匹配，字符串字面量中恰好出现黑名单单词
  （如 `where remark = 'delete'`）会被误杀——安全优先，可通过配置调整名单。
- 只约束数仓（dw）路径；元数据库（meta）执行的是代码内固定 SQL，不做限制。
