"""Integration core service.

Orchestration only: connect flow, sync runs, webhook processing and
disconnect. All provider specifics live behind the IntegrationAdapter
protocol; all record persistence lives in `persistence`.

Security invariants enforced here:
- business_id is resolved from the validated OAuth state (server-side),
  never from untrusted callback query parameters;
- the callback session cookie binds the browser to the user who started
  the connect, so a state cannot be completed by another user;
- credentials are encrypted at rest, decrypted only for the duration of a
  provider call, and never logged or returned;
- every sync/webhook write is scoped to the connection's business_id.
"""

import base64
import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.exceptions import ConflictError, NotFoundError
from src.core.logging import get_logger
from src.core.tenancy import can_access_business, resolve_tenant
from src.db.models import (
    Ad,
    AdAccount,
    AdInsight,
    AdSet,
    Business,
    Campaign,
    Creative,
    Customer,
    IntegrationConnection,
    IntegrationCredential,
    InventorySnapshot,
    Order,
    Product,
    SyncRun,
    WebhookEvent,
)
from src.modules.integrations.base.errors import (
    ConnectionStateError,
    IntegrationError,
    IntegrationNotFoundError,
    OAuthStateExpiredError,
    ProviderAuthError,
    ProviderError,
)
from src.modules.integrations.base.protocol import IntegrationAdapter, ProviderCredentials
from src.modules.integrations.base.types import (
    CanonicalAd,
    CanonicalAdAccount,
    CanonicalAdInsight,
    CanonicalAdSet,
    CanonicalCampaign,
    CanonicalCreative,
    CanonicalCustomer,
    CanonicalInventory,
    CanonicalOrder,
    CanonicalProduct,
)
from src.modules.integrations.callback_session import CallbackSessionService
from src.modules.integrations.credentials import OAuthStateService, TokenCipher
from src.modules.integrations.jobs import (
    enqueue_incremental_sync,
    enqueue_initial_sync,
    enqueue_meta_initial_sync,
)
from src.modules.integrations.persistence import (
    upsert_ad,
    upsert_ad_account,
    upsert_ad_insight,
    upsert_ad_set,
    upsert_campaign,
    upsert_creative,
    upsert_customer,
    upsert_order,
    upsert_product,
    write_inventory_snapshot,
)
from src.modules.integrations.registry import get_registry

logger = get_logger(__name__)

INITIAL_RESOURCES = ("products", "orders", "customers", "inventory")
INCREMENTAL_RESOURCES = ("orders", "products", "customers")
ALLOWED_LOCALES = ("en", "ar")

WEBHOOK_PAYLOAD_KEY = "webhook:payload:{}"
WEBHOOK_META_KEY = "webhook:meta:{}"


def _now() -> datetime:
    return datetime.now(UTC)


# -- connection lookups -------------------------------------------------------


async def get_connection(
    session: AsyncSession, business_id, connection_id
) -> IntegrationConnection:
    try:
        parsed = uuid.UUID(str(connection_id))
    except ValueError:
        raise IntegrationNotFoundError("Integration not found") from None
    connection = await session.get(IntegrationConnection, parsed)
    if connection is None or connection.business_id != business_id:
        raise IntegrationNotFoundError("Integration not found")
    return connection


async def get_connection_for_provider(
    session: AsyncSession, business_id, provider: str
) -> IntegrationConnection | None:
    return await session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == provider,
        )
    )


async def list_connections(session: AsyncSession, business_id) -> list[IntegrationConnection]:
    return list(
        await session.scalars(
            select(IntegrationConnection)
            .where(IntegrationConnection.business_id == business_id)
            .order_by(IntegrationConnection.created_at)
        )
    )


async def _decrypt_credentials(
    session: AsyncSession, settings: Settings, connection: IntegrationConnection
) -> ProviderCredentials:
    """Decrypts the stored token for the duration of the provider call."""
    credential = await session.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.connection_id == connection.id
        )
    )
    if credential is None:
        raise ConnectionStateError("Integration credentials are missing; reconnect required")
    cipher = TokenCipher.from_settings(settings)
    try:
        access_token = cipher.decrypt(credential.access_token_encrypted)
    except ValueError:
        raise ConnectionStateError("Integration credentials cannot be decrypted") from None
    return ProviderCredentials(
        shop_domain=connection.external_account_id or "",
        access_token=access_token,
        expires_at=credential.expires_at,
    )


