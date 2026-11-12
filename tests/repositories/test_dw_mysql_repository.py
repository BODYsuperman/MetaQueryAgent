import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.sql_safety import SqlSafetyError
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository


def make_session():
    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.fetchmany.return_value = [{"id": 1}]
    session.execute.return_value = result
    return session


async def test_run_rejects_write_sql():
    repo = DWMySQLRepository(make_session())
    with pytest.raises(SqlSafetyError):
        await repo.run("delete from fact_order")


async def test_validate_rejects_write_sql():
    repo = DWMySQLRepository(make_session())
    with pytest.raises(SqlSafetyError):
        await repo.validate("drop table users")


async def test_run_sets_timeout_and_limits_rows():
    session = make_session()
    repo = DWMySQLRepository(session)
    await repo.run("select * from fact_order")
    executed = [str(c.args[0].text) for c in session.execute.call_args_list]
    # 服务端超时变量已设置
    assert any("max_execution_time" in s for s in executed)
    # SQL 被改写追加了 LIMIT
    assert any("LIMIT 1000" in s.upper() for s in executed)
    # 结果集用 fetchmany 截断
    session.execute.return_value.mappings.return_value.fetchmany.assert_called_once_with(
        1000
    )


async def test_validate_sets_timeout():
    session = make_session()
    repo = DWMySQLRepository(session)
    await repo.validate("select * from fact_order")
    executed = [str(c.args[0].text) for c in session.execute.call_args_list]
    assert any("max_execution_time" in s for s in executed)


async def test_run_timeout_raises_safety_error():
    session = make_session()
    # SET 会话变量成功，查询本身超时
    session.execute.side_effect = [None, asyncio.TimeoutError()]
    repo = DWMySQLRepository(session)
    with pytest.raises(SqlSafetyError):
        await repo.run("select 1")


async def test_disabled_run_skips_timeout_and_row_cap(monkeypatch):
    from app.conf.app_config import app_config

    # 逃生口：enabled=False 时规格要求全部检查跳过（含超时与行数截断）
    monkeypatch.setattr(app_config.sql_safety, "enabled", False)
    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.fetchall.return_value = [{"id": 1}]
    session.execute.return_value = result
    repo = DWMySQLRepository(session)

    rows = await repo.run("delete from fact_order")

    assert rows == [{"id": 1}]
    executed = [str(c.args[0].text) for c in session.execute.call_args_list]
    assert not any("max_execution_time" in s for s in executed)
    result.mappings.return_value.fetchall.assert_called_once()
