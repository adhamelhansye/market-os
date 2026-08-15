"""Meta Graph API client (Marketing API).

- Every request goes to https://graph.facebook.com/{version}/... against
  provider-owned paths only (fixed host, fixed version from settings) —
  there is no user-supplied URL anywhere, so no SSRF surface.
- The access token travels only in the Authorization header and never
  appears in logs or exception messages.
- Rate limits (429 including error codes 613/80004) and transient 5xx
  retries use jittered exponential backoff bounded by _MAX_RETRIES and
  honor Retry-After when present; auth failures stop immediately.
- Throttling headers (x-app-usage) are logged so operators can observe
  headroom; providers are never hammered faster after a failure.
- Malformed payloads become ProviderDataError.
"""

import asyncio
import json
import random
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
from src.modules.integrations.meta.constants import GRAPH_API_HOST, PAGE_SIZE
from src.modules.integrations.meta.errors import classify_meta_error
from src.modules.integrations.meta.schemas import (
    AdAccountResponse,
    AdResponse,
    AdSetResponse,
    CampaignResponse,
    Envelope,
    InsightItem,
    MetaErrorResponse,
    TokenExchangeResponse,
    UserResponse,
)

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_STATUSES = (429, 500, 502, 503, 504)
_USAGE_WARN_THRESHOLD = 80.0


def _jittered_delay(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 120.0)
        except (TypeError, ValueError):
            pass
    return min(random.uniform(0.5, 1.5) * (2**attempt), 60.0)


