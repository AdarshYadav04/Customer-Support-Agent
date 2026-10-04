import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {"litellm_proxy_url": "http://x/v1", "litellm_proxy_key": "k"}


def test_plain_postgres_urls_are_switched_to_asyncpg():
    for url in ("postgresql://u:p@h/db", "postgres://u:p@h/db"):
        assert Settings(database_url=url, **BASE).database_url == "postgresql+asyncpg://u:p@h/db"


def test_asyncpg_url_is_left_alone():
    url = "postgresql+asyncpg://u:p@h/db"
    assert Settings(database_url=url, **BASE).database_url == url


def test_required_settings_must_be_provided(monkeypatch, tmp_path):
    for name in ("DATABASE_URL", "LITELLM_PROXY_URL", "LITELLM_PROXY_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    with pytest.raises(ValidationError):
        Settings()