# -- OAuth connect ------------------------------------------------------------


async def start_shopify_connect(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    *,
    user_id,
    business_id,
    shop_domain_raw: str,
    locale: str,
) -> tuple[str, str]:
    """Validates the shop, reserves a pending connection, issues the OAuth
    state AND the callback session cookie token. Returns (auth_url,
    callback_session_token)."""
    if locale not in ALLOWED_LOCALES:
        raise IntegrationError("Unsupported locale")
    adapter = _adapter("shopify")
    shop_domain = adapter.validate_connect_input(shop_domain_raw)

    connection = await get_connection_for_provider(session, business_id, "shopify")
    if connection is not None:
        if connection.status == "connected":
            raise ConflictError("Shopify is already connected to this business")
        connection.status = "pending"
        connection.external_account_id = shop_domain
        await session.commit()
    else:
        connection = IntegrationConnection(
            business_id=business_id,
            provider="shopify",
            status="pending",
            external_account_id=shop_domain,
        )
        session.add(connection)
        try:
            await session.commit()
        except IntegrityError:
            # Concurrent connect for the same business: reuse the winner.
            await session.rollback()
            connection = await get_connection_for_provider(session, business_id, "shopify")
            if connection is None or connection.status == "connected":
                raise ConflictError("Shopify is already connected to this business") from None

    state = await OAuthStateService(redis, settings).create(
        user_id=user_id, business_id=business_id, locale=locale
    )
    session_token = await CallbackSessionService(redis, settings).create(user_id=user_id)
    auth_url = adapter.build_authorize_url(shop_domain, state)
    logger.info("shopify connect started for business (business_id=%s)", business_id)
    return auth_url, session_token


async def _upsert_credential(
    session: AsyncSession,
    settings: Settings,
    connection: IntegrationConnection,
    access_token: str | None,
    expires_at: datetime | None,
    refresh_token: str | None,
) -> None:
    cipher = TokenCipher.from_settings(settings)
    credential = await session.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.connection_id == connection.id
        )
    )
    if credential is None:
        credential = IntegrationCredential(connection_id=connection.id)
        session.add(credential)
    if access_token is not None:
        credential.access_token_encrypted = cipher.encrypt(access_token)
        credential.key_version = settings.encryption_key_version
    if refresh_token is not None:
        credential.refresh_token_encrypted = cipher.encrypt(refresh_token)
    credential.expires_at = expires_at


