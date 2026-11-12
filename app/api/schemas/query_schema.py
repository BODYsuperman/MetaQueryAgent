from pydantic import BaseModel


class QuerySchema(BaseModel):
    query: str
    # 会话 id：追问时回传 SSE session 事件里下发的 id；不传则视为新会话
    session_id: str | None = None