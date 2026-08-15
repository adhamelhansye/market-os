"""Provider credential encryption and OAuth state handling.

Credentials are encrypted at rest with AES-256-GCM (cryptography library)
using a key derived from the environment-provided ENCRYPTION_KEY via HKDF.
The ciphertext carries a version marker so keys can be rotated without
invalidating existing rows (key_version is stored next to the ciphertext).

OAuth state tokens are short-lived, single-use, and bound to both the user
and the business: the callback resolves the business from the state — never
from an untrusted query parameter.

Never log: ciphertext, plaintext, or the derived key.
"""

import base64
import json
import os
import secrets
import uuid
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from redis.asyncio import Redis

from src.core.config import Settings
from src.core.logging import get_logger
from src.modules.integrations.base.errors import (
    OAuthStateExpiredError,
    OAuthStateMismatchError,
    OAuthStateMissingError,
)

logger = get_logger(__name__)

_VERSION_PREFIX = "v"
_CURRENT_VERSION = 1
_STATE_KEY_PREFIX = "oauth:state:"


def _derive_key(secret: str) -> bytes:
    """Derives a 32-byte AES key from the env secret via HKDF-SHA256."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"marketingos-credentials-v1",
        info=b"provider-token-encryption",
    )
    return hkdf.derive(secret.encode("utf-8"))


@dataclass(frozen=True)
class TokenCipher:
    """AES-256-GCM encrypt/decrypt for provider tokens."""

    key_version: int
    key: bytes

    @classmethod
    def from_settings(cls, settings: Settings) -> "TokenCipher":
        return cls(
            key_version=settings.encryption_key_version,
            key=_derive_key(settings.encryption_key),
        )

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = _VERSION_PREFIX + str(self.key_version) + ":" + base64.b64encode(
            nonce + ciphertext
        ).decode("ascii")
        return payload

    def decrypt(self, ciphertext: str) -> str:
        try:
            prefix, _, encoded = ciphertext.partition(":")
            if not prefix.startswith(_VERSION_PREFIX):
                raise ValueError("bad version marker")
            version = int(prefix[len(_VERSION_PREFIX) :])
            if version != self.key_version:
                raise ValueError(f"unsupported key version {version}")
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) < 12 + 16:
                raise ValueError("ciphertext too short")
            nonce, payload = raw[:12], raw[12:]
            return AESGCM(self.key).decrypt(nonce, payload, None).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - normalize all failures
            logger.warning("credential decryption failed (key_version=%s)", self.key_version)
            raise ValueError("unable to decrypt credential") from exc


class OAuthStateService:
    """Server-generated, single-use OAuth state stored in Redis.

    The state binds (user_id, business_id, locale); consuming it atomically
    removes it, so replaying the callback fails. TTL enforces short-lived
    state. The business is resolved FROM the state — never from the
    (untrusted) callback query string.
    """

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._ttl = settings.oauth_state_ttl_seconds

    async def create(
        self, *, user_id: uuid.UUID, business_id: uuid.UUID, locale: str
    ) -> str:
        state = secrets.token_urlsafe(32)
        payload = json.dumps(
            {
                "user_id": str(user_id),
                "business_id": str(business_id),
                "locale": locale,
            }
        )
        await self._redis.set(
            f"{_STATE_KEY_PREFIX}{state}", payload, ex=self._ttl
        )
        return state

    async def consume(self, state: str, *, user_id: uuid.UUID) -> dict:
        """Validates and atomically consumes the state.

        Returns the state payload (business_id, locale) on success. Raises
        OAuthStateMissingError/ExpiredError/MismatchError on every failure
        path. GETDEL makes the consume single-use even under concurrent
        callbacks, so reused states are rejected.
        """
        if not state:
            raise OAuthStateMissingError("Missing OAuth state")
        stored = await self._redis.getdel(f"{_STATE_KEY_PREFIX}{state}")
        if stored is None:
            # Distinguish "expired" from "reused" is impossible after the
            # fact; both are rejection paths. We surface a generic error.
            raise OAuthStateExpiredError("OAuth state is invalid, expired or already used")
        try:
            payload = json.loads(stored)
            stored_user = uuid.UUID(payload["user_id"])
            stored_business = uuid.UUID(payload["business_id"])
        except (ValueError, KeyError, TypeError):
            raise OAuthStateMissingError("Invalid OAuth state") from None
        if stored_user != user_id:
            raise OAuthStateMismatchError("OAuth state does not match the session")
        return {
            "user_id": stored_user,
            "business_id": stored_business,
            "locale": str(payload.get("locale") or "en"),
        }
