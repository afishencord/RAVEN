from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RAVEN"
    api_prefix: str = "/api"
    debug: bool = True
    database_url: str = "sqlite:///./raven.db"
    jwt_secret_key: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    frontend_origin: str = "http://localhost:3000"
    monitor_poll_seconds: int = 5
    runner_poll_seconds: int = 5
    embedded_monitoring: bool = True
    flock_server_url: str = "http://flock:8000/api/flock"
    flock_internal_token: str = "dev-flock-internal-token"
    flock_dispatch_timeout_seconds: int = 90
    flock_result_poll_seconds: int = 2
    flock_agent_state_path: str = "/data/flock-agent-state.json"
    flock_enrollment_token: str | None = None
    flock_agent_name: str | None = None

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
