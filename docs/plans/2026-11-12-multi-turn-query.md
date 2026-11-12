# 多轮问数（会话记忆）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持基于上一次结果继续追问的多轮问数：新增 rewrite_query 改写节点与进程内存 SessionStore，会话历史注入检索与生成链路。

**Architecture:** API 增加可选 `session_id`（SSE 首事件下发）；`QueryService` 从 SessionStore 读历史注入 state；新节点 `rewrite_query` 在 START 后把追问改写成自包含问题（无历史跳过）；`run_sql` 成功后把原话+SQL+结果前 20 行写回 SessionStore。其余链路零改动。

**Tech Stack:** Python 3.14, FastAPI, LangGraph, langchain-core, pytest + pytest-asyncio（均已存在，无新依赖）。

**Spec:** `docs/superpowers/specs/2026-11-12-multi-turn-query-design.md`

## Global Constraints

- 不带 `session_id` 的请求行为与现在完全一致（仅多一个 session 首事件）。
- 不改动现有节点的提示词与逻辑（run_sql 仅追加历史写入；graph.py 仅动 START 出边）。
- 不改前端代码；不引入新依赖；不做持久化。
- 遵循项目风格：中文注释、loguru、模块级单例（参照 `sql_safety_checker`）、节点结构参照 `generate_sql.py`（progress 事件 running/success/error + try/except raise）。
- 新字段读取一律 `state.get(...)` 防御（graph.py `__main__` 调试脚本等旧构造点不传新字段也不能崩）。

## Review Focus

1. 无 session_id 的旧请求：行为不变，且 SSE 首事件为 `{"type":"session","session_id":<32位hex>}`（Task 4 测试钉住）。
2. 首轮（history 为空）rewrite_query 不调用 LLM（Task 2 测试钉住）。
3. 失败轮不入历史：run_sql 抛异常时 SessionStore 无新增（Task 3 测试钉住）。
4. 轮次上限：同会话写入 7 轮后仅保留最近 5 轮且顺序正确（Task 1 测试钉住）。
5. LLM 改写输出为空/纯空白时保留原问题，不得把空串写进 state（Task 2 测试钉住）。

---

### Task 1: SessionStore 会话存储模块

**Files:**
- Create: `app/services/session_store.py`
- Test: `tests/services/test_session_store.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass
  class TurnRecord:
      question: str          # 用户原话
      sql: str               # 本轮执行的 SQL
      result_preview: list[dict]  # 结果前 PREVIEW_ROWS 行

  class SessionStore:
      MAX_TURNS = 5          # 每会话保留轮数
      MAX_SESSIONS = 200     # 会话总数上限，超限按插入序淘汰最旧
      PREVIEW_ROWS = 20      # result_preview 截断行数

      def append(self, session_id: str, question: str, sql: str, result: list[dict]) -> None
      def get_history(self, session_id: str) -> list[TurnRecord]  # 无会话返回 []

  session_store = SessionStore()  # 模块级单例
  ```

- [ ] **Step 1: 写失败的测试**

```python
# tests/services/test_session_store.py
from app.services.session_store import SessionStore

def test_append_and_get_history():
    store = SessionStore()
    store.append("s1", "各分类去年销售额", "select 1", [{"a": 1}])
    history = store.get_history("s1")
    assert len(history) == 1
    assert history[0].question == "各分类去年销售额"
    assert history[0].sql == "select 1"
    assert history[0].result_preview == [{"a": 1}]

def test_unknown_session_returns_empty():
    assert SessionStore().get_history("nope") == []

def test_result_preview_truncated_to_20():
    store = SessionStore()
    store.append("s1", "q", "select 1", [{"i": i} for i in range(50)])
    assert len(store.get_history("s1")[0].result_preview) == 20

def test_max_turns_keeps_latest_5_in_order():
    store = SessionStore()
    for i in range(7):
        store.append("s1", f"q{i}", f"select {i}", [])
    history = store.get_history("s1")
    assert [r.question for r in history] == ["q2", "q3", "q4", "q5", "q6"]

def test_max_sessions_evicts_oldest():
    store = SessionStore()
    for i in range(201):
        store.append(f"s{i}", "q", "select 1", [])
    assert store.get_history("s0") == []      # 最旧被淘汰
    assert len(store.get_history("s200")) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/services/ -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `app/services/session_store.py`**

按 Interfaces 实现；内部 `dict[str, list[TurnRecord]]`（保插入序）；append 中截断 `result[:PREVIEW_ROWS]`、追加后 `del turns[:-MAX_TURNS]` 式裁剪、会话数超 `MAX_SESSIONS` 时 `next(iter(...))` 淘汰最旧键。中文 docstring 说明"进程内存存储，重启丢失，接口可替换为持久化实现"。文件末尾创建单例 `session_store = SessionStore()`。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/services/ -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/session_store.py tests/services/
git commit -m "feat: add in-process SessionStore for multi-turn query memory"
```

