# SQL 安全防护 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 LLM 生成并面向数仓执行的 SQL 增加四层防护：只读限制、黑名单关键字、查询超时、结果行数限制。

**Architecture:** 新增独立安全模块 `app/core/sql_safety.py`（sqlglot AST 只读校验 + 黑名单正则 + LIMIT 改写），在仓储层咽喉点 `DWMySQLRepository.validate()/run()` 强制调用；`validate_sql` 节点对 `SqlSafetyError` 单独放行上抛以终止图执行。配置沿用 OmegaConf dataclass 模式，新增 `sql_safety` 段。

**Tech Stack:** Python 3.14, sqlglot（新依赖）, SQLAlchemy async + asyncmy, pytest + pytest-asyncio（新 dev 依赖）, LangGraph。

**Spec:** `docs/superpowers/specs/2026-11-12-sql-safety-design.md`

## Global Constraints

- 只约束 dw 数仓路径（`DWMySQLRepository`）；meta 库路径不加限制、不改动。
- 不改 LangGraph 图结构（`graph.py` 的边不动）。
- 遵循项目现有风格：中文注释、loguru 日志、模块级单例（参照 `mysql_client_manager.py`）。
- 默认值：`timeout_seconds: 30`、`max_rows: 1000`、`enabled: true`。
- `sql_safety.enabled: false` 时所有检查跳过（逃生口）。
- 违规抛出 `SqlSafetyError`，直接终止本次查询，不走 correct_sql。
- 不修改与本功能无关的代码（含 `conf/app_config.yaml` 中已暴露的 API key 问题，只提醒不处理）。

## Review Focus

1. `SELECT ... INTO OUTFILE '/tmp/x'` —— AST 是 Select 会放行，必须由黑名单 OUTFILE 拦截（Task 2 测试钉住）。
2. 多语句注入 `SELECT 1; DROP TABLE users` —— 必须被"恰好 1 条语句"规则拒绝（Task 2 测试钉住）。
3. 大小写/空白绕过 `  sElEcT 1 ` —— 校验必须大小写不敏感、容忍前后空白（Task 2 测试钉住）。
4. 已有更小 LIMIT 时不被放大：`SELECT * FROM t LIMIT 5` 在 max_rows=1000 下保持 LIMIT 5（Task 3 测试钉住）。
5. `enabled: false` 时写操作 SQL 也能通过检查（Task 2 测试钉住）。

---

### Task 1: 依赖与配置

**Files:**
- Modify: `pyproject.toml`（dependencies 增加 `sqlglot`；新增 dev 依赖组与 pytest 配置）
- Modify: `app/conf/app_config.py`（新增 `SqlSafetyConfig` dataclass，`AppConfig` 增加 `sql_safety` 字段）
- Modify: `conf/app_config.yaml`（新增 `sql_safety` 段）
- Test: `tests/conf/test_app_config.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass
  class SqlSafetyConfig:
      enabled: bool = True
      timeout_seconds: int = 30
      max_rows: int = 1000
      blacklisted_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_BLACKLIST))
  ```
  `DEFAULT_BLACKLIST`（模块级常量，定义在 `app/core/sql_safety.py`，见 Task 2；本任务中 `SqlSafetyConfig` 先直接从该模块导入前需避免循环依赖——将 `DEFAULT_BLACKLIST` 定义在 `app/conf/app_config.py` 顶部并由 `sql_safety.py` 复用，或直接在 dataclass 默认值中内联名单；实现者二选一，保证 `app_config.py` 不 import `sql_safety.py`）。
  `app_config.sql_safety` 全局可访问。

- [ ] **Step 1: 添加依赖**

`pyproject.toml` dependencies 中加入 `"sqlglot>=26.0.0"`；加入 dev 依赖组：
```toml
[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```
运行 `uv sync`（或项目现用安装方式），验证：`uv run python -c "import sqlglot, pytest"` 无报错。

- [ ] **Step 2: 写失败的配置测试**

```python
# tests/conf/test_app_config.py
from app.conf.app_config import app_config

def test_sql_safety_config_loaded():
    cfg = app_config.sql_safety
    assert cfg.enabled is True
    assert cfg.timeout_seconds == 30
    assert cfg.max_rows == 1000
    assert "DROP" in cfg.blacklisted_keywords
    assert "OUTFILE" in cfg.blacklisted_keywords
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest tests/conf/test_app_config.py -v`
Expected: FAIL（`AppConfig` 无 `sql_safety` 属性）

