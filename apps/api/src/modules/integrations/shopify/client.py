"""Shopify REST Admin API client.

- Requests go to https://{shop_domain}/admin/api/{version}/... where the
  shop domain was validated by the adapter (myshopify.com only, no scheme
  or path) — SSRF-safe.
- Responses are validated with Pydantic schemas; malformed responses become
  ProviderDataError.
- Retries with backoff on rate limits (429) and transient 5xx using
  Retry-After when present.
- Tokens are sent only in the Authorization header and never appear in logs
  or exception messages.
"""

import asyncio
import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from src.core.logging import get_logger
from src.modules.integrations.base.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderRateLimitError,
)
from src.modules.integrations.shopify.schemas import (
    CustomerResponse,
    InventoryLevelResponse,
    OrderResponse,
    ProductResponse,
    ShopResponse,
    TokenExchangeResponse,
)

logger = get_logger(__name__)

_LINK_NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="next"')
_MAX_RETRIES = 3
_RETRY_STATUSES = (429, 502, 503, 504)


def _next_page_url(headers: httpx.Headers) -> str | None:
    link = headers.get("link")
    if not link:
        return None
    match = _LINK_NEXT.search(link)
    return match.group(1) if match else None


async def exchange_access_token(
    *, shop_domain: str, code: str, client_id: str, client_secret: str
) -> TokenExchangeResponse:
    """Exchanges the OAuth authorization code for an access token.

    Runs BEFORE any token exists, so it uses the client secret directly.
    The client secret is never logged and never included in error messages.
    """
    from src.modules.integrations.base.errors import TokenExchangeError

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0), follow_redirects=False
        ) as client:
            response = await client.post(
                f"https://{shop_domain}/admin/oauth/access_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                },
            )
    except httpx.HTTPError as exc:
        raise TokenExchangeError("Token exchange failed") from exc
    if response.status_code >= 400:
        raise TokenExchangeError("Token exchange failed")
    try:
        token = TokenExchangeResponse.model_validate(response.json())
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise TokenExchangeError("Token exchange failed") from exc
    return token


class ShopifyClient:
    def __init__(self, *, shop_domain: str, access_token: str, api_version: str) -> None:
        self._base_url = f"https://{shop_domain}/admin/api/{api_version}"
        self._headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }
        self._shop_currency: str | None = None
        self._variant_index: dict[int, str] | None = None  # item id -> product external id

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        attempts = 0
        while True:
            attempts += 1
            try:
                response = await httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0), follow_redirects=False
                ).request(method, f"{self._base_url}{path}", params=params, headers=self._headers)
            except httpx.HTTPError as exc:
                if attempts <= _MAX_RETRIES:
                    await asyncio.sleep(2**attempts)
                    continue
                logger.warning("shopify request failed after retries: %s", type(exc).__name__)
                raise ProviderError("Shopify request failed") from exc

            if response.status_code in (401, 403):
                raise ProviderAuthError("Shopify rejected the stored credentials")
            if response.status_code in _RETRY_STATUSES:
                if attempts <= _MAX_RETRIES:
                    retry_after = response.headers.get("retry-after")
                    delay = float(retry_after) if retry_after else float(2**attempts)
                    await asyncio.sleep(min(delay, 30.0))
                    continue
                if response.status_code == 429:
                    raise ProviderRateLimitError("Shopify rate limit exceeded")
                raise ProviderError(f"Shopify returned HTTP {response.status_code}")
            if response.status_code >= 400:
                # The body may contain Shopify error details; never include
                # request headers or tokens.
                detail = response.text[:200]
                raise ProviderError(f"Shopify returned HTTP {response.status_code}: {detail}")
            return response

    def _get_model(
        self, response: httpx.Response, model: type[BaseModel], *, wrap: str | None = None
    ):
        try:
            data = response.json()
            if wrap is not None:
                data = data.get(wrap)
            return model.model_validate(data)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("shopify malformed response for %s", model.__name__)
            raise ProviderDataError("Malformed response from Shopify") from exc

    def _get_list(self, response: httpx.Response, model: type[BaseModel], *, wrap: str) -> list:
        try:
            data = response.json()
            return [model.model_validate(item) for item in data.get(wrap, [])]
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("shopify malformed list response for %s", model.__name__)
            raise ProviderDataError("Malformed response from Shopify") from exc

    async def fetch_shop(self) -> ShopResponse:
        response = await self._request("GET", "/shop.json")
        shop = self._get_model(response, ShopResponse, wrap="shop")
        self._shop_currency = shop.currency
        return shop

    async def fetch_shop_currency(self) -> str:
        if self._shop_currency is None:
            shop = await self.fetch_shop()
            self._shop_currency = shop.currency
        return self._shop_currency

    async def revoke_access(self) -> None:
        await self._request("DELETE", "/api_permissions/current.json")

    # -- sync endpoints ------------------------------------------------------

    async def list_products(self, cursor: str | None) -> tuple[list[ProductResponse], str | None]:
        """cursor is an updated_at_min ISO timestamp or a page URL."""
        if cursor and cursor.startswith("http"):
            response = await self._request_url(cursor)
        else:
            params: dict[str, Any] = {"limit": 250}
            if cursor:
                params["updated_at_min"] = cursor
            response = await self._request("GET", "/products.json", params=params)
        products = self._get_list(response, ProductResponse, wrap="products")
        return products, _next_page_url(response.headers)

    async def list_orders(self, cursor: str | None) -> tuple[list[OrderResponse], str | None]:
        if cursor and cursor.startswith("http"):
            response = await self._request_url(cursor)
        else:
            params: dict[str, Any] = {"limit": 250, "status": "any"}
            if cursor:
                params["updated_at_min"] = cursor
            response = await self._request("GET", "/orders.json", params=params)
        orders = self._get_list(response, OrderResponse, wrap="orders")
        return orders, _next_page_url(response.headers)

    async def list_customers(self, cursor: str | None) -> tuple[list[CustomerResponse], str | None]:
        if cursor and cursor.startswith("http"):
            response = await self._request_url(cursor)
        else:
            params: dict[str, Any] = {"limit": 250}
            if cursor:
                params["updated_at_min"] = cursor
            response = await self._request("GET", "/customers.json", params=params)
        customers = self._get_list(response, CustomerResponse, wrap="customers")
        return customers, _next_page_url(response.headers)

    async def list_inventory_levels(self) -> tuple[list[InventoryLevelResponse], None]:
        response = await self._request("GET", "/inventory_levels.json")
        levels = self._get_list(response, InventoryLevelResponse, wrap="inventory_levels")
        return levels, None

    async def _request_url(self, url: str) -> httpx.Response:
        """Follows a page_info link URL returned by Shopify."""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0), follow_redirects=False
            ) as client:
                return await client.get(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ProviderError("Shopify pagination request failed") from exc

    # -- variant index (inventory_item_id -> product external id) -----------

    async def build_variant_index(self) -> dict[int, str]:
        """Maps inventory_item_id → product external id (all products)."""
        if self._variant_index is not None:
            return self._variant_index
        index: dict[int, str] = {}
        cursor: str | None = None
        while True:
            products, next_cursor = await self.list_products(cursor)
            for product in products:
                for variant in product.variants:
                    if variant.inventory_item_id is not None:
                        index[variant.inventory_item_id] = str(product.id)
            if not next_cursor:
                break
            cursor = next_cursor
            await asyncio.sleep(0.05)  # stay well under rate limits
        self._variant_index = index
        return index