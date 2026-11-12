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
    assert history[0].question == "那上个月呢？"  # 存原话而非改写后问题
    assert history[0].sql == "select * from fact_order"
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

    assert store.get_history("s1") == []
