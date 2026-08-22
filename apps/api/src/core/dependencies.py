"""Central FastAPI dependencies.

Authentication, tenant resolution, permission checks, business access and
rate limiting are all implemented here. Routes only declare which dependency
they need; they never re-implement authorization logic.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from src.core.logging import get_logger
from src.core.security import ACCESS_TOKEN_TYPE, decode_token
from src.core.tenancy import TenantContext, can_access_business, resolve_tenant
from src.db.models import User
from src.db.session import create_db_session_factory

logger = get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    factory = create_db_session_factory(settings)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis_client() -> AsyncIterator[Redis]:
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisClient = Annotated[Redis, Depends(get_redis_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: DbSession,
    settings: SettingsDep,
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required")
    try:
        payload = decode_token(credentials.credentials, settings.jwt_secret, ACCESS_TOKEN_TYPE)
    except pyjwt.InvalidTokenError:
        raise AuthenticationError("Invalid or expired access token") from None
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise AuthenticationError("Invalid access token") from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired access token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_tenant(
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> TenantContext:
    """Resolves the current organization from the X-Organization-Id header.

    The header value is never trusted; membership is validated server-side.
    """
    organization_id_raw = request.headers.get("X-Organization-Id")
    if not organization_id_raw:
        raise PermissionDeniedError("X-Organization-Id header is required")
    try:
        organization_id = uuid.UUID(organization_id_raw)
    except ValueError:
        raise PermissionDeniedError("Invalid organization id") from None
    return await resolve_tenant(session, user.id, organization_id)


CurrentTenant = Annotated[TenantContext, Depends(get_current_tenant)]


def require_permission(permission: str) -> Callable:
    """Factory for a dependency that requires `permission` in the current tenant."""

    async def dependency(
        tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    ) -> TenantContext:
        if not tenant.has_permission(permission):
            raise PermissionDeniedError(f"Missing required permission: {permission}")
        return tenant

    return dependency


async def get_org_from_path(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> TenantContext:
    """Resolves the tenant for an organization id supplied in the path.

    Used for organization-scoped detail endpoints, where the requested
    organization may differ from the current one.
    """
    organization_id_raw = request.path_params.get("organization_id", "")
    try:
        organization_id = uuid.UUID(organization_id_raw)
    except ValueError:
        raise NotFoundError("Organization not found") from None
    return await resolve_tenant(session, user.id, organization_id)


def require_org_permission(permission: str) -> Callable:
    """Factory for a dependency requiring `permission` on the path organization."""

    async def dependency(
        tenant: Annotated[TenantContext, Depends(get_org_from_path)],
    ) -> TenantContext:
        if not tenant.has_permission(permission):
            raise PermissionDeniedError(f"Missing required permission: {permission}")
        return tenant

    return dependency


async def get_business_from_path(
    request: Request,
    tenant: CurrentTenant,
    session: DbSession,
) -> uuid.UUID:
    """Validates business access rules against the current tenant."""
    business_id_raw = request.path_params.get("business_id", "")
    try:
        business_id = uuid.UUID(business_id_raw)
    except ValueError:
        raise NotFoundError("Business not found") from None
    business = await can_access_business(session, tenant.organization_id, business_id)
    if business is None:
        raise NotFoundError("Business not found")
    return business_id


CurrentBusinessId = Annotated[uuid.UUID, Depends(get_business_from_path)]


def rate_limit(limit: int, window_seconds: int) -> Callable:
    """Fixed-window rate limiter backed by Redis. Disabled in test env."""

    async def dependency(request: Request, redis: RedisClient, settings: SettingsDep) -> None:
        if settings.app_env == "test":
            return
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{client_ip}:{request.url.path}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
        if count > limit:
            logger.warning("rate limit exceeded for %s", key)
            raise RateLimitError("Too many requests")

    return dependency