from unittest.mock import MagicMock

from langchain_core.runnables import RunnableLambda

import app.agent.nodes.rewrite_query as rq
from app.agent.nodes.rewrite_query import rewrite_query

HISTORY = [
    {
        "question": "各分类去年销售额",
        "sql": "select 1",
        "result_preview": [{"a": 1}],
    }
]


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
    result = await rewrite_query(
        {"query": "各分类销售额", "history": []}, make_runtime()
    )
    assert result == {}
    assert calls == []  # 首轮零 LLM 开销


async def test_missing_history_key_skips_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(rq, "llm", fake_llm(calls))
    result = await rewrite_query({"query": "各分类销售额"}, make_runtime())
    assert result == {}


async def test_with_history_rewrites_query(monkeypatch):
    calls = []
    monkeypatch.setattr(rq, "llm", fake_llm(calls))
    result = await rewrite_query(
        {"query": "那上个月呢？", "history": HISTORY}, make_runtime()
    )
    assert result == {"query": "统计全国各分类商品上个月的销售额"}
    assert len(calls) == 1


async def test_blank_llm_output_keeps_original(monkeypatch):
    monkeypatch.setattr(rq, "llm", fake_llm([], output="   "))
    result = await rewrite_query(
        {"query": "那上个月呢？", "history": HISTORY}, make_runtime()
    )
    assert result == {}
