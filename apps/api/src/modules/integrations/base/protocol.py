"""Provider-agnostic integration adapter interface.

The core integration service depends ONLY on this interface. Providers
(Shopify today, Meta/GA4/TikTok later) implement it inside their own
directory; no provider concept ever leaks into the core service.

Adapters never touch the database: the service decrypts credentials and
hands the adapter a `ProviderCredentials` value (in memory, for the
duration of the request only), and the service persists whatever canonical
data the adapter returns.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from src.modules.integrations.base.types import (
    ProviderExchangeResult,
    SyncPage,
    WebhookResolution,
)


@dataclass(frozen=True)
class ProviderCredentials:
    """Decrypted provider credentials, valid only for the current call."""

    shop_domain: str
    access_token: str
    expires_at: datetime | None = None


@runtime_checkable
class IntegrationAdapter(Protocol):
    """Interface implemented by every provider adapter."""

    provider: str

    resource_types: tuple[str, ...]

    def validate_connect_input(self, raw: str) -> str:
        """Validates and normalizes the user-supplied connect input.

        Used to prevent SSRF: the returned value is the only thing ever used
        in outbound requests. Raises IntegrationError on invalid input.
        """
        ...

    def build_authorize_url(self, shop_domain: str, state: str) -> str:
        """Builds the OAuth authorize URL (provider-side, config-based).

        `shop_domain` is the value returned by validate_connect_input and
        `state` the server-generated single-use token. The redirect_uri
        always comes from configuration — never from the client.
        """
        ...

    async def exchange_code(self, shop_domain: str, code: str) -> ProviderExchangeResult:
        """Exchanges the OAuth authorization code for tokens."""
        ...

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        """Verifies a webhook signature against the raw body.

        The raw body must never be parsed/normalized before verification.
        """
        ...

    async def validate_connection(self, credentials: ProviderCredentials) -> None:
        """Confirms the credentials work (e.g. fetches the shop)."""
        ...

    async def disconnect(self, credentials: ProviderCredentials) -> None:
        """Best-effort provider-side revocation. Failures are ignored."""
        ...

    async def health_check(self, credentials: ProviderCredentials) -> bool:
        """Checks the connection is currently usable."""
        ...

    async def sync_page(
        self,
        credentials: ProviderCredentials,
        resource_type: str,
        cursor: str | None,
    ) -> SyncPage:
        """Fetches one page of canonical records for `resource_type`.

        `cursor` is opaque to the caller (provider-specific pagination or
        incremental marker). Returns canonical records and the next cursor
        (None when the last page was reached).
        """
        ...

    async def resolve_webhook(
        self, raw_body: bytes, headers: dict[str, str]
    ) -> WebhookResolution:
        """Converts a verified webhook into canonical records.

        Returns handled=False for topics this provider does not support.
        """
        ...
