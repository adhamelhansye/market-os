"""Credentials (encryption + OAuth state + callback session) tests."""

import uuid

import pytest

from src.core.config import Settings
from src.modules.integrations.callback_session import CallbackSessionService
from src.modules.integrations.credentials import OAuthStateService, TokenCipher


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+asyncpg://u:p@h:5432/d",
        redis_url="redis://redis:6379/15",
        jwt_secret="s" * 16,
        jwt_refresh_secret="r" * 16,
        encryption_key="e" * 32,
        encryption_key_version=1,
    )


# -- TokenCipher --------------------------------------------------------------


def test_token_cipher_roundtrip(settings: Settings) -> None:
    cipher = TokenCipher.from_settings(settings)
    plaintext = "shpat_abcdef0123456789"
    ciphertext = cipher.encrypt(plaintext)
    assert ciphertext != plaintext
    assert ciphertext.startswith("v1:")
    assert cipher.decrypt(ciphertext) == plaintext


def test_token_cipher_wrong_key_version(settings: Settings) -> None:
    cipher = TokenCipher.from_settings(settings)
    ciphertext = cipher.encrypt("secret")
    other = TokenCipher(key_version=2, key=cipher.key)
    with pytest.raises(ValueError, match="unable to decrypt"):
        other.decrypt(ciphertext)


def test_token_cipher_garbage_does_not_leak(settings: Settings) -> None:
    cipher = TokenCipher.from_settings(settings)
    with pytest.raises(ValueError, match="unable to decrypt"):
        cipher.decrypt("v1:bm90LWJhc2U2NA==")
    # The error message must not include any decoded bytes or stack details.
    with pytest.raises(ValueError):
        cipher.decrypt("totally-broken-ciphertext")


def test_token_cipher_different_keys_do_not_collide(settings: Settings) -> None:
    cipher_a = TokenCipher.from_settings(settings)
    other_settings = Settings(
        app_env="test",
        database_url=settings.database_url,
        redis_url=settings.redis_url,
        jwt_secret=settings.jwt_secret,
        jwt_refresh_secret=settings.jwt_refresh_secret,
        encryption_key="f" * 32,
        encryption_key_version=1,
    )
    cipher_b = TokenCipher.from_settings(other_settings)
    with pytest.raises(ValueError):
        cipher_b.decrypt(cipher_a.encrypt("nope"))


# -- OAuthStateService --------------------------------------------------------


async def test_oauth_state_valid(settings: Settings, redis_client) -> None:
    svc = OAuthStateService(redis_client, settings)
    user_id = uuid.uuid4()
    business_id = uuid.uuid4()
    state = await svc.create(user_id=user_id, business_id=business_id, locale="en")
    payload = await svc.consume(state, user_id=user_id)
    assert payload["business_id"] == business_id
    assert payload["locale"] == "en"


async def test_oauth_state_consume_is_single_use(settings: Settings, redis_client) -> None:
    svc = OAuthStateService(redis_client, settings)
    user_id = uuid.uuid4()
    state = await svc.create(user_id=user_id, business_id=uuid.uuid4(), locale="en")
    await svc.consume(state, user_id=user_id)
    from src.modules.integrations.base.errors import OAuthStateExpiredError

    with pytest.raises(OAuthStateExpiredError):
        await svc.consume(state, user_id=user_id)


async def test_oauth_state_rejects_wrong_user(settings: Settings, redis_client) -> None:
    svc = OAuthStateService(redis_client, settings)
    state = await svc.create(
        user_id=uuid.uuid4(), business_id=uuid.uuid4(), locale="en"
    )
    from src.modules.integrations.base.errors import OAuthStateMismatchError

    with pytest.raises(OAuthStateMismatchError):
        await svc.consume(state, user_id=uuid.uuid4())


async def test_oauth_state_missing(settings: Settings, redis_client) -> None:
    svc = OAuthStateService(redis_client, settings)
    from src.modules.integrations.base.errors import OAuthStateMissingError

    with pytest.raises(OAuthStateMissingError):
        await svc.consume("", user_id=uuid.uuid4())


async def test_oauth_state_unknown_token(settings: Settings, redis_client) -> None:
    svc = OAuthStateService(redis_client, settings)
    from src.modules.integrations.base.errors import OAuthStateExpiredError

    with pytest.raises(OAuthStateExpiredError):
        await svc.consume("never-issued", user_id=uuid.uuid4())


# -- CallbackSessionService ---------------------------------------------------


async def test_callback_session_resolves_once(settings: Settings, redis_client) -> None:
    svc = CallbackSessionService(redis_client, settings)
    user_id = uuid.uuid4()
    token = await svc.create(user_id=user_id)
    assert await svc.resolve(token) == user_id
    assert await svc.resolve(token) is None


async def test_callback_session_invalid_token(settings: Settings, redis_client) -> None:
    svc = CallbackSessionService(redis_client, settings)
    assert await svc.resolve(None) is None
    assert await svc.resolve("never-issued") is None


async def test_callback_session_garbage_value(settings: Settings, redis_client) -> None:
    svc = CallbackSessionService(redis_client, settings)
    # Set a non-UUID value in the same key prefix and verify resolve() is safe.
    await redis_client.set("oauth:cb-session:bad", "not-a-uuid", ex=10)
    assert await svc.resolve("bad") is None