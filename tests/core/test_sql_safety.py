import pytest

from app.conf.app_config import SqlSafetyConfig
from app.core.sql_safety import SqlSafetyChecker, SqlSafetyError


@pytest.fixture
def checker():
    return SqlSafetyChecker(SqlSafetyConfig())


def test_select_passes(checker):
    checker.check("select * from fact_order limit 10")  # 不抛异常


def test_case_insensitive_and_whitespace(checker):
    checker.check("  sElEcT 1 ")


def test_with_cte_select_passes(checker):
    checker.check("with t as (select id from fact_order) select * from t")


def test_write_rejected(checker):
    with pytest.raises(SqlSafetyError):
        checker.check("delete from fact_order")


def test_into_outfile_rejected(checker):
    with pytest.raises(SqlSafetyError):
        checker.check("select * from fact_order into outfile '/tmp/x'")


def test_multi_statement_rejected(checker):
    with pytest.raises(SqlSafetyError):
        checker.check("select 1; drop table users")


def test_sleep_blacklisted(checker):
    with pytest.raises(SqlSafetyError):
        checker.check("select sleep(10)")


def test_unparseable_raises_parse_error_not_safety(checker):
    import sqlglot

    with pytest.raises(sqlglot.errors.ParseError):
        checker.check("select from where ((( ")


def test_disabled_skips_all():
    c = SqlSafetyChecker(SqlSafetyConfig(enabled=False))
    c.check("delete from fact_order")  # 不抛异常


def test_limit_appended(checker):
    out = checker.apply_row_limit("select * from fact_order")
    assert "1000" in out  # LIMIT 1000


def test_existing_larger_limit_tightened(checker):
    out = checker.apply_row_limit("select * from fact_order limit 5000")
    assert "5000" not in out and "1000" in out


def test_existing_smaller_limit_preserved(checker):
    out = checker.apply_row_limit("select * from fact_order limit 5")
    assert "5" in out and "1000" not in out


def test_limit_disabled():
    c = SqlSafetyChecker(SqlSafetyConfig(enabled=False))
    assert c.apply_row_limit("select * from t") == "select * from t"
