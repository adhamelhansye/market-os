"""Shopify adapter implementation.

Mapping rules (Phase 2A):

Products
    - matched to internal products by (business_id, external_id); when no
      match exists, by variant SKU; otherwise a new product is created.
    - price changes append new product_prices records (effective_from=now);
      existing price history is never modified.
    - inventory is written as inventory_snapshots(source='shopify').
    - COGS (product_costs) are NEVER written by the sync: manually
      configured COGS must not be overwritten.

Orders
    - canonical orders (orders/order_items/customers) are upserted
      idempotently by (business_id, source, external_id); updates replace
      the canonical record — history is never modified destructively.

API errors are mapped to typed integration errors; credentials never appear
in error messages.
"""

import base64
import hashlib
import hmac
import re
from decimal import InvalidOperation
from urllib.parse import urlencode

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.modules.integrations.base.errors import (
    InvalidShopDomainError,
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    WebhookVerificationError,
)
from src.modules.integrations.base.protocol import IntegrationAdapter, ProviderCredentials
from src.modules.integrations.base.types import (
    CanonicalInventory,
    CanonicalProduct,
    ProviderExchangeResult,
    SyncPage,
    WebhookResolution,
)
from src.modules.integrations.shopify.client import ShopifyClient, exchange_access_token
from src.modules.integrations.shopify.mapper import (
    map_customer,
    map_inventory,
    map_order,
    map_product,
    map_variant_inventory,
)
from src.modules.integrations.shopify.schemas import (
    InventoryLevelResponse,
    OrderResponse,
    ProductResponse,
)

logger = get_logger(__name__)

SHOP_DOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\.myshopify\.com$")

SUPPORTED_WEBHOOK_TOPICS = {
    "products/create",
    "products/update",
    "orders/create",
    "orders/updated",
    "orders/cancelled",
    "inventory_levels/update",
}

RESOURCE_TYPES = ("products", "orders", "customers", "inventory")


def normalize_shop_domain(raw: str) -> str:
    """Validates and normalizes a Shopify shop domain.

    Only a myshopify.com subdomain is accepted: no scheme, no path, no
    arbitrary host (SSRF-safe — the domain is used verbatim in outbound
    requests).
    """
    value = raw.strip().lower().rstrip("/")
    if "://" in value or "/" in value or not SHOP_DOMAIN_PATTERN.match(value):
        raise InvalidShopDomainError(
            "Enter a valid Shopify shop domain (e.g. store.myshopify.com)"
        )
    return value


