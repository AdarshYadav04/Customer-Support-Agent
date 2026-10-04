from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()  # read .env file if present

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Required: set in .env (the app refuses to start without them) ---
    database_url: str
    litellm_proxy_url: str
    litellm_proxy_key: str

    # --- Optional ---
    store_name: str = "ShopEase"
    log_level: str = "INFO"
    auto_create_tables: bool = False  # dev convenience; use migrations in production

    # Model names exactly as exposed by your LiteLLM proxy
    agent_model: str = "gpt-4.1"
    guardrail_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = 60.0

    max_tool_iterations: int = 6
    history_limit: int = 10
    return_window_days: int = 30

    # Optional service-to-service API key (disabled when empty)
    service_api_key: str | None = None

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg_driver(cls, value: str) -> str:
        """Accept plain postgres:// or postgresql:// URLs and switch them to asyncpg."""
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix):]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
