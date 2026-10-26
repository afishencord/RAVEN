from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def validate_secret(value: str) -> str:
    """Reject missing/known example values without including a secret in errors."""
    normalized = value.lower().replace("_", "-")
    if (
        len(value) < 32
        or value != value.strip()
        or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value)
        or any(marker in normalized for marker in ("change-me", "changeme", "replace-", "your-", "dev-flock", "placeholder"))
    ):
        raise ValueError("must be a private random secret of at least 32 characters, not an example value")
    return value


def validate_admin_password(value: str) -> str:
    # bcrypt only uses the first 72 bytes; never silently accept truncation.
    if not 16 <= len(value.encode("utf-8")) <= 72 or not value.strip() or "\x00" in value:
        raise ValueError("admin password must contain 16 to 72 UTF-8 bytes")
    if any(marker in value.lower() for marker in ("replace-this", "change-me", "changeme", "your-password")):
        raise ValueError("admin password must not be an example value")
    return value


class EnvironmentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )


class AgentSettings(EnvironmentSettings):
    """Agents must not receive control-plane JWT or internal dispatch secrets."""

    flock_server_url: str = "http://flock:8000/api/flock"
    flock_agent_state_path: str = "/data/flock-agent-state.json"
    flock_enrollment_token: str | None = Field(default=None, repr=False)
    flock_agent_name: str | None = None

    @field_validator("flock_enrollment_token", mode="before")
    @classmethod
    def optional_enrollment_secret(cls, value):
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise ValueError("enrollment secret must be a string")
        if len(value.encode("utf-8")) > 72:
            raise ValueError("enrollment secret must not exceed 72 UTF-8 bytes")
        return validate_secret(value)


class Settings(AgentSettings):
    app_name: str = "RAVEN"
    api_prefix: str = "/api"
    debug: bool = False
    database_url: str = "sqlite:///./raven.db"
    jwt_secret_key: str = Field(repr=False)
    # This app uses one shared secret to issue and verify access tokens. Do not
    # mix asymmetric key algorithms into that configuration or accept "none".
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = 60 * 12
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-4.1-mini"
    frontend_origin: str = "http://localhost:3000"
    monitor_poll_seconds: int = 5
    runner_poll_seconds: int = 5
    embedded_monitoring: bool = True
    flock_internal_token: str = Field(repr=False)
    flock_dispatch_timeout_seconds: int = 90
    flock_result_poll_seconds: int = 2
    ssh_known_hosts_path: str | None = None
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = Field(default=None, repr=False)

    @field_validator("jwt_secret_key", "flock_internal_token")
    @classmethod
    def private_secret(cls, value: str) -> str:
        return validate_secret(value)

    @field_validator("bootstrap_admin_username")
    @classmethod
    def bootstrap_username(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value != value.strip() or len(value) > 64):
            raise ValueError("bootstrap admin username must contain 1 to 64 characters without surrounding whitespace")
        return value

    @field_validator("bootstrap_admin_password")
    @classmethod
    def bootstrap_password(cls, value: str | None) -> str | None:
        return None if value is None else validate_admin_password(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
