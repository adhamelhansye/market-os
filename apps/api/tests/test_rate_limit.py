"""Rate limiting: exercises the dependency directly with a development
Settings object. APP_ENV=test disables the limiter in integration mode by
design; the unit-level test below proves the limit is enforced without
weakening the production behavior."""

import pytest
from redis.asyncio import Redis
from starlette.requests import Request

from src.core.config import Settings
from src.core.dependencies import rate_limit
from src.core.exceptions import RateLimitError

PATH = "/api/v1/businesses"


def _dev_settings() -> Settings:
    return Settings(
        app_env="development",
        database_url="postgresql+asyncpg://u:p@h:5432/d",
        redis_url="redis://h:6379/0",
        jwt_secret="s" * 16,
        jwt_refresh_secret="r" * 16,
        encryption_key="e" * 16,
    )


def _request(client_ip: str, port: int) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": PATH,
        "raw_path": PATH.encode(),
        "query_string": b"",
        "headers": [],
        "client": (client_ip, port),
        "server": ("test", 80),
    }
    return Request(scope)


async def test_rate_limit_dependency_enforces_limit(redis_client: Redis) -> None:
    ip = "203.0.113.9"
    key = f"ratelimit:{ip}:{PATH}"
    await redis_client.delete(key)
    dependency = rate_limit(2, 60)
    request = _request(ip, 1234)
    settings = _dev_settings()

    await dependency(request, redis_client, settings)
    await dependency(request, redis_client, settings)
    with pytest.raises(RateLimitError):
        await dependency(request, redis_client, settings)

    await redis_client.delete(key)


async def test_rate_limit_is_per_client_and_path(redis_client: Redis) -> None:
    """A second client ip is not throttled by the first client's count."""
    ip_a, ip_b = "203.0.113.9", "203.0.113.10"
    keys = [f"ratelimit:{ip}:{PATH}" for ip in (ip_a, ip_b)]
    for key in keys:
        await redis_client.delete(key)

    dependency = rate_limit(2, 60)
    settings = _dev_settings()

    await dependency(_request(ip_a, 1234), redis_client, settings)
    await dependency(_request(ip_a, 1234), redis_client, settings)
    await dependency(_request(ip_b, 4321), redis_client, settings)  # different ip: allowed

    for key in keys:
        await redis_client.delete(key)