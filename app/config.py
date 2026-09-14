"""Environment-backed application settings."""

# Author: Sonit — configuration and environment variable handling.

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration supplied by the environment or a local .env file."""

    github_token: str = ""
    github_owner: str = ""
    github_repo: str = ""
    webhook_secret: str = ""
    port: int = 8000
    service_base_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