class ShopifyAdapter(IntegrationAdapter):
    """Shopify REST Admin API adapter."""

    provider = "shopify"
    resource_types = RESOURCE_TYPES

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._clients: dict[tuple[str, str], ShopifyClient] = {}

    def _client(self, credentials: ProviderCredentials) -> ShopifyClient:
        key = (credentials.shop_domain, credentials.access_token)
        client = self._clients.get(key)
        if client is None:
            client = ShopifyClient(
                shop_domain=credentials.shop_domain,
                access_token=credentials.access_token,
                api_version=self._settings.shopify_api_version,
            )
            self._clients[key] = client
        return client

    # -- OAuth connect --------------------------------------------------------

    def validate_connect_input(self, raw: str) -> str:
        return normalize_shop_domain(raw)

    def build_authorize_url(self, shop_domain: str, state: str) -> str:
        params = urlencode(
            {
                "client_id": self._settings.shopify_client_id,
                "scope": self._settings.shopify_scopes,
                "redirect_uri": self._settings.shopify_redirect_uri,
                "state": state,
            }
        )
        return f"https://{shop_domain}/admin/oauth/authorize?{params}"

    async def exchange_code(self, shop_domain: str, code: str) -> ProviderExchangeResult:
        result = await exchange_access_token(
            shop_domain=shop_domain,
            code=code,
            client_id=self._settings.shopify_client_id,
            client_secret=self._settings.shopify_client_secret,
        )
        scopes = [s.strip() for s in result.scope.split(",") if s.strip()]
        return ProviderExchangeResult(access_token=result.access_token, scope=scopes)

    # -- webhooks -----------------------------------------------------------

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        if not signature:
            return False
        secret = self._settings.shopify_client_secret
        if not secret:
            logger.warning("shopify webhook received but no client secret is configured")
            return False
        expected = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("ascii")
        return hmac.compare_digest(expected, signature)

    async def resolve_webhook(
        self, raw_body: bytes, headers: dict[str, str]
    ) -> WebhookResolution:
        if not self.verify_webhook(raw_body, headers.get("x-shopify-hmac-sha256")):
            raise WebhookVerificationError("Invalid webhook signature")
        topic = (headers.get("x-shopify-topic") or "").strip()
        if topic not in SUPPORTED_WEBHOOK_TOPICS:
            return WebhookResolution(topic=topic, records=[], handled=False)
        try:
            if topic in ("products/create", "products/update"):
                product = ProductResponse.model_validate_json(raw_body)
                return WebhookResolution(
                    topic=topic,
                    records=[map_product(product, "USD")],
                    handled=True,
                )
            if topic in ("orders/create", "orders/updated", "orders/cancelled"):
                order = OrderResponse.model_validate_json(raw_body)
                return WebhookResolution(topic=topic, records=[map_order(order)], handled=True)
            if topic == "inventory_levels/update":
                level = InventoryLevelResponse.model_validate_json(raw_body)
                return WebhookResolution(
                    topic=topic, records=[map_inventory(level)], handled=True
                )
        except (ValueError, KeyError, TypeError, InvalidOperation):
            raise ProviderDataError("Malformed Shopify webhook payload") from None
        raise ProviderError("Unhandled Shopify webhook topic")  # pragma: no cover

    # -- connection lifecycle ------------------------------------------------

    async def validate_connection(self, credentials: ProviderCredentials) -> dict:
        """Fetches shop info; raises ProviderAuthError on bad credentials."""
        client = self._client(credentials)
        shop = await client.fetch_shop()
        return {
            "name": shop.name,
            "myshopify_domain": shop.myshopify_domain,
            "currency": shop.currency,
        }

    async def disconnect(self, credentials: ProviderCredentials) -> None:
        """Best-effort token revocation (DELETE api_permissions/current)."""
        try:
            client = self._client(credentials)
            await client.revoke_access()
        except ProviderAuthError:
            pass  # token already invalid; nothing to revoke
        except ProviderError as exc:
            logger.warning("shopify disconnect: revocation failed: %s", exc.code)

    async def health_check(self, credentials: ProviderCredentials) -> bool:
        client = self._client(credentials)
        try:
            await client.fetch_shop()
            return True
        except ProviderError:
            return False

    # -- sync ----------------------------------------------------------------

    async def sync_page(
        self,
        credentials: ProviderCredentials,
        resource_type: str,
        cursor: str | None,
    ) -> SyncPage:
        if resource_type not in RESOURCE_TYPES:
            raise ProviderError(f"Unsupported resource type: {resource_type}")
        client = self._client(credentials)
        if resource_type == "products":
            products, next_cursor = await client.list_products(cursor)
            shop_currency = await client.fetch_shop_currency()
            records: list[CanonicalProduct | CanonicalInventory] = []
            for product in products:
                records.append(map_product(product, shop_currency))
                records.append(map_variant_inventory(product))
            return SyncPage(records=records, next_cursor=next_cursor)
        if resource_type == "orders":
            orders, next_cursor = await client.list_orders(cursor)
            return SyncPage(
                records=[map_order(order) for order in orders], next_cursor=next_cursor
            )
        if resource_type == "customers":
            customers, next_cursor = await client.list_customers(cursor)
            return SyncPage(
                records=[map_customer(customer) for customer in customers],
                next_cursor=next_cursor,
            )
        levels, _ = await client.list_inventory_levels()
        variant_index = await client.build_variant_index()
        records: list[CanonicalInventory] = []
        for level in levels:
            product_id = (
                variant_index.get(int(level.inventory_item_id))
                if level.inventory_item_id
                else None
            )
            records.append(map_inventory(level, product_external_id=product_id))
        return SyncPage(records=records, next_cursor=None)