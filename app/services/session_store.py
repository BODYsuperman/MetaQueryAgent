"""
会话存储

多轮问数的会话记忆：按 session_id 保存每轮的用户原话、执行的 SQL
和结果预览，供 rewrite_query 节点把追问改写成自包含问题时参照。

进程内存存储（dict），重启丢失、多 worker 不共享；当前部署形态
（单进程 FastAPI）可接受，需要持久化时保持接口不变替换实现即可。
"""

from dataclasses import dataclass


@dataclass
class TurnRecord:
    """一轮成功问数的记录"""

    question: str  # 用户原话（非改写后的问题）
    sql: str  # 本轮实际执行的 SQL
    result_preview: list[dict]  # 结果前 PREVIEW_ROWS 行


class SessionStore:
    """按会话保存最近若干轮问答记录"""

    MAX_TURNS = 5  # 每会话保留轮数
    MAX_SESSIONS = 200  # 会话总数上限，超限按插入序淘汰最旧
    PREVIEW_ROWS = 20  # result_preview 截断行数

    def __init__(self):
        # dict 保插入序，兼作会话淘汰顺序的依据
        self._sessions: dict[str, list[TurnRecord]] = {}

    def append(
        self, session_id: str, question: str, sql: str, result: list[dict]
    ) -> None:
        """写入一轮记录，并维护轮数与会话数上限"""
        turns = self._sessions.setdefault(session_id, [])
        turns.append(
            TurnRecord(
                question=question,
                sql=sql,
                result_preview=result[: self.PREVIEW_ROWS],
            )
        )
        if len(turns) > self.MAX_TURNS:
            del turns[: len(turns) - self.MAX_TURNS]

        while len(self._sessions) > self.MAX_SESSIONS:
            oldest = next(iter(self._sessions))
            del self._sessions[oldest]

    def get_history(self, session_id: str) -> list[TurnRecord]:
        """读取会话历史，无会话返回空列表"""
        return self._sessions.get(session_id, [])


# 模块级单例，与 sql_safety_checker、client_manager 的现有模式一致
session_store = SessionStore()