- [ ] **Step 4: 实现配置**

`app/conf/app_config.py`：按 Interfaces 中的定义新增 `SqlSafetyConfig`（含默认黑名单常量，名单与设计文档一致：`INSERT UPDATE DELETE DROP TRUNCATE ALTER CREATE RENAME GRANT REVOKE CALL EXECUTE LOAD HANDLER OUTFILE DUMPFILE LOAD_FILE SLEEP BENCHMARK`），`AppConfig` 增加字段 `sql_safety: SqlSafetyConfig`。
`conf/app_config.yaml` 末尾新增：
```yaml
sql_safety:
  enabled: true
  timeout_seconds: 30
  max_rows: 1000
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/conf/test_app_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml app/conf/app_config.py conf/app_config.yaml tests/ uv.lock
git commit -m "feat: add sql_safety config section and sqlglot/pytest dependencies"
```

---

### Task 2: SqlSafetyChecker.check() 只读校验

**Files:**
- Create: `app/core/sql_safety.py`
- Test: `tests/core/test_sql_safety.py`

**Interfaces:**
- Consumes: `app_config.sql_safety`（Task 1）
- Produces:
  ```python
  class SqlSafetyError(Exception): ...

  class SqlSafetyChecker:
      def __init__(self, config: SqlSafetyConfig): ...
      def check(self, sql: str) -> None:  # 违规抛 SqlSafetyError；解析失败抛原始 sqlglot ParseError
      def apply_row_limit(self, sql: str) -> str:  # 本任务先不实现（Task 3）

  sql_safety_checker = SqlSafetyChecker(app_config.sql_safety)  # 模块级单例
  ```

- [ ] **Step 1: 写失败的测试**

```python
# tests/core/test_sql_safety.py
import pytest
from app.conf.app_config import SqlSafetyConfig
from app.core.sql_safety import SqlSafetyChecker, SqlSafetyError

@pytest.fixture
def checker():
    return SqlSafetyChecker(SqlSafetyConfig())

def test_select_passes(checker):
    checker.check("select * from fact_order limit 10")  # 不抛异常

def test_case_insensitive_and_whitespace(checker):
    checker.check("  sElEcT 1 ")

def test_with_cte_select_passes(checker):
    checker.check("with t as (select id from fact_order) select * from t")

def test_write_rejected(checker):
    with pytest.raises(SqlSafetyError):
        checker.check("delete from fact_order")

def test_into_outfile_rejected(checker):
    with pytest.raises(SqlSafetyError):
        checker.check("select * from fact_order into outfile '/tmp/x'")

def test_multi_statement_rejected(checker):
    with pytest.raises(SqlSafetyError):
        checker.check("select 1; drop table users")

def test_sleep_blacklisted(checker):
    with pytest.raises(SqlSafetyError):
        checker.check("select sleep(10)")

def test_unparseable_raises_parse_error_not_safety(checker):
    import sqlglot
    with pytest.raises(sqlglot.errors.ParseError):
        checker.check("select from where ((( ")

def test_disabled_skips_all():
    c = SqlSafetyChecker(SqlSafetyConfig(enabled=False))
    c.check("delete from fact_order")  # 不抛异常
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/core/test_sql_safety.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `app/core/sql_safety.py`**

check() 逻辑顺序：
1. `if not self.config.enabled: return`
2. `expressions = sqlglot.parse(sql, dialect="mysql")`——ParseError 原样上抛（交回语法纠错流程）；过滤 None 后语句数 != 1 → `SqlSafetyError("只允许执行单条SQL语句")`
3. 语句类型不是 `sqlglot.exp.Select / Union / Except / Intersect` 之一 → `SqlSafetyError("只允许执行只读SELECT查询")`
4. 黑名单正则：`re.search(r"\b(" + "|".join(keywords) + r")\b", sql, re.IGNORECASE)` 命中 → `SqlSafetyError(f"SQL包含被禁止的关键字: {命中词}")`
文件末尾创建模块级单例 `sql_safety_checker = SqlSafetyChecker(app_config.sql_safety)`；`apply_row_limit` 本任务先原样返回 sql（Task 3 实现）。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/core/test_sql_safety.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/sql_safety.py tests/core/
git commit -m "feat: add SqlSafetyChecker read-only validation with AST and blacklist"
```

---

