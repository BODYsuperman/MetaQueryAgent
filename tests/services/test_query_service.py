import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import app.services.query_service as qs
from app.services.session_store import SessionStore


class FakeGraph:
    """替换真实图：捕获输入 state，只产出一个 result 事件"""

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