---

### Task 2: State 扩展 + rewrite_query 节点 + 提示词

**Files:**
- Modify: `app/agent/state.py`（`DataAgentState` 新增字段）
- Create: `prompts/rewrite_query.prompt`
- Create: `app/agent/nodes/rewrite_query.py`
- Test: `tests/agent/test_rewrite_query.py`

**Interfaces:**
- Consumes: 现有 `app.agent.llm.llm`、`load_prompt`、`runtime.stream_writer`（与 generate_sql 相同模式）
- Produces:
  - `DataAgentState` 新增：`session_id: str`、`original_query: str`、`history: list[dict]`
  - `async def rewrite_query(state: DataAgentState, runtime: Runtime[DataAgentContext]) -> dict`：
    无历史返回 `{}`；有历史返回 `{"query": 改写后的问题}`；改写输出为空白时返回 `{}`

- [ ] **Step 1: state.py 新增字段（无独立测试，随本任务节点测试覆盖）**

在 `DataAgentState` 末尾追加：
```python
    session_id: str  # 会话 id，多轮问数用
    original_query: str  # 用户原始输入，改写不覆盖它
    history: list[dict]  # 本轮开始时的会话历史快照（TurnRecord 的 dict 形式）
```

- [ ] **Step 2: 创建 `prompts/rewrite_query.prompt`**（模板变量 `{history}` `{query}`，风格对齐现有提示词）

```
角色：
你是数据问答系统的问题改写专家，负责把用户的追问改写成"自包含、可独立检索"的完整问题。

任务：
给定【会话历史】（此前每轮的问题、执行的SQL与结果预览）和【当前问题】，判断当前问题是否依赖上下文：
- 若依赖（如"那上个月呢？""哪个分类最高？""再按地区拆分"），从历史中补齐缺失的业务对象、指标、时间范围与筛选条件，改写成无需历史即可独立理解和执行的问题
- 若不依赖（当前问题本身语义完整，或与历史无关），原样输出当前问题

改写规则（严格遵守）：
1. 只输出改写后的一行问题文本，不输出解释、SQL、引号或前缀
2. 只能使用【会话历史】与【当前问题】中出现过的信息，禁止虚构业务口径
3. 保持用户原意，不额外增加或删减分析维度
4. 输出语言与当前问题保持一致

会话历史（YAML）：
{history}

当前问题：
{query}
```

- [ ] **Step 3: 写失败的节点测试**

