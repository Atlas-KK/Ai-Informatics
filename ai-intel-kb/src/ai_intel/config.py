"""Foundation configuration with local-only defaults and safe error messages."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MissingConfigurationError(RuntimeError):
    """Raised without ever embedding a secret value in the message."""

    def __init__(self, config_name: str) -> None:
        self.config_name = config_name
        super().__init__(f"Missing required configuration: {config_name}")


class Settings(BaseSettings):
    """Process settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI_INTEL_",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    host: Literal["127.0.0.1", "::1"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


def require_configured(config_name: str, value: str | None) -> str:
    """Return a configured value or raise an error containing only its setting name."""

    if value is None or not value.strip():
        raise MissingConfigurationError(config_name)
    return value