async def handle_shopify_callback(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    *,
    callback_session_token: str | None,
    code: str | None,
    state: str | None,
) -> dict:
    """Completes the OAuth exchange. Returns {'business_id', 'locale'} —
    the caller turns it into a browser redirect.

    Rejection paths (none leak anything to the browser):
    - callback session cookie missing/unbound/expired: the state's user
      cannot be established, so the state is never consumed;
    - OAuth state missing/expired/reused/mismatched (consumed atomically);
    - the state's user no longer belongs to the business's organization.
    """
    user_id = await CallbackSessionService(redis, settings).resolve(callback_session_token)
    if user_id is None:
        raise OAuthStateExpiredError("OAuth callback session is invalid or expired")
    if not code or not state:
        raise OAuthStateExpiredError("OAuth callback is missing required parameters")

    state_payload = await OAuthStateService(redis, settings).consume(state, user_id=user_id)
    business_id = state_payload["business_id"]
    locale = state_payload["locale"] if state_payload["locale"] in ALLOWED_LOCALES else "en"

    # Re-validate business access server-side: membership may have been
    # revoked between state creation and the callback.
    business = await session.get(Business, business_id)
    if business is None:
        raise OAuthStateExpiredError("OAuth callback is invalid")
    tenant = await resolve_tenant(session, user_id, business.organization_id)
    if await can_access_business(session, tenant.organization_id, business_id) is None:
        raise OAuthStateExpiredError("OAuth callback is invalid")

    adapter = _adapter("shopify")
    connection = await get_connection_for_provider(session, business_id, "shopify")
    if connection is None or connection.status != "pending":
        raise ConnectionStateError("No pending Shopify connection for this business")

    exchange = await adapter.exchange_code(connection.external_account_id or "", code)
    credentials = ProviderCredentials(
        shop_domain=connection.external_account_id or "",
        access_token=exchange.access_token,
        expires_at=exchange.expires_at,
    )
    shop_info = await adapter.validate_connection(credentials)

    await _upsert_credential(
        session, settings, connection, exchange.access_token, exchange.expires_at, None
    )
    connection.status = "connected"
    connection.external_account_id = (
        shop_info.get("myshopify_domain") or connection.external_account_id
    )
    connection.external_account_name = shop_info.get("name")
    connection.scopes = exchange.scope
    connection.provider_metadata = {"currency": shop_info.get("currency")}
    connection.connected_at = _now()
    try:
        await session.commit()
    except IntegrityError:
        # Same shop connected in another business concurrently: treat as a
        # configuration error rather than silently sharing data.
        await session.rollback()
        raise ConflictError("This shop is already connected to another business") from None

    await enqueue_initial_sync(str(connection.id))
    logger.info(
        "shopify connected for business (business_id=%s, shop=%s)",
        business_id,
        connection.external_account_id,
    )
    return {"business_id": str(business_id), "locale": locale, "success": True}


# -- Meta (Facebook) connect --------------------------------------------------


async def get_pending_meta_connection(
    session: AsyncSession, business_id
) -> IntegrationConnection | None:
    """The most recent pending Meta connection awaiting account selection."""
    return await session.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == "meta",
            IntegrationConnection.status == "pending",
            IntegrationConnection.external_account_id.is_(None),
        )
        .order_by(IntegrationConnection.created_at.desc())
        .limit(1)
    )


async def get_meta_connection_by_account(
    session: AsyncSession, business_id, account_ref: str
) -> IntegrationConnection | None:
    return await session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == "meta",
            IntegrationConnection.external_account_id == account_ref,
        )
    )


async def start_meta_connect(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    *,
    user_id,
    business_id,
    locale: str,
) -> tuple[str, str]:
    """Begins the Meta OAuth dance. Meta needs no user input: the connection
    stays `pending` until the user explicitly selects an account, so one
    OAuth completion can cover several ad accounts."""
    if locale not in ALLOWED_LOCALES:
        raise IntegrationError("Unsupported locale")

    connection = await get_pending_meta_connection(session, business_id)
    if connection is None:
        connection = IntegrationConnection(
            business_id=business_id, provider="meta", status="pending"
        )
        session.add(connection)
        await session.commit()
    else:
        # Re-connect after an abandoned flow: drop any stale token and
        # discovered accounts so the new authorization is authoritative.
        await session.execute(
            delete(IntegrationCredential).where(
                IntegrationCredential.connection_id == connection.id
            )
        )
        connection.provider_metadata = None
        connection.external_account_name = None
        connection.scopes = []
        await session.commit()

    state = await OAuthStateService(redis, settings).create(
        user_id=user_id, business_id=business_id, locale=locale, provider="meta"
    )
    session_token = await CallbackSessionService(redis, settings).create(user_id=user_id)
    auth_url = _adapter("meta").build_authorize_url("", state)
    logger.info("meta connect started for business (business_id=%s)", business_id)
    return auth_url, session_token


