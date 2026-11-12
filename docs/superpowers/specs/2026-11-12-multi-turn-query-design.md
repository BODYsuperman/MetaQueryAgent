# 多轮问数（会话记忆）设计文档

日期：2026-11-12
状态：待审批

## 背景与意图

data-agent 当前是纯单轮架构：`POST /api/query {query}` 每次新建
`DataAgentState` 走完整链路（extract_keywords → 三路召回 → 过滤补全 →
generate_sql → validate → run_sql），请求之间没有任何关联。

需要支持**多轮问数**：用户基于上一次结果继续追问（"那上个月呢？"
"哪个分类最高？"），系统能理解上下文。追问句往往缺关键词，直接送进
现有召回链路会检索落空，因此需要一个上下文补齐机制。

## 已确认的决策（用户选定）

| 决策点 | 结论 |
|--------|------|
| 核心机制 | **问题改写节点**：新增 `rewrite_query` 节点，LLM 拿历史把追问改写成自包含问题，后续链路零改动 |
| 会话存储 | **进程内存**：新建 SessionStore 模块，dict 按 session_id 存最近 N 轮；重启丢失、单 worker，后续需要持久化时接口不变只换实现 |

否决的方案：
- 历史直接注入 generate_sql 提示词——召回阶段拿到的仍是残缺追问句，检索质量无保障。
- 改写 + 注入双重机制——token 消耗与复杂度最高，改写后历史信息已包含在问题里，收益有限。
- MySQL/Redis 持久化——当前阶段（本地 docker + 单进程）复杂度不成比例。

## 设计

### API 契约（向后兼容）

- `QuerySchema` 增加可选字段 `session_id: str | None = None`。
  不传 → 服务端生成 `uuid4().hex`，行为等同现在的单轮。
- `QueryService.query(query, session_id)`：SSE 流**开始时先发出**
  `{"type": "session", "session_id": "..."}` 事件，前端保存并在追问时回传。
- 其余事件格式不变。

### SessionStore（新模块 `app/services/session_store.py`）

- `TurnRecord`（dataclass）：`question`（用户原话）、`sql`、
  `result_preview`（前 20 行结果字典列表）。
- `SessionStore`：
  - `append(session_id, record)`：追加一轮；每会话只保留最近 5 轮。
  - `get_history(session_id) -> list[TurnRecord]`：无会话返回空列表。
  - 会话总数上限 200，超限按插入序淘汰最旧会话（dict 保序，`popitem` 风格）。
- 模块级单例 `session_store = SessionStore()`（与 `sql_safety_checker`、
  client_manager 的现有单例模式一致）。

### State 扩展（`app/agent/state.py`）

`DataAgentState` 新增三个字段：
- `session_id: str`
- `original_query: str` —— 用户原始输入，改写不覆盖它
- `history: list[dict]` —— 本轮开始时从 SessionStore 读出的历史快照

`query` 字段语义变为"当前用于检索与生成的问题"（首轮=原始输入，
追问轮=改写后的自包含问题）。

### rewrite_query 节点（新节点 `app/agent/nodes/rewrite_query.py`）

- 图结构变化：`START → rewrite_query → extract_keywords`（其余边不动）。
- 逻辑：
  - `history` 为空 → 直接返回 `{}`，**不调 LLM**（首轮零开销）。
  - 有历史 → 新提示词 `prompts/rewrite_query.prompt`，输入
    `history`（YAML 序列化，与现有节点一致）与 `query`，输出改写后的
    自包含问题；LLM 判断无需改写时应原样返回问题（提示词中约定）。
  - 返回 `{"query": 改写结果}`。
  - 进度事件：step "Rewrite Query"，running/success/error，与现有节点一致。

### 历史入库（run_sql 节点）

- `run_sql` 成功拿到结果后：
  `session_store.append(state["session_id"], TurnRecord(question=state["original_query"], sql=state["sql"], result_preview=result[:20]))`。
- session_store 直接 import 模块级单例（不进 DataAgentContext，
  避免改动 context 结构与所有构造点）。
- **取舍：失败轮不入历史**。查询失败（语法纠错失败/安全拦截/超时）时
  该轮不写入 SessionStore，下一轮视同该轮未发生。理由：追问基于成功
  结果，失败轮没有可参照的 SQL/结果；实现上也避免在异常路径埋写库逻辑。

### QueryService 改动

- `query(self, query, session_id=None)`：
  1. `session_id` 为空则 `uuid4().hex` 生成；
  2. 先 yield `{"type": "session", "session_id": ...}` SSE 事件；
  3. `history = session_store.get_history(session_id)`，以 dataclass 转
     dict 列表注入 state；
  4. `DataAgentState(query=query, original_query=query, session_id=..., history=...)`；
  5. 其余流式逻辑不变。

## 边界与已知取舍

- 进程内存存储：重启丢会话、多 worker 不共享——当前部署形态（单进程）
  可接受，SessionStore 接口设计为可替换实现。
- 结果预览截前 20 行：追问"哪个最高"类问题通常只涉及头部数据；
  完整结果不入库以控制内存。
- 改写质量依赖 LLM：改写错误会传导到召回与生成（与单轮生成 SQL 的
  风险同质，不额外兜底）。
- 并发同 session 请求不做互斥：后写覆盖，演示场景可接受。

## 不做的事（YAGNI）

- 不改前端代码（契约通过 SSE session 事件暴露，前端接入是独立工作）。
- 不做持久化存储、会话管理 API（列出/删除历史）。
- 不做失败轮重试或失败历史利用。
- 不改召回/生成/纠错节点的提示词与逻辑（correct_sql 提示词已含 query，
  改写后的 query 自然传入）。

## 验收标准

1. 不带 session_id 的请求行为与现在完全一致（回归），响应含 session 事件。
2. 带同一 session_id 连续两次请求：第二轮追问（如"那上个月呢？"）经
   rewrite_query 改写成自包含问题，能走完召回→生成→执行链路。
3. 首轮（无历史）不调用 LLM 改写（单测钉住）。
4. SessionStore：每会话最多 5 轮、会话总数最多 200、result_preview
   截断 20 行（单测钉住）。
5. 失败轮不写入历史（单测钉住）。
6. 新增节点/store/service 改动均有单元测试；全量测试通过。
