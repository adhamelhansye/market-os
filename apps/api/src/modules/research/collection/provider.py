"""Provider interface and the controlled public website provider."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from src.modules.research.collection.extract import extract_page
from src.modules.research.collection.security import (
    URLPolicyError,
    URLScope,
    normalize_url,
    validate_public_url,
)

MAX_PAGES = 50
MAX_DEPTH = 2
MAX_RESPONSE_BYTES = 2_000_000
MAX_REDIRECTS = 5
MAX_TEXT_BYTES = 200_000


class CollectionError(RuntimeError):
    code = "collection_failed"
    retryable = False


class CollectionTransientError(CollectionError):
    retryable = True


@dataclass(frozen=True)
class CollectionRequest:
    url: str
    mode: str = "single_page"
    max_pages: int = 1
    max_depth: int = 0
    same_domain: bool = True
    specific_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectedPage:
    original_url: str
    normalized_url: str
    final_url: str
    status_code: int
    content_type: str | None
    extracted: dict
    content: str
    content_hash: str
    response_size: int
    duration_ms: int
    depth: int
    retrieved_at: datetime
    redirect_count: int


class ResearchCollectionProvider:
    name = "base"

    async def collect(self, request: CollectionRequest) -> list[CollectedPage]:
        raise NotImplementedError


class WebsiteCollectionProvider(ResearchCollectionProvider):
    name = "website"

    async def collect(self, request: CollectionRequest) -> list[CollectedPage]:
        if request.mode not in {"single_page", "site_limited", "specific_urls"}:
            raise CollectionError("unsupported collection mode")
        if request.max_pages < 1 or request.max_pages > MAX_PAGES:
            raise CollectionError("max_pages must be between 1 and 50")
        if request.max_depth < 0 or request.max_depth > MAX_DEPTH:
            raise CollectionError("max_depth must be between 0 and 2")
        root = await validate_public_url(request.url)
        scope = URLScope(urlsplit(root).hostname or "", request.same_domain)
        queue: deque[tuple[str, int]] = deque([(root, 0)])
        if request.mode == "specific_urls":
            queue = deque((await validate_public_url(url), 0) for url in request.specific_urls)
        pages: list[CollectedPage] = []
        seen: set[str] = set()
        last_request_at = 0.0
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)
        headers = {"User-Agent": "MarketingOS Research Collector/1.0 (+public research)"}
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=False, headers=headers
        ) as client:
            while queue and len(pages) < request.max_pages:
                candidate, depth = queue.popleft()
                candidate = normalize_url(candidate)
                if candidate in seen or depth > request.max_depth or not scope.allows(candidate):
                    continue
                seen.add(candidate)
                elapsed = time.monotonic() - last_request_at
                if last_request_at and elapsed < 0.2:
                    await asyncio.sleep(0.2 - elapsed)
                page = await self._fetch_page(client, candidate, depth)
                last_request_at = time.monotonic()
                pages.append(page)
                if request.mode == "site_limited" and depth < request.max_depth:
                    for link in page.extracted.get("links", []):
                        try:
                            normalized = normalize_url(urljoin(page.final_url, link))
                        except URLPolicyError:
                            continue
                        if scope.allows(normalized) and normalized not in seen:
                            queue.append((normalized, depth + 1))
        return pages

    async def _fetch_page(self, client: httpx.AsyncClient, url: str, depth: int) -> CollectedPage:
        started = time.monotonic()
        current = url
        redirects = 0
        while True:
            # Validate every hop, including redirects, immediately before use.
            await validate_public_url(current)
            try:
                response = await client.get(current)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise CollectionTransientError("public page request timed out or failed") from exc
            finally:
                # Public collection never retains or replays server cookies.
                client.cookies.clear()
            if response.status_code in {429, 500, 502, 503, 504}:
                if response.status_code == 429:
                    try:
                        delay = min(max(float(response.headers.get("retry-after", "0")), 0), 60)
                    except ValueError:
                        delay = 0
                    if delay:
                        await asyncio.sleep(delay)
                raise CollectionTransientError(f"public page returned HTTP {response.status_code}")
            if 300 <= response.status_code < 400:
                location = response.headers.get("location")
                if not location or redirects >= MAX_REDIRECTS:
                    raise CollectionError("redirect limit exceeded")
                current = normalize_url(urljoin(current, location))
                redirects += 1
                continue
            if response.status_code >= 400:
                raise CollectionError(f"public page returned HTTP {response.status_code}")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower() or None
            if content_type not in {"text/html", "application/xhtml+xml", "application/json"}:
                raise CollectionError("unsupported content type")
            body = response.content
            if len(body) > MAX_RESPONSE_BYTES:
                raise CollectionError("response exceeds collection size limit")
            text = body.decode(response.encoding or "utf-8", errors="replace")
            extracted = extract_page(text, str(response.url))
            normalized_content = extracted["text"][:MAX_TEXT_BYTES]
            return CollectedPage(
                original_url=url,
                normalized_url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                content_type=content_type,
                extracted=extracted,
                content=normalized_content,
                content_hash=hashlib.sha256(normalized_content.encode("utf-8")).hexdigest(),
                response_size=len(body),
                duration_ms=int((time.monotonic() - started) * 1000),
                depth=depth,
                retrieved_at=datetime.now(UTC),
                redirect_count=redirects,
            )