async def handle_meta_callback(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    *,
    callback_session_token: str | None,
    code: str | None,
    state: str | None,
) -> dict:
    """Completes the Meta OAuth exchange: stores the token and the list of
    accessible ad accounts on the pending connection. NO account is
    auto-connected — the user picks one explicitly (POST /accounts/select),
    which is what triggers the initial sync."""
    user_id = await CallbackSessionService(redis, settings).resolve(callback_session_token)
    if user_id is None:
        raise OAuthStateExpiredError("OAuth callback session is invalid or expired")
    if not code or not state:
        raise OAuthStateExpiredError("OAuth callback is missing required parameters")

    state_payload = await OAuthStateService(redis, settings).consume(
        state, user_id=user_id, provider="meta"
    )
    business_id = state_payload["business_id"]
    locale = state_payload["locale"] if state_payload["locale"] in ALLOWED_LOCALES else "en"

    business = await session.get(Business, business_id)
    if business is None:
        raise OAuthStateExpiredError("OAuth callback is invalid")
    tenant = await resolve_tenant(session, user_id, business.organization_id)
    if await can_access_business(session, tenant.organization_id, business_id) is None:
        raise OAuthStateExpiredError("OAuth callback is invalid")

    adapter = _adapter("meta")
    connection = await get_pending_meta_connection(session, business_id)
    if connection is None:
        raise ConnectionStateError("No pending Meta connection for this business")

    exchange = await adapter.exchange_code("", code)
    credentials = ProviderCredentials(
        shop_domain="",
        access_token=exchange.access_token,
        expires_at=exchange.expires_at,
    )
    user_info = await adapter.validate_connection(credentials)
    accounts = await adapter.list_accounts(credentials)

    await _upsert_credential(
        session, settings, connection, exchange.access_token, exchange.expires_at, None
    )
    connection.scopes = exchange.scope
    connection.external_account_name = user_info.get("name")
    connection.provider_metadata = {
        "user_id": user_info.get("user_id"),
        "version": 1,
        "accounts": [
            {
                "external_account_id": account.external_id,
                "name": account.name,
                "currency": account.currency,
                "status": account.status,
                "timezone": account.timezone,
            }
            for account in accounts
        ],
    }
    await session.commit()
    logger.info("meta oauth completed for business (business_id=%s)", business_id)
    return {"business_id": str(business_id), "locale": locale, "success": True}


async def meta_accounts_view(session: AsyncSession, business_id) -> dict:
    """Discovered (not yet selected) accounts for the pending connection."""
    connection = await get_pending_meta_connection(session, business_id)
    if connection is None:
        return {"connection_id": None, "accounts": []}
    accounts = (connection.provider_metadata or {}).get("accounts") or []
    return {"connection_id": str(connection.id), "accounts": accounts}


async def select_meta_account(
    session: AsyncSession,
    settings: Settings,
    *,
    business_id,
    external_account_id: str,
) -> IntegrationConnection:
    """Connects ONE explicitly chosen ad account (never an implicit bulk
    connect) and triggers its initial sync. The account must come from the
    server-side discovered list — anything else is rejected."""
    connection = await get_pending_meta_connection(session, business_id)
    if connection is None:
        raise ConnectionStateError("No pending Meta connection for this business")
    discovered = (connection.provider_metadata or {}).get("accounts") or []
    selected = next(
        (a for a in discovered if a.get("external_account_id") == external_account_id),
        None,
    )
    if selected is None:
        raise IntegrationError("This Meta ad account was not part of the authorization")

    credentials = await _decrypt_credentials(session, settings, connection)
    account_info = await _adapter("meta").validate_ad_account(
        credentials, external_account_id
    )

    account_ref = f"act_{external_account_id}"
    connection.external_account_id = account_ref
    connection.external_account_name = account_info.get("name") or selected.get("name")
    metadata = dict(connection.provider_metadata or {})
    metadata["currency"] = account_info.get("currency")
    connection.provider_metadata = metadata
    connection.status = "connected"
    connection.connected_at = _now()

    existing = await get_meta_connection_by_account(session, business_id, account_ref)
    if existing is not None and existing.id != connection.id:
        raise ConnectionStateError("This Meta ad account is already connected to this business")

    await upsert_ad_account(
        session,
        business_id,
        CanonicalAdAccount(
            external_id=external_account_id,
            name=account_info.get("name") or selected.get("name"),
            currency=account_info.get("currency") or "USD",
            timezone=account_info.get("timezone") or selected.get("timezone"),
            timezone_offset_hours_utc=(
                Decimal(account_info["timezone_offset_hours_utc"])
                if account_info.get("timezone_offset_hours_utc")
                else None
            ),
            status=account_info.get("status") or "UNKNOWN",
        ),
    )
    try:
        await session.commit()
    except IntegrityError:
        # Same ad account connected in this or another business: never
        # share a provider account silently.
        await session.rollback()
        raise ConflictError(
            "This Meta ad account is already connected to another business"
        ) from None

    await enqueue_meta_initial_sync(str(connection.id))
    logger.info(
        "meta account connected for business (business_id=%s, account=%s)",
        business_id,
        account_ref,
    )
    return connection