### Task 3: SqlSafetyChecker.apply_row_limit() 行数限制改写

**Files:**
- Modify: `app/core/sql_safety.py`
- Test: `tests/core/test_sql_safety.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `SqlSafetyChecker`
- Produces: `apply_row_limit(self, sql: str) -> str`——无 LIMIT 追加 `LIMIT max_rows`；已有 LIMIT 大于 max_rows 收紧为 max_rows；已有 LIMIT 小于等于 max_rows 保留原值；`enabled=False` 时原样返回。

- [ ] **Step 1: 写失败的测试（追加到 tests/core/test_sql_safety.py）**

```python
def test_limit_appended(checker):
    out = checker.apply_row_limit("select * from fact_order")
    assert "1000" in out  # LIMIT 1000

def test_existing_larger_limit_tightened(checker):
    out = checker.apply_row_limit("select * from fact_order limit 5000")
    assert "5000" not in out and "1000" in out

def test_existing_smaller_limit_preserved(checker):
    out = checker.apply_row_limit("select * from fact_order limit 5")
    assert "5" in out and "1000" not in out

def test_limit_disabled():
    c = SqlSafetyChecker(SqlSafetyConfig(enabled=False))
    assert c.apply_row_limit("select * from t") == "select * from t"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/core/test_sql_safety.py -v -k limit`
Expected: FAIL

- [ ] **Step 3: 实现 apply_row_limit**

用 `sqlglot.parse_one(sql, dialect="mysql")` 取表达式；读取 `expression.args.get("limit")`：无则 `expression = expression.limit(self.config.max_rows, dialect="mysql")`；有则解析其 `expression` 字面量整数值，大于 max_rows 时同样调用 `.limit(max_rows)` 覆盖，否则不动。返回 `expression.sql(dialect="mysql")`。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/core/test_sql_safety.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/sql_safety.py tests/core/test_sql_safety.py
git commit -m "feat: add row limit rewriting to SqlSafetyChecker"
```

---

### Task 4: 仓储层接入（超时 + 行数截断 + 强制检查）

**Files:**
- Modify: `app/repositories/mysql/dw/dw_mysql_repository.py`（`validate()` 与 `run()`）
- Test: `tests/repositories/test_dw_mysql_repository.py`

**Interfaces:**
- Consumes: `app.core.sql_safety` 的 `sql_safety_checker` 单例、`SqlSafetyError`；`app_config.sql_safety.timeout_seconds / max_rows`
- Produces: `DWMySQLRepository.validate(sql)` / `run(sql)` 签名不变；内部行为：
  1. 先 `sql_safety_checker.check(sql)`（validate 与 run 都执行）
  2. run 中 `sql = sql_safety_checker.apply_row_limit(sql)`
  3. 执行前 `SET SESSION max_execution_time = timeout_seconds * 1000`
  4. `asyncio.wait_for(session.execute(...), timeout_seconds)`，超时转抛 `SqlSafetyError("查询执行超时...")`
  5. run 结果 `fetchmany(max_rows)` 截断
  其余方法（get_column_types 等）不动。

- [ ] **Step 1: 写失败的测试（用 AsyncMock 伪造 session，不需要真实数据库）**