```python
# tests/agent/test_rewrite_query.py
from unittest.mock import MagicMock

import pytest
from langchain_core.runnables import RunnableLambda

import app.agent.nodes.rewrite_query as rq
from app.agent.nodes.rewrite_query import rewrite_query

HISTORY = [{"question": "各分类去年销售额", "sql": "select 1", "result_preview": [{"a": 1}]}]

def make_runtime():
    runtime = MagicMock()
    runtime.stream_writer = MagicMock()
    runtime.context = {}
    return runtime

def fake_llm(recorder, output="统计全国各分类商品上个月的销售额"):
    def _call(_inputs):
        recorder.append(_inputs)
        return output
    return RunnableLambda(_call)

async def test_no_history_skips_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(rq, "llm", fake_llm(calls))
    result = await rewrite_query({"query": "各分类销售额", "history": []}, make_runtime())
    assert result == {}
    assert calls == []  # 首轮零 LLM 开销

async def test_missing_history_key_skips_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(rq, "llm", fake_llm(calls))
    result = await rewrite_query({"query": "各分类销售额"}, make_runtime())  # 旧构造点无 history 键
    assert result == {}

async def test_with_history_rewrites_query(monkeypatch):
    calls = []
    monkeypatch.setattr(rq, "llm", fake_llm(calls))
    result = await rewrite_query({"query": "那上个月呢？", "history": HISTORY}, make_runtime())
    assert result == {"query": "统计全国各分类商品上个月的销售额"}
    assert len(calls) == 1

async def test_blank_llm_output_keeps_original(monkeypatch):
    monkeypatch.setattr(rq, "llm", fake_llm([], output="   "))
    result = await rewrite_query({"query": "那上个月呢？", "history": HISTORY}, make_runtime())
    assert result == {}
```

- [ ] **Step 4: 运行确认失败**

Run: `uv run pytest tests/agent/test_rewrite_query.py -v`
Expected: FAIL（节点模块不存在）

- [ ] **Step 5: 实现 `app/agent/nodes/rewrite_query.py`**

结构对齐 `generate_sql.py`：step 名 "Rewrite Query"；`history = state.get("history") or []`，为空直接 `return {}`（不发进度事件、不调 LLM）；有历史时发 running 事件，`PromptTemplate(template=load_prompt("rewrite_query"), input_variables=["history", "query"]) | llm | StrOutputParser()`，history 用 `yaml.dump(..., allow_unicode=True, sort_keys=False)`；`rewritten = res.strip()`，为空白返回 `{}`，否则发 success 并返回 `{"query": rewritten}`；except 分支 log + error 事件 + raise（与现有节点一致）。

- [ ] **Step 6: 运行确认通过**

Run: `uv run pytest tests/agent/test_rewrite_query.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add app/agent/state.py app/agent/nodes/rewrite_query.py prompts/rewrite_query.prompt tests/agent/test_rewrite_query.py
git commit -m "feat: add rewrite_query node with session-aware question rewriting"
```

---

### Task 3: graph 接线 + run_sql 历史入库

**Files:**
- Modify: `app/agent/graph.py`（注册节点；`START → rewrite_query → extract_keywords`，删除原 `START → extract_keywords` 边）
- Modify: `app/agent/nodes/run_sql.py`（成功后写入历史）
- Test: `tests/agent/test_run_sql.py`

**Interfaces:**
- Consumes: `app.services.session_store.session_store`（Task 1）、state 的 `session_id`/`original_query`（Task 2）
- Produces: run_sql 成功路径把 `TurnRecord(question=state.get("original_query") or state["query"], sql=sql, result_preview=result[:20])` 写入 `state.get("session_id")` 对应会话；`session_id` 缺失或执行失败时不写入。

- [ ] **Step 1: 写失败的测试**

```python
# tests/agent/test_run_sql.py
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.agent.nodes.run_sql as rs
from app.core.sql_safety import SqlSafetyError
from app.services.session_store import SessionStore

def make_runtime(repo):
    runtime = MagicMock()
    runtime.stream_writer = MagicMock()
    runtime.context = {"dw_mysql_repository": repo}
    return runtime

def make_state():
    return {
        "sql": "select * from fact_order",
        "query": "统计全国各分类商品上个月的销售额",
        "original_query": "那上个月呢？",
        "session_id": "s1",
    }

async def test_run_sql_saves_history(monkeypatch):
    store = SessionStore()
    monkeypatch.setattr(rs, "session_store", store)
    repo = AsyncMock()
    repo.run.return_value = [{"分类": "食品", "销售额": 100}]
    await rs.run_sql(make_state(), make_runtime(repo))
    history = store.get_history("s1")
    assert len(history) == 1
    assert history[0].question == "那上个月呢？"   # 存原话而非改写后问题
    assert history[0].result_preview == [{"分类": "食品", "销售额": 100}]

async def test_failed_run_does_not_save_history(monkeypatch):
    store = SessionStore()
    monkeypatch.setattr(rs, "session_store", store)
    repo = AsyncMock()
    repo.run.side_effect = SqlSafetyError("查询执行超时")
    with pytest.raises(SqlSafetyError):
        await rs.run_sql(make_state(), make_runtime(repo))
    assert store.get_history("s1") == []

async def test_missing_session_id_skips_save(monkeypatch):
    store = SessionStore()
    monkeypatch.setattr(rs, "session_store", store)
    repo = AsyncMock()
    repo.run.return_value = [{"a": 1}]
    state = make_state()
    del state["session_id"]
    await rs.run_sql(state, make_runtime(repo))  # 旧调试脚本兼容，不崩
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/agent/test_run_sql.py -v`
Expected: FAIL（run_sql 未引用 session_store / AttributeError）