# -- sync ---------------------------------------------------------------------


async def request_sync(
    session: AsyncSession, business_id, connection_id, resources: Sequence[str] | None
) -> list[str]:
    connection = await get_connection(session, business_id, connection_id)
    if connection.status != "connected":
        raise ConnectionStateError("Integration is not connected")
    adapter = _adapter(connection.provider)
    if resources is not None:
        unknown = [r for r in resources if r not in adapter.resource_types]
        if unknown:
            raise IntegrationError("Unsupported sync resources")
    if resources is None:
        # Provider-specific defaults: Shopify ingests commerce resources;
        # Meta ingests its own hierarchy + daily insights. Adapters may
        # declare their own sets; Shopify keeps the Phase 2A defaults.
        if connection.last_sync_at is None:
            chosen = list(
                getattr(adapter, "initial_resources", None) or INITIAL_RESOURCES
            )
        else:
            chosen = list(
                getattr(adapter, "incremental_resources", None) or INCREMENTAL_RESOURCES
            )
    else:
        chosen = list(resources)
    await enqueue_incremental_sync(str(connection.id), chosen)
    return chosen


async def run_sync(
    session: AsyncSession,
    *,
    connection_id,
    resources: Sequence[str],
    initial: bool,
) -> dict[str, int]:
    """Runs one sync per resource, recording SyncRun rows. Idempotent and
    resumable: completed runs store the incremental watermark (cursor);
    failures leave the previous watermark intact."""
    try:
        connection_id_parsed = uuid.UUID(str(connection_id))
    except ValueError:
        raise NotFoundError("Integration not found") from None
    connection = await session.get(IntegrationConnection, connection_id_parsed)
    if connection is None:
        raise NotFoundError("Integration not found")
    if connection.status != "connected":
        raise ConnectionStateError("Integration is not connected")
    adapter = _adapter(connection.provider)
    settings = get_settings()
    credentials = await _decrypt_credentials(session, settings, connection)
    business_id = connection.business_id
    currency_fallback = (connection.provider_metadata or {}).get("currency")

    processed_total: dict[str, int] = {}
    for resource in resources:
        if resource not in adapter.resource_types:
            raise IntegrationError(f"Unsupported sync resource: {resource}")
        run = SyncRun(connection_id=connection.id, resource_type=resource)
        session.add(run)
        await session.commit()

        previous_cursor = (
            None
            if initial
            else await _previous_cursor(session, connection.id, resource)
        )
        cursor = previous_cursor
        processed = 0
        skipped = 0
        watermark = None
        try:
            while True:
                page = await adapter.sync_page(credentials, resource, cursor)
                for record in page.records:
                    try:
                        await _persist_with_retry(
                            session, business_id, record, currency_fallback=currency_fallback
                        )
                        await session.commit()
                        processed += 1
                    except (ValueError, TypeError, IntegrityError):
                        # Unresolvable record (e.g. provider data violating
                        # constraints): skip it, never abort the run.
                        await session.rollback()
                        skipped += 1
                record_watermark = _watermark(page.records)
                if record_watermark is not None:
                    watermark = record_watermark if watermark is None else max(
                        watermark, record_watermark
                    )
                if not page.next_cursor:
                    break
                cursor = page.next_cursor
            run.records_processed = processed
            run.status = "partial" if skipped else "success"
            run.cursor = watermark or previous_cursor
            run.error_summary = (
                f"{skipped} record(s) skipped due to malformed provider data"
                if skipped
                else None
            )
            run.finished_at = _now()
            await session.commit()
        except (ProviderAuthError, ProviderError):
            run.status = "failed"
            run.finished_at = _now()
            await session.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("sync failed for resource (resource=%s)", resource)
            run.status = "failed"
            run.error_summary = str(exc)[:500]
            run.finished_at = _now()
            await session.commit()
            raise
        processed_total[resource] = processed

    connection.last_sync_at = _now()
    await session.commit()
    return processed_total


