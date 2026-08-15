"""Meta Ads adapter implementation (read-only).

Mapping model (Phase 2B):

- The adapter never mutates Meta: no campaign/ad-set/ad creation, no
  budget/bid changes, no creative uploads, no ads_management permission.
- One connection row per Meta ad account (multiple accounts per business).
  Connect ends in a `pending` connection holding the discovered account
  list; the user then explicitly selects which account(s) to ingest.
- Sync resources: ad_accounts (metadata), campaigns, ad_sets, ads
  (ad pages also emit their nested creative), insights (daily facts).
- Insights windows: initial = bounded historical window (config, ~90 days);
  incremental = recent window covering reporting latency, with a 1-day
  overlap re-fetched idempotently.
- Errors are classified to typed integration errors in meta/errors.py;
  credentials never appear in messages.

Meta webhooks are intentionally NOT supported in Phase 2B.
"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.modules.integrations.base.errors import (
    ProviderError,
    WebhookVerificationError,
)
from src.modules.integrations.base.protocol import IntegrationAdapter, ProviderCredentials
from src.modules.integrations.base.types import (
    CanonicalAdAccount,
    ProviderExchangeResult,
    SyncPage,
    WebhookResolution,
)
from src.modules.integrations.meta.client import MetaGraphClient, exchange_access_token
from src.modules.integrations.meta.constants import (
    INCREMENTAL_RESOURCES,
    INITIAL_RESOURCES,
    MAX_INSIGHTS_RANGE_DAYS,
    PROVIDER,
    RESOURCE_TYPES,
)
from src.modules.integrations.meta.mapper import (
    map_ad,
    map_ad_account,
    map_ad_set,
    map_campaign,
    map_creative,
    map_insight,
)

logger = get_logger(__name__)


def _account_id(account_ref: str) -> str:
    """Normalizes an account ref (act_123 or 123) to the numeric id."""
    value = (account_ref or "").strip().removeprefix("act_")
    if not value.isdigit():
        raise ProviderError("Meta ad account id is missing")
    return value


def _format_date(value: date) -> str:
    return value.isoformat()


class MetaAdapter(IntegrationAdapter):
    provider = PROVIDER
    resource_types = RESOURCE_TYPES
    initial_resources = INITIAL_RESOURCES
    incremental_resources = INCREMENTAL_RESOURCES

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._clients: dict[str, MetaGraphClient] = {}

    def _client(self, credentials: ProviderCredentials) -> MetaGraphClient:
        client = self._clients.get(credentials.access_token)
        if client is None:
            client = MetaGraphClient(
                api_version=self._settings.meta_graph_api_version,
                access_token=credentials.access_token,
            )
            self._clients[credentials.access_token] = client
        return client

    # -- OAuth connect --------------------------------------------------------

    def validate_connect_input(self, raw: str) -> str:
        # Meta takes no user-supplied input: nothing is ever used in
        # outbound requests, so there is no SSRF surface to open.
        return ""

    def build_authorize_url(self, account_ref: str, state: str) -> str:
        params = urlencode(
            {
                "client_id": self._settings.meta_app_id,
                "redirect_uri": self._settings.meta_redirect_uri,
                "state": state,
                "scope": self._settings.meta_scopes,
                "response_type": "code",
            }
        )
        version = self._settings.meta_graph_api_version
        return f"https://www.facebook.com/{version}/dialog/oauth?{params}"

    async def exchange_code(self, account_ref: str, code: str) -> ProviderExchangeResult:
        result = await exchange_access_token(
            api_version=self._settings.meta_graph_api_version,
            app_id=self._settings.meta_app_id,
            app_secret=self._settings.meta_app_secret,
            redirect_uri=self._settings.meta_redirect_uri,
            code=code,
        )
        scope = [s.strip() for s in self._settings.meta_scopes.split(",") if s.strip()]
        expires_at = None
        if result.expires_in:
            expires_at = datetime.now(UTC) + timedelta(seconds=result.expires_in)
        return ProviderExchangeResult(
            access_token=result.access_token, scope=scope, expires_at=expires_at
        )

    # -- webhooks (unsupported in Phase 2B) -----------------------------------

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        return False

    async def resolve_webhook(
        self, raw_body: bytes, headers: dict[str, str]
    ) -> WebhookResolution:
        raise WebhookVerificationError("Meta webhooks are not supported")

    # -- connection lifecycle --------------------------------------------------

    async def validate_connection(self, credentials: ProviderCredentials) -> dict:
        """Fetches the connected user; raises ProviderAuthError on bad token."""
        user = await self._client(credentials).fetch_user()
        return {"user_id": str(user.id), "name": user.name or ""}

    async def validate_ad_account(self, credentials: ProviderCredentials, external_id: str) -> dict:
        """Validates the token can read the given ad account and returns its
        metadata (single source of truth for currency/status/timezone)."""
        account = await self._client(credentials).fetch_ad_account(_account_id(external_id))
        canonical = map_ad_account(account)
        return {
            "name": canonical.name,
            "currency": canonical.currency,
            "status": canonical.status,
            "timezone": canonical.timezone,
            "timezone_offset_hours_utc": (
                str(canonical.timezone_offset_hours_utc)
                if canonical.timezone_offset_hours_utc is not None
                else None
            ),
        }

    async def disconnect(self, credentials: ProviderCredentials) -> None:
        """Best-effort provider-side token revocation; failures are ignored."""
        try:
            await self._client(credentials).revoke_token()
        except ProviderError as exc:
            logger.warning("meta disconnect: revocation failed: %s", exc.code)

    async def health_check(self, credentials: ProviderCredentials) -> bool:
        try:
            await self._client(credentials).fetch_user()
            return True
        except ProviderError:
            return False

    async def list_accounts(
        self, credentials: ProviderCredentials
    ) -> list[CanonicalAdAccount]:
        """Discovers all ad accounts the token can access (paginated)."""
        client = self._client(credentials)
        accounts: list[CanonicalAdAccount] = []
        after: str | None = None
        while True:
            items, next_after = await client.list_ad_accounts(after)
            for item in items:
                accounts.append(map_ad_account(item))
            if not next_after:
                break
            after = next_after
        return accounts

    # -- sync -----------------------------------------------------------------

    async def sync_page(
        self,
        credentials: ProviderCredentials,
        resource_type: str,
        cursor: str | None,
    ) -> SyncPage:
        if resource_type not in RESOURCE_TYPES:
            raise ProviderError(f"Unsupported resource type: {resource_type}")
        client = self._client(credentials)
        account = _account_id(credentials.shop_domain)

        if resource_type == "ad_accounts":
            account_meta = await client.fetch_ad_account(account)
            record = map_ad_account(account_meta)
            return SyncPage(records=[record], next_cursor=None)

        if resource_type == "campaigns":
            after = _decode_after(cursor)
            items, next_after = await client.list_campaigns(account, after)
            return SyncPage(
                records=[
                    replace(map_campaign(item), ad_account_external_id=account)
                    for item in items
                ],
                next_cursor=_encode_after(next_after),
            )

        if resource_type == "ad_sets":
            after = _decode_after(cursor)
            items, next_after = await client.list_ad_sets(account, after)
            return SyncPage(
                records=[
                    replace(map_ad_set(item), ad_account_external_id=account)
                    for item in items
                ],
                next_cursor=_encode_after(next_after),
            )

        if resource_type == "ads":
            after = _decode_after(cursor)
            items, next_after = await client.list_ads(account, after)
            records: list = []
            for item in items:
                creative = map_creative(item.creative) if item.creative else None
                if creative is not None:
                    records.append(creative)
                records.append(
                    replace(map_ad(item, creative), ad_account_external_id=account)
                )
            return SyncPage(records=records, next_cursor=_encode_after(next_after))

        # insights: cursor is an ISO date (coverage through, from SyncRun)
        # or a {"since","until","after"} continuation payload.
        settings = self._settings
        window = _resolve_window(cursor, settings)
        after = _decode_after(cursor)
        items, next_after = await client.list_insights(
            account, since=window["since"], until=window["until"], after=after
        )
        records = [
            replace(map_insight(item), ad_account_external_id=account) for item in items
        ]
        next_cursor: str | None = None
        if next_after or cursor is None or _is_date(cursor):
            # Carry the window forward so continuation pages and the
            # checkpoint (max record date) are consistent.
            payload = {"since": window["since"], "until": window["until"]}
            if next_after:
                payload["after"] = next_after
            next_cursor = json.dumps(payload)
        return SyncPage(records=records, next_cursor=next_cursor)


def _is_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _decode_after(cursor: str | None) -> str | None:
    if not cursor:
        return None
    if _is_date(cursor):
        return None
    try:
        payload = json.loads(cursor)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    after = payload.get("after")
    return str(after) if after else None


def _encode_after(after: str | None) -> str | None:
    if not after:
        return None
    return json.dumps({"after": after})


def _resolve_window(cursor: str | None, settings: Settings) -> dict[str, str]:
    """Determines the insights time window.

    - No cursor (first run): bounded initial window.
    - ISO date cursor (sync checkpoint coverage date): incremental window
      with 1 day of overlap, floored by the lookback (reporting latency).
    - {"since","until"} cursor: continuation within the same window.
    """
    today = datetime.now(UTC).date()
    lookback = timedelta(days=settings.meta_incremental_lookback_days)

    if cursor is not None and not isinstance(cursor, str):
        cursor = str(cursor)
    if cursor and _is_date(cursor):
        covered = datetime.strptime(cursor, "%Y-%m-%d").date()
        window_start = max(today - lookback, covered - timedelta(days=1))
        return {"since": _format_date(window_start), "until": _format_date(today)}

    if cursor:
        try:
            payload = json.loads(cursor)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict) and payload.get("since") and payload.get("until"):
            return {"since": str(payload["since"]), "until": str(payload["until"])}

    window_start = today - timedelta(days=settings.meta_initial_sync_days)
    if today - window_start > timedelta(days=MAX_INSIGHTS_RANGE_DAYS):
        window_start = today - timedelta(days=MAX_INSIGHTS_RANGE_DAYS)
    return {"since": _format_date(window_start), "until": _format_date(today)}