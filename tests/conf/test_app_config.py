from app.conf.app_config import app_config


def test_sql_safety_config_loaded():
    cfg = app_config.sql_safety
    assert cfg.enabled is True
    assert cfg.timeout_seconds == 30
    assert cfg.max_rows == 1000
    assert "DROP" in cfg.blacklisted_keywords
    assert "OUTFILE" in cfg.blacklisted_keywords