async def _previous_cursor(session: AsyncSession, connection_id, resource: str) -> str | None:
    """Watermark from the latest COMPLETED run of this resource (failed runs
    must not advance the cursor: their data is re-fetched on the next run,
    idempotently)."""
    return await session.scalar(
        select(SyncRun.cursor)
        .where(
            SyncRun.connection_id == connection_id,
            SyncRun.resource_type == resource,
            SyncRun.status.in_(("success", "partial")),
        )
        .order_by(SyncRun.started_at.desc())
        .limit(1)
    )


def _watermark(records) -> str | None:
    """Incremental watermark: the newest record update time in a page.

    Records without an `updated_at` fall back to their `date` (Meta daily
    insights): the watermark is then the latest covered day, which bounds
    the next incremental window (with a 1-day overlap for latency).
    """
    best: datetime | None = None
    best_date: date | None = None
    for record in records:
        updated_at = getattr(record, "updated_at", None)
        if updated_at is not None:
            if best is None or updated_at > best:
                best = updated_at
            continue
        fact_date = getattr(record, "date", None)
        if hasattr(fact_date, "isoformat") and (
            best_date is None or fact_date > best_date
        ):
            best_date = fact_date
    if best is not None:
        return best.isoformat()
    return best_date.isoformat() if best_date else None


async def _persist_with_retry(
    session: AsyncSession,
    business_id,
    record,
    *,
    currency_fallback: str | None,
) -> None:
    """Persists one record; on constraint races (two writers upserting the
    same row concurrently) rolls back and replays once."""
    try:
        await _persist_record(
            session, business_id, record, currency_fallback=currency_fallback
        )
    except (IntegrityError, ValueError, TypeError):
        await session.rollback()
        await _persist_record(
            session, business_id, record, currency_fallback=currency_fallback
        )


async def _persist_record(
    session: AsyncSession,
    business_id,
    record,
    *,
    currency_fallback: str | None,
) -> None:
    if isinstance(record, CanonicalProduct):
        await upsert_product(
            session, business_id, record, currency_fallback=currency_fallback
        )
    elif isinstance(record, CanonicalOrder):
        await upsert_order(
            session, business_id, "shopify", record, currency_fallback=currency_fallback
        )
    elif isinstance(record, CanonicalCustomer):
        await upsert_customer(session, business_id, record)
    elif isinstance(record, CanonicalInventory):
        await write_inventory_snapshot(session, business_id, record)
    elif isinstance(record, CanonicalAdAccount):
        await upsert_ad_account(session, business_id, record)
    elif isinstance(record, CanonicalCampaign):
        await upsert_campaign(session, business_id, record)
    elif isinstance(record, CanonicalAdSet):
        await upsert_ad_set(session, business_id, record)
    elif isinstance(record, CanonicalCreative):
        await upsert_creative(session, business_id, record)
    elif isinstance(record, CanonicalAd):
        await upsert_ad(session, business_id, record)
    elif isinstance(record, CanonicalAdInsight):
        await upsert_ad_insight(session, business_id, record)
    else:  # pragma: no cover - protocol guarantees the canonical types
        raise TypeError(f"Unknown canonical record type: {type(record).__name__}")


# -- webhooks -----------------------------------------------------------------


async def record_webhook_event(
    session: AsyncSession, *, provider: str, external_event_id: str | None,
    raw_body: bytes,
) -> WebhookEvent | None:
    """Persists the webhook event with a content hash for idempotency.
    Returns None when the event was already recorded (duplicate)."""
    event = WebhookEvent(
        provider=provider,
        external_event_id=external_event_id,
        payload_hash=hashlib.sha256(raw_body).hexdigest(),
        status="received",
    )
    session.add(event)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    return event


