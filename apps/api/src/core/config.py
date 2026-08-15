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
    encryption_key_version: int = 1

    # Shopify OAuth (custom app). Shopify API version is configurable so the
    # deployment can track its own upgrade schedule.
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_redirect_uri: str = ""
    shopify_api_version: str = "2026-04"
    shopify_scopes: str = "read_products,read_orders,read_customers,read_inventory,read_locations"

    # OAuth state: how long a connect state token stays valid (single-use).
    oauth_state_ttl_seconds: int = 600

    # Callback session cookie: binds the browser tab that started the OAuth
    # connect to the identity of the authenticated user who initiated it, so
    # the browser-redirect callback can reject a state used by the wrong user.
    callback_session_cookie_name: str = "mos_cb_session"
    callback_session_ttl_seconds: int = 900

    # Origin the OAuth callback redirects to after completing the exchange.
    # NEVER user-supplied: only this configured value is used.
    frontend_base_url: str = "http://localhost:3000"

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

    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key_length(cls, value: str) -> str:
        # The AES-GCM key is derived from this value via HKDF; short values
        # would make the derivation trivially brute-forceable.
        if len(value) < 16:
            raise ValueError("ENCRYPTION_KEY must be at least 16 characters")
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