- [ ] **Step 3: 修改 run_sql 与 graph**

`run_sql.py`：顶部 `from app.services.session_store import session_store`；在 `result = await dw_mysql_repository.run(sql)` 与日志之后追加：
```python
        # 成功执行后写入会话历史，供后续追问改写参照；失败路径抛异常，不会写入
        session_id = state.get("session_id")
        if session_id:
            session_store.append(
                session_id,
                state.get("original_query") or state["query"],
                sql,
                result,
            )
```
`graph.py`：import 并 `add_node("rewrite_query", rewrite_query)`；把 `add_edge(START, "extract_keywords")` 改为 `add_edge(START, "rewrite_query")` + `add_edge("rewrite_query", "extract_keywords")`；`__main__` 调试 state 增加 `session_id="debug"`、`original_query=原始问题`、`history=[]`。

- [ ] **Step 4: 运行确认通过 + 导入检查**

Run: `uv run pytest tests/agent/test_run_sql.py -v && uv run python -c "from app.agent.graph import graph; print('OK')"`
Expected: 3 passed；OK

- [ ] **Step 5: Commit**

```bash
git add app/agent/graph.py app/agent/nodes/run_sql.py tests/agent/test_run_sql.py
git commit -m "feat: wire rewrite_query into graph and persist turns from run_sql"
```

---

### Task 4: QueryService + API 契约

**Files:**
- Modify: `app/api/schemas/query_schema.py`（`session_id: str | None = None`）
- Modify: `app/api/routers/query_router.py`（透传 `query_schema.session_id`）
- Modify: `app/services/query_service.py`（`query(self, query: str, session_id: str | None = None)`）
- Test: `tests/services/test_query_service.py`、`tests/api/test_query_schema.py`

**Interfaces:**
- Consumes: `session_store` 单例（Task 1）、state 新字段（Task 2）
- Produces: `QueryService.query(query, session_id=None)` 为 async generator：
  1. `session_id` 为空则 `uuid4().hex` 生成；
  2. 首个 yield 为 `data: {"type": "session", "session_id": "..."}\n\n`；
  3. state 含 `session_id`、`original_query=query`、`history=[TurnRecord→dict]`；
  4. 其余 SSE 输出格式不变。

- [ ] **Step 1: 写失败的测试**

```python
# tests/api/test_query_schema.py
from app.api.schemas.query_schema import QuerySchema

def test_session_id_optional_defaults_none():
    assert QuerySchema(query="q").session_id is None

def test_session_id_accepted():
    assert QuerySchema(query="q", session_id="s1").session_id == "s1"
```