async def process_webhook_event(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    *,
    event_id,
) -> None:
    """Claims and processes one webhook event. The worker must never process
    the same event twice: claiming flips received -> processing atomically."""
    try:
        event_id_parsed = uuid.UUID(str(event_id))
    except ValueError:
        return
    claimed = await session.execute(
        update(WebhookEvent)
        .where(WebhookEvent.id == event_id_parsed, WebhookEvent.status == "received")
        .values(status="processing")
    )
    if claimed.rowcount == 0:
        return
    await session.commit()

    event = await session.get(WebhookEvent, event_id_parsed)
    meta_raw = await redis.getdel(WEBHOOK_META_KEY.format(event_id))
    payload_b64 = await redis.getdel(WEBHOOK_PAYLOAD_KEY.format(event_id))
    if payload_b64 is None or meta_raw is None:
        await _finish_webhook(session, event, "failed", "webhook payload expired")
        return
    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError):
        await _finish_webhook(session, event, "failed", "webhook payload invalid")
        return
    try:
        meta = json.loads(meta_raw)
    except (ValueError, TypeError):
        await _finish_webhook(session, event, "failed", "webhook metadata invalid")
        return

    shop_domain = str(meta.get("shop_domain") or "")
    connection = await session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.provider == event.provider,
            IntegrationConnection.external_account_id == shop_domain,
            IntegrationConnection.status == "connected",
        )
    )
    if connection is None:
        await _finish_webhook(session, event, "ignored", "no connected integration for shop")
        return

    adapter = _adapter(event.provider)
    headers = {
        "x-shopify-topic": str(meta.get("topic") or ""),
        "x-shopify-hmac-sha256": str(meta.get("signature") or ""),
    }
    try:
        resolution = await adapter.resolve_webhook(payload, headers)
    except ProviderError:
        await _finish_webhook(session, event, "failed", "provider rejected webhook")
        raise
    if not resolution.handled:
        await _finish_webhook(session, event, "ignored", None)
        return

    currency_fallback = (connection.provider_metadata or {}).get("currency")
    failed_records = 0
    for record in resolution.records:
        try:
            await _persist_with_retry(
                session, connection.business_id, record, currency_fallback=currency_fallback
            )
            await session.commit()
        except (ValueError, TypeError, IntegrityError):
            await session.rollback()
            failed_records += 1
    await _finish_webhook(
        session,
        event,
        "processed",
        f"{failed_records} record(s) failed to persist" if failed_records else None,
    )


async def _finish_webhook(
    session: AsyncSession, event: WebhookEvent, status: str, error_summary: str | None
) -> None:
    event.status = status
    event.error_summary = error_summary
    event.processed_at = _now()
    await session.commit()


# -- disconnect ---------------------------------------------------------------


async def mark_meta_reconnect_required(session: AsyncSession, connection_id) -> None:
    """Flips a Meta connection to `error` after the provider rejected its
    token: retrying would burn rate limits, so the connection stays dead
    until the user re-authorizes."""
    try:
        connection_id_parsed = uuid.UUID(str(connection_id))
    except ValueError:
        return
    connection = await session.get(IntegrationConnection, connection_id_parsed)
    if connection is None or connection.provider != "meta":
        return
    metadata = dict(connection.provider_metadata or {})
    metadata["auth_error"] = True
    connection.provider_metadata = metadata
    connection.status = "error"
    await session.commit()


