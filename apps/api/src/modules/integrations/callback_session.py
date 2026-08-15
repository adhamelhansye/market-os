"""Callback session cookie handling.

The OAuth callback is a browser redirect, so it cannot carry the Bearer
access token (stored in-memory on the frontend). The connect endpoint (an
authenticated API call) therefore issues a short-lived httpOnly session
cookie that binds the browser to the authenticated user. The callback reads
that cookie, resolves the user, and only then accepts the OAuth state —
a state created by user A cannot be completed from user B's browser.

The cookie value is an opaque random token whose mapping to the user lives
in Redis and expires after `callback_session_ttl_seconds`. It is never a
JWT and never contains user identifiers.
"""

import secrets
import uuid

from redis.asyncio import Redis

from src.core.config import Settings

_CB_SESSION_KEY_PREFIX = "oauth:cb-session:"


class CallbackSessionService:
    """Issues and resolves the short-lived callback session cookie."""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._ttl = settings.callback_session_ttl_seconds

    async def create(self, *, user_id: uuid.UUID) -> str:
        token = secrets.token_urlsafe(32)
        await self._redis.set(
            f"{_CB_SESSION_KEY_PREFIX}{token}", str(user_id), ex=self._ttl
        )
        return token

    async def resolve(self, token: str | None) -> uuid.UUID | None:
        """Returns the bound user id, consuming the session in the process."""
        if not token:
            return None
        stored = await self._redis.getdel(f"{_CB_SESSION_KEY_PREFIX}{token}")
        if stored is None:
            return None
        try:
            return uuid.UUID(stored)
        except (ValueError, TypeError):
            return None