```python
# tests/services/test_query_service.py
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import app.services.query_service as qs
from app.services.session_store import SessionStore, TurnRecord

class FakeGraph:
    def __init__(self):
        self.captured_input = None
    def astream(self, input, context, stream_mode):
        self.captured_input = input
        async def gen():
            yield {"type": "result", "data": []}
        return gen()

@asynccontextmanager
async def _fake_session():
    yield AsyncMock()

def make_manager():
    m = MagicMock()
    m.session_factory = _fake_session
    return m

def make_service(monkeypatch, fake_graph, store):
    monkeypatch.setattr(qs, "graph", fake_graph)
    monkeypatch.setattr(qs, "session_store", store)
    monkeypatch.setattr(qs, "meta_mysql_client_manager", make_manager())
    monkeypatch.setattr(qs, "dw_mysql_client_manager", make_manager())
    return qs.QueryService(None, None, None, None, None, None)

async def collect(agen):
    return [json.loads(e.removeprefix("data: ").strip()) async for e in agen]

async def test_session_event_first_and_id_generated(monkeypatch):
    fake = FakeGraph()
    svc = make_service(monkeypatch, fake, SessionStore())
    events = await collect(svc.query("各分类销售额"))
    assert events[0]["type"] == "session"
    assert len(events[0]["session_id"]) == 32

async def test_given_session_id_and_history_injected(monkeypatch):
    fake = FakeGraph()
    store = SessionStore()
    store.append("s1", "各分类去年销售额", "select 1", [{"a": 1}])
    svc = make_service(monkeypatch, fake, store)
    events = await collect(svc.query("那上个月呢？", session_id="s1"))
    assert events[0] == {"type": "session", "session_id": "s1"}
    state = fake.captured_input
    assert state["session_id"] == "s1"
    assert state["original_query"] == "那上个月呢？"
    assert state["query"] == "那上个月呢？"
    assert state["history"][0]["question"] == "各分类去年销售额"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/api/ tests/services/test_query_service.py -v`
Expected: FAIL（schema 无 session_id / query() 不接受第二参数）

- [ ] **Step 3: 实现**

`query_schema.py`：`session_id: str | None = None`。
`query_router.py`：`query_service.query(query_schema.query, query_schema.session_id)`。
`query_service.py`：顶部 import `uuid`、`from dataclasses import asdict`、`from app.services.session_store import session_store`；`query()` 签名加参；进入 async with 之前生成 id 并 yield session 事件（沿用现有 `data: {json}\n\n` 格式与 `ensure_ascii=False`）；state 构造改为：
```python
            history = [asdict(r) for r in session_store.get_history(session_id)]
            state = DataAgentState(
                query=query,
                original_query=query,
                session_id=session_id,
                history=history,
            )
```

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `uv run pytest tests/api/ tests/services/ -v && uv run pytest`
Expected: 新增测试全过；全量套件无回归

- [ ] **Step 5: Commit**

```bash
git add app/api/schemas/query_schema.py app/api/routers/query_router.py app/services/query_service.py tests/api/ tests/services/
git commit -m "feat: add session_id contract and history injection to query API"
```

---

### Task 5: 集成验证与文档

**Files:**
- Create: `docs/multi_turn_query.md`

**Interfaces:**
- Consumes: Task 1-4 全部产出

- [ ] **Step 1: 全量回归 + 导入检查**

Run: `uv run pytest -v && uv run python -c "from app.main import * " 2>/dev/null || uv run python -c "from app.agent.graph import graph; from app.services.query_service import QueryService; print('OK')"`
Expected: 全部测试通过；导入 OK（若项目有 `main.py` 入口则以其实际可导入形式验证）

- [ ] **Step 2: 真实 LLM 冒烟（可选，消耗 token；不可用时如实记录"未执行"）**

启动 docker 依赖后，用两次连续请求验证：第一轮"统计全国各分类商品去年卖了多少钱？"，第二轮带同一 session_id 追问"那前年呢？"。观察日志中出现 "Rewrite Query" 步骤且第二轮改写出的问题含"前年"与完整业务对象。

- [ ] **Step 3: 写 `docs/multi_turn_query.md`**

内容：API 契约（session_id 字段 + session SSE 事件示例）、改写机制流程图（文字版）、SessionStore 行为（5 轮/200 会话/20 行预览/失败轮不入历史/重启丢失）、已知取舍。链接设计文档。

- [ ] **Step 4: Commit**

```bash
git add docs/multi_turn_query.md
git commit -m "docs: document multi-turn query session contract and behavior"
```
