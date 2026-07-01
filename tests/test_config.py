import pytest

from app.config import Settings, load_settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-test")
    settings = Settings()
    assert settings.gitlab_url == "https://gitlab.example.com"
    assert settings.gitlab_token == "glpat-test"
    assert settings.port == 8080
    assert settings.request_timeout == 30


def test_load_settings_exits_when_token_missing(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        load_settings()
