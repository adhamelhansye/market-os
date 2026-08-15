"""Integration endpoints.

- Connection lifecycle (list/get/connect/disconnect/sync) is auth + tenant
  + business-scoped: business_id comes from the path and access is validated
  by CurrentBusinessId + permissions server-side.
- The Shopify OAuth callback is a browser redirect after Shopify's
  authorization page. Identity is proven by the httpOnly callback session
  cookie + the single-use OAuth state (see base/shopify docs); the business
  is resolved from the validated state — never from query parameters. The
  callback then 302-redirects to the frontend; it never returns credentials.
- The webhook endpoint verifies the HMAC signature on the RAW body before
  anything else and records the event for idempotent processing.
"""

import base64
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from src.core.dependencies import (
    CurrentBusinessId,
    CurrentUser,
    DbSession,
    RedisClient,
    SettingsDep,
    require_permission,
)
from src.core.logging import get_logger
from src.core.tenancy import TenantContext
from src.modules.integrations import service
from src.modules.integrations.base.errors import (
    IntegrationError,
    WebhookVerificationError,
)
from src.modules.integrations.jobs import enqueue_webhook_processing
from src.modules.integrations.registry import get_registry
from src.modules.integrations.schemas import (
    ConnectionRead,
    ShopifyConnectRequest,
    ShopifyConnectResponse,
    SyncRequest,
    SyncResponse,
    WebhookAck,
)

router = APIRouter(tags=["integrations"])

logger = get_logger(__name__)


@router.get(
    "/businesses/{business_id}/integrations",
    response_model=list[ConnectionRead],
)
async def list_integrations(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[ConnectionRead]:
    connections = await service.list_connections(session, business_id)
    return [
        ConnectionRead(**await service.connection_view(session, connection))
        for connection in connections
    ]


@router.get(
    "/businesses/{business_id}/integrations/{connection_id}",
    response_model=ConnectionRead,
)
async def get_integration(
    business_id: CurrentBusinessId,
    connection_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> ConnectionRead:
    connection = await service.get_connection(session, business_id, connection_id)
    return ConnectionRead(**await service.connection_view(session, connection))


@router.post(
    "/businesses/{business_id}/integrations/shopify/connect",
    response_model=ShopifyConnectResponse,
)
async def connect_shopify(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
    settings: SettingsDep,
    response: Response,
    payload: ShopifyConnectRequest,
) -> ShopifyConnectResponse:
    auth_url, session_token = await service.start_shopify_connect(
        session,
        redis,
        settings,
        user_id=user.id,
        business_id=business_id,
        shop_domain_raw=payload.shop_domain,
        locale=payload.locale,
    )
    # Binds this browser tab to the authenticated user for the OAuth dance.
    # httpOnly + SameSite=Lax: sent on the top-level navigation to the
    # callback, never readable by scripts, expires in minutes.
    response.set_cookie(
        key=settings.callback_session_cookie_name,
        value=session_token,
        max_age=settings.callback_session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return ShopifyConnectResponse(auth_url=auth_url)


@router.get("/integrations/shopify/callback", include_in_schema=True)
async def shopify_callback(
    request: Request,
    session: DbSession,
    redis: RedisClient,
    settings: SettingsDep,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    """Completes the OAuth exchange for the browser that started it.

    Rejected callbacks (missing/invalid/expired/reused state, wrong user,
    revoked business access, failed token exchange) redirect to the
    frontend with a safe generic error — no details, no credentials.
    """
    session_token = request.cookies.get(settings.callback_session_cookie_name)
    try:
        result = await service.handle_shopify_callback(
            session,
            redis,
            settings,
            callback_session_token=session_token,
            code=code,
            state=state,
        )
    except IntegrationError as exc:
        logger.warning("shopify callback rejected: %s", exc.code)
        return _error_redirect(settings, "en")
    except Exception:  # noqa: BLE001
        logger.exception("shopify callback failed")
        return _error_redirect(settings, "en")

    response = RedirectResponse(
        url=_success_url(settings, result), status_code=302
    )
    response.delete_cookie(
        key=settings.callback_session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


def _success_url(settings, result: dict) -> str:
    locale = result.get("locale", "en")
    business_id = result.get("business_id")
    return (
        f"{settings.frontend_base_url}/{locale}/business/{business_id}/integrations"
        "?connected=1"
    )


def _error_redirect(settings, locale: str = "en") -> RedirectResponse:
    # The rejected callback cannot know the business (that is the point);
    # the user lands on the dashboard and can retry from Integrations.
    return RedirectResponse(
        url=f"{settings.frontend_base_url}/{locale}/dashboard?error=connect_failed",
        status_code=302,
    )


@router.post(
    "/businesses/{business_id}/integrations/{connection_id}/sync",
    response_model=SyncResponse,
)
async def sync_integration(
    business_id: CurrentBusinessId,
    connection_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    payload: SyncRequest | None = None,
) -> SyncResponse:
    chosen = await service.request_sync(
        session, business_id, connection_id, payload.resources if payload else None
    )
    return SyncResponse(resources=chosen)


@router.post(
    "/businesses/{business_id}/integrations/{connection_id}/disconnect",
    response_model=ConnectionRead,
)
async def disconnect_integration(
    business_id: CurrentBusinessId,
    connection_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    settings: SettingsDep,
) -> ConnectionRead:
    connection = await service.disconnect_connection(
        session, settings, business_id, connection_id
    )
    return ConnectionRead(**await service.connection_view(session, connection))


@router.post("/integrations/shopify/webhook", response_model=WebhookAck)
async def shopify_webhook(
    request: Request,
    session: DbSession,
    redis: RedisClient,
    settings: SettingsDep,
) -> WebhookAck:
    """Receives Shopify webhooks. HMAC is verified on the raw body first;
    the event is deduplicated by provider event id; processing is queued."""
    raw_body = await request.body()
    signature = request.headers.get("x-shopify-hmac-sha256")
    adapter = get_registry().get("shopify")
    if not adapter.verify_webhook(raw_body, signature):
        raise WebhookVerificationError("Invalid webhook signature")
    topic = request.headers.get("x-shopify-topic") or ""
    shop_domain = request.headers.get("x-shopify-shop-domain") or ""
    external_event_id = request.headers.get("x-shopify-webhook-id")

    event = await service.record_webhook_event(
        session, provider="shopify", external_event_id=external_event_id, raw_body=raw_body
    )
    if event is None:
        return WebhookAck(received=True)  # duplicate: already recorded

    # The payload is stored base64-encoded so the worker can re-verify the
    # signature against the EXACT original bytes.
    await redis.set(
        service.WEBHOOK_PAYLOAD_KEY.format(event.id),
        base64.b64encode(raw_body).decode("ascii"),
        ex=86400,
    )
    await redis.set(
        service.WEBHOOK_META_KEY.format(event.id),
        json.dumps(
            {
                "shop_domain": shop_domain,
                "topic": topic,
                "signature": signature or "",
            }
        ),
        ex=86400,
    )
    await enqueue_webhook_processing(str(event.id))
    logger.info("shopify webhook queued (topic=%s, event=%s)", topic, event.id)
    return WebhookAck(received=True)