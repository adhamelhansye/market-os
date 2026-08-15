"""Application settings.

Required environment variables are validated at startup by pydantic-settings.
Missing required values abort boot with a clear error.
"""

import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ENVIRONMENTS = {"development", "test", "staging", "production"}

_META_VERSION_PATTERN = re.compile(r"^v\d+(\.\d+)?$")


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

    # Meta Marketing API (Facebook Login app). Read-only: the ONLY requested
    # permission is ads_read (no mutation capabilities). The Graph API
    # version is pinned exactly — there is no silent fallback to older
    # versions; bump META_GRAPH_API_VERSION deliberately when upgrading.
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = ""
    meta_graph_api_version: str = "v26.0"
    meta_scopes: str = "ads_read"

    # Meta sync windows. Initial sync is a bounded historical window (Meta
    # rejects time ranges over 37 months); incremental sync re-fetches a
    # short recent window that absorbs reporting latency, and upsert
    # idempotency makes the overlap safe to reprocess.
    meta_initial_sync_days: int = 90
    meta_incremental_lookback_days: int = 2

    # Analytics freshness: a provider whose facts stopped arriving this many
    # hours ago is reported stale by the metrics data-quality endpoint.
    metrics_stale_after_hours: int = 48

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

    @field_validator("meta_graph_api_version")
    @classmethod
    def validate_meta_api_version(cls, value: str) -> str:
        value = value.strip()
        if not _META_VERSION_PATTERN.match(value) or value == "v0":
            raise ValueError("META_GRAPH_API_VERSION must look like v26.0")
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