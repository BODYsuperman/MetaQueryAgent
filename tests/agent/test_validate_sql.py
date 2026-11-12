from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.nodes.validate_sql import validate_sql
from app.core.sql_safety import SqlSafetyError


def make_runtime(repo):
    runtime = MagicMock()
    runtime.stream_writer = MagicMock()
    runtime.context = {"dw_mysql_repository": repo}
    return runtime


async def test_syntax_error_returns_state_error():
    repo = AsyncMock()
    repo.validate.side_effect = Exception("unknown column")
    result = await validate_sql({"sql": "select x"}, make_runtime(repo))
    assert result == {"error": "unknown column"}


async def test_safety_error_propagates():
    repo = AsyncMock()
    repo.validate.side_effect = SqlSafetyError("只允许执行只读SELECT查询")
    with pytest.raises(SqlSafetyError):
        await validate_sql({"sql": "delete from t"}, make_runtime(repo))