```python
# tests/repositories/test_dw_mysql_repository.py
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.core.sql_safety import SqlSafetyError
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository

def make_session():
    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.fetchmany.return_value = [{"id": 1}]
    session.execute.return_value = result
    return session

async def test_run_rejects_write_sql():
    repo = DWMySQLRepository(make_session())
    with pytest.raises(SqlSafetyError):
        await repo.run("delete from fact_order")

async def test_validate_rejects_write_sql():
    repo = DWMySQLRepository(make_session())
    with pytest.raises(SqlSafetyError):
        await repo.validate("drop table users")

async def test_run_sets_timeout_and_limits_rows():
    session = make_session()
    repo = DWMySQLRepository(session)
    await repo.run("select * from fact_order")
    executed = [str(c.args[0].text) for c in session.execute.call_args_list]
    assert any("max_execution_time" in s for s in executed)      # 会话超时变量
    assert any("LIMIT 1000" in s.upper() for s in executed)      # SQL 被改写
    session.execute.return_value.mappings.return_value.fetchmany.assert_called_once_with(1000)

async def test_run_timeout_raises_safety_error():
    session = make_session()
    session.execute.side_effect = [None, asyncio.TimeoutError()]  # SET 成功，查询超时
    # 若实现将 wait_for 包裹在外部，用 side_effect=asyncio.TimeoutError 模拟即可
    repo = DWMySQLRepository(session)
    with pytest.raises(SqlSafetyError):
        await asyncio.wait_for(repo.run("select 1"), 5)
```
（实现者可按最终代码结构调整 mock 细节，断言意图不变：拒绝写 SQL、设置超时变量、改写 LIMIT、fetchmany 截断、超时转 SqlSafetyError。）

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/repositories/ -v`
Expected: FAIL

- [ ] **Step 3: 改造 `validate()` 与 `run()`**

按 Interfaces 中 1-5 的行为实现；`import asyncio`、`from app.core.sql_safety import sql_safety_checker, SqlSafetyError`、`from app.conf.app_config import app_config`。捕获 `asyncio.TimeoutError` 转抛 `SqlSafetyError("查询执行超时，已终止（限制 {timeout_seconds} 秒）")`。保持中文注释风格。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/repositories/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 回归——全量测试**

Run: `uv run pytest -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/repositories/mysql/dw/dw_mysql_repository.py tests/repositories/
git commit -m "feat: enforce sql safety checks, timeout and row limit in DW repository"
```

---

### Task 5: validate_sql 节点放行 SqlSafetyError

**Files:**
- Modify: `app/agent/nodes/validate_sql.py`
- Test: `tests/agent/test_validate_sql.py`

**Interfaces:**
- Consumes: `SqlSafetyError`；现有 `DataAgentState`、`Runtime[DataAgentContext]`
- Produces: 节点行为——`SqlSafetyError` 单独捕获：写 error 进度事件后**向上抛出**（终止图执行）；其他异常维持现状（写 `state["error"]` 走 correct_sql）。

- [ ] **Step 1: 写失败的测试（mock runtime 与 repository）**

```python
# tests/agent/test_validate_sql.py
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.agent.nodes.validate_sql import validate_sql
from app.core.sql_safety import SqlSafetyError

def make_runtime(repo):
    runtime = MagicMock()
    runtime.stream_writer = MagicMock()
    runtime.context = {"dw_mysql_repository": repo}
    return runtime

async def test_syntax_error_returns_state_error():
    repo = AsyncMock()
    repo.validate.side_effect = Exception("unknown column")
    result = await validate_sql({"sql": "select x"}, make_runtime(repo))
    assert result == {"error": "unknown column"}

async def test_safety_error_propagates():
    repo = AsyncMock()
    repo.validate.side_effect = SqlSafetyError("只允许执行只读SELECT查询")
    with pytest.raises(SqlSafetyError):
        await validate_sql({"sql": "delete from t"}, make_runtime(repo))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/agent/ -v`
Expected: `test_safety_error_propagates` FAIL（当前被通用 except 吞掉写入 state）

- [ ] **Step 3: 修改节点**

在内层 `except Exception` 之前增加：
```python
except SqlSafetyError as e:
    logger.error(f"SQL安全检查未通过：{e}")
    writer({"type": "progress", "step": step, "status": "error"})
    raise
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/agent/ -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/nodes/validate_sql.py tests/agent/
git commit -m "feat: terminate graph on SqlSafetyError in validate_sql node"
```

---

### Task 6: 集成验证与文档

**Files:**
- Modify: `README.md`（如存在功能说明章节则追加"SQL 安全防护"小节；无 README 则在 `docs/` 下补充说明并链接设计文档）

**Interfaces:**
- Consumes: 前 5 个任务的全部产出

- [ ] **Step 1: 全量测试回归**

Run: `uv run pytest -v`
Expected: 全部 PASS

- [ ] **Step 2: 静态检查**

Run: `uv run python -c "from app.agent.graph import graph"`
Expected: 无导入错误（确认 graph/节点/仓储改动没有破坏导入链）

- [ ] **Step 3: 本地集成冒烟（若本机 docker 环境可用）**

启动依赖服务后运行 `uv run python -m app.agent.graph`，观察：正常 SELECT 查询成功返回且结果 ≤1000 行。若环境不可用，明确记录"集成冒烟未执行"并说明原因，不得声称已验证。

- [ ] **Step 4: 更新 README 文档**

新增"SQL 安全防护"小节：四层防护说明、`sql_safety` 配置项含义与默认值、违规时的行为（error 事件终止）。

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document sql safety feature and configuration"
```