class MetaGraphClient:
    """Stateless-ish client: one instance per adapter (token-bound)."""

    def __init__(self, *, api_version: str, access_token: str) -> None:
        self._base_url = f"https://{GRAPH_API_HOST}/{api_version}"
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._timeout = httpx.Timeout(30.0)

    async def _request(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        method: str = "GET",
    ) -> httpx.Response:
        attempts = 0
        while True:
            attempts += 1
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, follow_redirects=False
                ) as client:
                    response = await client.request(
                        method,
                        f"{self._base_url}/{path}",
                        params=params,
                        headers=self._headers,
                    )
            except httpx.HTTPError as exc:
                if attempts <= _MAX_RETRIES:
                    await asyncio.sleep(_jittered_delay(attempts, None))
                    continue
                logger.warning("meta request failed after retries: %s", type(exc).__name__)
                raise ProviderError("Meta API request failed") from exc

            self._observe_usage(response)

            if response.status_code in (401, 403):
                raise ProviderAuthError("Meta rejected the stored credentials")

            error = self._extract_error(response)
            if error is not None:
                if isinstance(error, ProviderAuthError) or (
                    isinstance(error, ProviderError)
                    and error.code in ("provider_data_error",)
                ):
                    raise error
                if attempts <= _MAX_RETRIES:
                    retry_after = response.headers.get("retry-after")
                    await asyncio.sleep(_jittered_delay(attempts, retry_after))
                    continue
                raise error

            if response.status_code in _RETRY_STATUSES:
                if attempts <= _MAX_RETRIES:
                    retry_after = response.headers.get("retry-after")
                    await asyncio.sleep(_jittered_delay(attempts, retry_after))
                    continue
                if response.status_code == 429:
                    raise ProviderRateLimitError("Meta rate limit exceeded")
                raise ProviderError(f"Meta returned HTTP {response.status_code}")

            if response.status_code >= 400:
                raise ProviderError(f"Meta returned HTTP {response.status_code}")

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ProviderError(f"Meta returned HTTP {response.status_code}") from exc
            return response

    def _observe_usage(self, response: httpx.Response) -> None:
        raw = response.headers.get("x-app-usage")
        if not raw:
            return
        try:
            usage = float(raw)
        except (TypeError, ValueError):
            return
        if usage > _USAGE_WARN_THRESHOLD:
            logger.warning("meta app usage high: %.1f%%", usage)

    def _extract_error(self, response: httpx.Response) -> ProviderError | None:
        """Parses a Meta `{error: {...}}` envelope; None when absent."""
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            if response.status_code >= 400:
                return ProviderError(f"Meta returned HTTP {response.status_code}")
            return None
        if not isinstance(payload, dict) or "error" not in payload:
            return None
        try:
            body = MetaErrorResponse.model_validate(payload).error
        except ValidationError:
            return ProviderError("Meta returned an unexpected error payload")
        error = classify_meta_error(body.code, body.error_subcode)
        logger.warning(
            "meta api error (code=%s, subcode=%s, error=%s)",
            body.code,
            body.error_subcode,
            error.code,
        )
        return error

    def _parse(self, response: httpx.Response, model: type[BaseModel]) -> BaseModel:
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("meta malformed response for %s", model.__name__)
            raise ProviderDataError("Malformed response from Meta") from exc
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            logger.warning("meta malformed response for %s", model.__name__)
            raise ProviderDataError("Malformed response from Meta") from exc

    def _parse_list(
        self, response: httpx.Response, wrapper: type[BaseModel]
    ) -> tuple[list[BaseModel], str | None]:
        envelope = self._parse(response, Envelope)
        records: list[BaseModel] = []
        for item in envelope.data:
            try:
                records.append(wrapper.model_validate(item))
            except ValidationError:
                logger.warning("meta malformed list item for %s", wrapper.__name__)
                continue
        return records, envelope.paging.after if envelope.paging else None

    # -- tokens ----------------------------------------------------------------

    async def fetch_user(self) -> UserResponse:
        response = await self._request("me", {"fields": "id,name"})
        return self._parse(response, UserResponse)  # type: ignore[return-value]

    async def revoke_token(self) -> None:
        await self._request("me/permissions", method="DELETE")

    # -- discovery -------------------------------------------------------------

    async def list_ad_accounts(
        self, after: str | None = None
    ) -> tuple[list[AdAccountResponse], str | None]:
        params: dict[str, Any] = {
            "fields": (
                "id,account_id,name,currency,account_status,"
                "timezone_name,timezone_offset_hours_utc"
            ),
            "limit": PAGE_SIZE,
        }
        if after:
            params["after"] = after
        response = await self._request("me/adaccounts", params)
        accounts, next_after = self._parse_list(response, AdAccountResponse)
        return accounts, next_after  # type: ignore[return-value]

    async def fetch_ad_account(self, external_id: str) -> AdAccountResponse:
        response = await self._request(
            f"act_{external_id}",
            {
                "fields": (
                    "id,account_id,name,currency,account_status,"
                    "timezone_name,timezone_offset_hours_utc"
                )
            },
        )
        return self._parse(response, AdAccountResponse)  # type: ignore[return-value]

    # -- hierarchy -------------------------------------------------------------

    async def list_campaigns(
        self, external_id: str, after: str | None = None
    ) -> tuple[list[CampaignResponse], str | None]:
        params: dict[str, Any] = {
            "fields": (
                "id,name,status,effective_status,objective,buying_type,"
                "created_time,updated_time"
            ),
            "limit": PAGE_SIZE,
        }
        if after:
            params["after"] = after
        response = await self._request(f"act_{external_id}/campaigns", params)
        campaigns, next_after = self._parse_list(response, CampaignResponse)
        return campaigns, next_after  # type: ignore[return-value]

    async def list_ad_sets(
        self, external_id: str, after: str | None = None
    ) -> tuple[list[AdSetResponse], str | None]:
        params: dict[str, Any] = {
            "fields": (
                "id,name,status,effective_status,campaign_id,"
                "optimization_goal,billing_event,created_time,updated_time"
            ),
            "limit": PAGE_SIZE,
        }
        if after:
            params["after"] = after
        response = await self._request(f"act_{external_id}/adsets", params)
        ad_sets, next_after = self._parse_list(response, AdSetResponse)
        return ad_sets, next_after  # type: ignore[return-value]

    async def list_ads(
        self, external_id: str, after: str | None = None
    ) -> tuple[list[AdResponse], str | None]:
        params: dict[str, Any] = {
            "fields": (
                "id,name,status,effective_status,campaign_id,adset_id,"
                "creative{id,name,status,object_type,thumbnail_url,"
                "object_story_spec,created_time,updated_time},"
                "created_time,updated_time"
            ),
            "limit": PAGE_SIZE,
        }
        if after:
            params["after"] = after
        response = await self._request(f"act_{external_id}/ads", params)
        ads, next_after = self._parse_list(response, AdResponse)
        return ads, next_after  # type: ignore[return-value]

    # -- insights --------------------------------------------------------------

    async def list_insights(
        self,
        external_id: str,
        *,
        since: str,
        until: str,
        after: str | None = None,
    ) -> tuple[list[InsightItem], str | None]:
        params: dict[str, Any] = {
            "fields": (
                "date_start,campaign_id,adset_id,ad_id,impressions,reach,"
                "frequency,clicks,inline_link_clicks,landing_page_views,"
                "spend,actions,action_values"
            ),
            "time_range": json.dumps({"since": since, "until": until}),
            "time_increment": 1,
            "level": "ad",
            "limit": PAGE_SIZE,
        }
        if after:
            params["after"] = after
        response = await self._request(f"act_{external_id}/insights", params)
        items, next_after = self._parse_list(response, InsightItem)
        return items, next_after  # type: ignore[return-value]


async def exchange_access_token(
    *,
    api_version: str,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    code: str,
) -> TokenExchangeResponse:
    """Exchanges the authorization code for a user access token.

    Runs BEFORE any token exists, so it uses the app secret server-side
    only. The secret is never logged and never included in error messages.
    """
    from src.modules.integrations.base.errors import TokenExchangeError

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0), follow_redirects=False
        ) as client:
            response = await client.get(
                f"https://{GRAPH_API_HOST}/{api_version}/oauth/access_token",
                params={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
    except httpx.HTTPError as exc:
        raise TokenExchangeError("Token exchange failed") from exc
    if response.status_code >= 400:
        try:
            error = MetaErrorResponse.model_validate(response.json()).error
        except (ValidationError, ValueError, json.JSONDecodeError):
            raise TokenExchangeError("Token exchange failed") from None
        logger.warning("meta token exchange rejected (code=%s)", error.code)
        raise TokenExchangeError("Token exchange failed") from None
    try:
        return TokenExchangeResponse.model_validate(response.json())
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise TokenExchangeError("Token exchange failed") from exc