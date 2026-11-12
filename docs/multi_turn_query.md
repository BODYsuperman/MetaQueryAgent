# 多轮问数（会话记忆）

支持基于上一次结果继续追问：系统记住每个会话最近几轮的问答，把
"那上个月呢？""哪个分类最高？"这类追问改写成自包含问题后走原有链路。
设计细节见[设计文档](superpowers/specs/*.md)。

## API 契约

`POST /api/query` 请求体新增可选字段 `session_id`：

```json
{"query": "统计全国各分类商品去年卖了多少钱？"}
{"query": "那前年呢？", "session_id": "<上一轮响应里下发的 id>"}
```

SSE 响应**首个事件**下发会话 id，前端保存并在追问时回传：

```
data: {"type": "session", "session_id": "9f3a...32位hex"}
```

不带 `session_id` 的请求视为新会话，其余行为与单轮版本完全一致。

## 工作流程

```
请求(query, session_id?)
  → QueryService: 生成/复用 session_id，读历史快照注入 state
  → rewrite_query 节点：
      · 无历史（首轮）→ 直接跳过，不调 LLM
      · 有历史 → LLM 对照历史（问题+SQL+结果预览）把追问改写成自包含问题
  → 现有链路原样运行：extract_keywords → 召回 → generate_sql → validate → run_sql
  → run_sql 成功后写入会话历史（用户原话 + SQL + 结果前 20 行）
```

## SessionStore 行为（`app/services/session_store.py`）

| 项 | 值 |
|----|----|
| 每会话保留轮数 | 最近 5 轮 |
| 会话总数上限 | 200，超限按插入序淘汰最旧 |
| 结果预览 | 每轮只存前 20 行 |
| 失败轮 | 不写入历史（追问基于成功结果） |
| 存储介质 | 进程内存，**重启丢失**，多 worker 不共享 |

需要持久化时保持 `SessionStore` 接口不变替换实现即可。

## 已知取舍

- 改写质量依赖 LLM；改写错误会传导到召回与生成（与单轮生成 SQL 的风险同质）。
- 并发同 session 请求不做互斥，后写覆盖。
- 前端接入（保存并回传 session_id）是独立工作，本功能只暴露契约。
