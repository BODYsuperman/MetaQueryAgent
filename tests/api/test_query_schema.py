from app.api.schemas.query_schema import QuerySchema


def test_session_id_optional_defaults_none():
    assert QuerySchema(query="q").session_id is None


def test_session_id_accepted():
    assert QuerySchema(query="q", session_id="s1").session_id == "s1"
