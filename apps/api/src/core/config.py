"""Application settings.

Required environment variables are validated at startup by pydantic-settings.
Missing required values abort boot with a clear error.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ENVIRONMENTS = {"development", "test", "staging", "production"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "development"
    api_url: str = "http://localhost:8000"
    web_url: str = "http://localhost:3000"

    database_url: str
    redis_url: str

    jwt_secret: str
    jwt_refresh_secret: str
    encryption_key: str

    cors_origins: str = ""

    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    refresh_cookie_name: str = "mos_refresh"
    refresh_cookie_secure: bool | None = None

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        if value not in APP_ENVIRONMENTS:
            raise ValueError(f"APP_ENV must be one of {sorted(APP_ENVIRONMENTS)}")
        return value

    @field_validator("jwt_secret", "jwt_refresh_secret")
    @classmethod
    def validate_secret_length(cls, value: str) -> str:
        if len(value) < 16:
            raise ValueError("JWT secrets must be at least 16 characters")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return origins or [self.web_url]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cookie_secure(self) -> bool:
        if self.refresh_cookie_secure is not None:
            return self.refresh_cookie_secure
        return self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()