"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/options_edge"

    # External API keys
    POLYGON_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    BENZINGA_API_KEY: str = ""

    # Gmail integration
    GMAIL_CREDENTIALS_PATH: str = "credentials/gmail.json"

    # Application
    APP_ENV: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def sync_database_url(self) -> str:
        """Return a synchronous database URL for Alembic migrations."""
        return self.DATABASE_URL.replace("asyncpg", "psycopg2")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
