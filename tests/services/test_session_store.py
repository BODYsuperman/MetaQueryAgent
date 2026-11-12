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
    assert store.get_history("s0") == []  # 最旧被淘汰
    assert len(store.get_history("s200")) == 1