async def disconnect_connection(
    session: AsyncSession, settings: Settings, business_id, connection_id
) -> IntegrationConnection:
    connection = await get_connection(session, business_id, connection_id)
    if connection.status == "connected":
        try:
            credentials = await _decrypt_credentials(session, settings, connection)
            await _adapter(connection.provider).disconnect(credentials)
        except (ProviderError, ConnectionStateError):
            pass  # best effort; the local disconnect still proceeds
    await session.execute(
        delete(IntegrationCredential).where(
            IntegrationCredential.connection_id == connection.id
        )
    )
    if connection.provider == "meta":
        # The account hierarchy cascades from ad_accounts; orphaned
        # creatives (not referenced by any remaining ad) are removed too.
        ad_account = await session.scalar(
            select(AdAccount.id).where(
                AdAccount.integration_connection_id == connection.id
            )
        )
        if ad_account is not None:
            await session.execute(
                delete(AdInsight).where(AdInsight.ad_account_id == ad_account)
            )
            await session.execute(delete(Ad).where(Ad.ad_account_id == ad_account))
            await session.execute(delete(AdSet).where(AdSet.ad_account_id == ad_account))
            await session.execute(
                delete(Campaign).where(Campaign.ad_account_id == ad_account)
            )
            await session.execute(delete(AdAccount).where(AdAccount.id == ad_account))
            await session.execute(
                delete(Creative)
                .where(
                    Creative.business_id == business_id,
                    Creative.provider == "meta",
                )
                .where(
                    Creative.id.notin_(
                        select(Ad.creative_id).where(Ad.creative_id.isnot(None))
                    )
                )
            )
    connection.status = "disconnected"
    connection.connected_at = None
    connection.last_sync_at = None
    connection.error_message = None
    await session.commit()
    await session.refresh(connection)
    logger.info(
        "integration disconnected (business_id=%s, provider=%s)",
        business_id,
        connection.provider,
    )
    return connection


# -- read views ---------------------------------------------------------------


async def connection_view(session: AsyncSession, connection: IntegrationConnection) -> dict:
    business_id = connection.business_id
    source = connection.provider
    products_count = await session.scalar(
        select(func.count(Product.id)).where(
            Product.business_id == business_id,
            Product.external_source == source,
        )
    )
    orders_count = await session.scalar(
        select(func.count(Order.id)).where(
            Order.business_id == business_id, Order.source == source
        )
    )
    customers_count = await session.scalar(
        select(func.count(Customer.id)).where(
            Customer.business_id == business_id,
            Customer.external_id.isnot(None),
        )
    )
    inventory_count = await session.scalar(
        select(func.count(func.distinct(InventorySnapshot.product_id))).where(
            InventorySnapshot.source == source
        )
    )
    latest_run = await session.scalar(
        select(SyncRun)
        .where(SyncRun.connection_id == connection.id)
        .order_by(SyncRun.started_at.desc())
        .limit(1)
    )
    campaigns_count = ad_sets_count = ads_count = daily_records_count = 0
    if connection.provider == "meta":
        ad_account = await session.scalar(
            select(AdAccount.id).where(
                AdAccount.integration_connection_id == connection.id
            )
        )
        if ad_account is not None:
            campaigns_count = await session.scalar(
                select(func.count(Campaign.id)).where(Campaign.ad_account_id == ad_account)
            )
            ad_sets_count = await session.scalar(
                select(func.count(AdSet.id)).where(AdSet.ad_account_id == ad_account)
            )
            ads_count = await session.scalar(
                select(func.count(Ad.id)).where(Ad.ad_account_id == ad_account)
            )
            daily_records_count = await session.scalar(
                select(func.count(AdInsight.id)).where(
                    AdInsight.ad_account_id == ad_account
                )
            )
    return {
        "id": connection.id,
        "business_id": business_id,
        "provider": connection.provider,
        "status": connection.status,
        "external_account_id": connection.external_account_id,
        "external_account_name": connection.external_account_name,
        "scopes": connection.scopes,
        "metadata": connection.provider_metadata,
        "connected_at": connection.connected_at,
        "last_sync_at": connection.last_sync_at,
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
        "products_count": products_count,
        "orders_count": orders_count,
        "customers_count": customers_count,
        "inventory_count": inventory_count,
        "campaigns_count": campaigns_count,
        "ad_sets_count": ad_sets_count,
        "ads_count": ads_count,
        "daily_records_count": daily_records_count,
        "latest_sync": (
            {
                "id": latest_run.id,
                "resource_type": latest_run.resource_type,
                "status": latest_run.status,
                "started_at": latest_run.started_at,
                "finished_at": latest_run.finished_at,
                "records_processed": latest_run.records_processed,
                "error_summary": latest_run.error_summary,
            }
            if latest_run
            else None
        ),
    }


def _adapter(provider: str) -> IntegrationAdapter:
    return get_registry().get(provider)