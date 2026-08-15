"""Authentication flow tests: signup, login, refresh, logout, me.

Rotation tests deliberately control cookies explicitly: httpx updates its
cookie jar automatically, so tests that want to replay an OLD refresh token
must pass the cookie per-request.
"""

import asyncio

import pytest
from conftest import auth_headers, create_organization, create_user
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.rbac import DEFAULT_ROLES
from src.core.security import create_access_token, create_refresh_token
from src.db.models import Membership, Organization, Role, User
from src.main import app

REFRESH_COOKIE = "mos_refresh"


async def _post_with_cookie(client: AsyncClient, cookie_value: str):
    """POST /api/v1/auth/refresh with an explicit refresh cookie.

    Used instead of relying on the client cookie jar so tests can replay
    OLD tokens without httpx silently swapping in the rotated cookie.
    """
    client.cookies.set(REFRESH_COOKIE, cookie_value)
    return await client.post("/api/v1/auth/refresh")


@pytest.fixture
async def signed_up(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "Password123!",
            "organization_name": "Acme Agency",
            "organization_type": "agency",
        },
    )
    assert response.status_code == 201, response.text
    return response


async def test_signup_creates_user_organization_role_membership(
    session: AsyncSession, signed_up
) -> None:
    body = signed_up.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "alice@example.com"
    assert "password" not in body["user"]

    user = await session.scalar(select(User).where(User.email == "alice@example.com"))
    assert user is not None
    assert await session.scalar(select(func.count()).select_from(Organization)) == 1

    organization = await session.scalar(select(Organization))
    assert organization.slug == "acme-agency"

    owner_role = await session.scalar(select(Role).where(Role.organization_id == organization.id))
    assert owner_role.name == "owner"
    assert set(owner_role.permissions_json) == set(DEFAULT_ROLES["owner"])

    membership = await session.scalar(
        select(Membership).where(Membership.organization_id == organization.id)
    )
    assert membership.user_id == user.id
    assert membership.role_id == owner_role.id
    assert membership.status == "active"


async def test_signup_duplicate_email_conflict(client: AsyncClient) -> None:
    payload = {
        "name": "Alice",
        "email": "alice@example.com",
        "password": "Password123!",
        "organization_name": "Acme Agency",
        "organization_type": "agency",
    }
    assert (await client.post("/api/v1/auth/signup", json=payload)).status_code == 201
    response = await client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_signup_duplicate_organization_name(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await create_organization(session, name="Acme Agency", slug="acme-agency")
    await session.commit()
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Bob",
            "email": "bob@example.com",
            "password": "Password123!",
            "organization_name": "Acme Agency",
            "organization_type": "agency",
        },
    )
    assert response.status_code == 201
    created = await session.scalar(select(Organization).where(Organization.slug != org.slug))
    assert created is not None
    assert created.slug.startswith("acme-agency-")


async def test_email_normalization_prevents_duplicate_accounts(
    client: AsyncClient,
) -> None:
    """Case and whitespace variants must resolve to a single account."""
    payload = {
        "name": "Alice",
        "email": "Alice@Example.com",
        "password": "Password123!",
        "organization_name": "Acme Agency",
        "organization_type": "agency",
    }
    assert (await client.post("/api/v1/auth/signup", json=payload)).status_code == 201

    for variant in ("alice@example.com", "ALICE@EXAMPLE.COM", " alice@example.com "):
        response = await client.post(
            "/api/v1/auth/signup", json={**payload, "email": variant}
        )
        assert response.status_code == 409, f"duplicate allowed for {variant!r}"

    # Login works regardless of case/whitespace.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": " ALICE@EXAMPLE.com ", "password": "Password123!"},
    )
    assert login.status_code == 200


async def test_concurrent_signup_same_email_single_winner(
    client: AsyncClient,
) -> None:
    """Two concurrent signups for the same email: one 201, one 409 (never 500)."""
    payload = {
        "name": "Alice",
        "email": "alice@example.com",
        "password": "Password123!",
        "organization_name": "Acme Agency",
        "organization_type": "agency",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c1, AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c2:
        r1, r2 = await asyncio.gather(
            c1.post("/api/v1/auth/signup", json=payload),
            c2.post("/api/v1/auth/signup", json=payload),
        )
    assert sorted([r1.status_code, r2.status_code]) == [201, 409]


async def test_login_success_sets_refresh_cookie(client: AsyncClient, signed_up) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "Password123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["name"] == "Alice"
    cookie = response.cookies.get(REFRESH_COOKIE)
    assert cookie
    assert response.headers["set-cookie"].lower().find("httponly") != -1


async def test_login_invalid_credentials(client: AsyncClient, signed_up) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"

    unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Password123!"},
    )
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "invalid_credentials"


async def test_refresh_rotates_tokens_with_old_rejected(
    client: AsyncClient, signed_up
) -> None:
    first_access = signed_up.json()["access_token"]
    old_refresh = signed_up.cookies.get(REFRESH_COOKIE)
    assert old_refresh

    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    new_access = response.json()["access_token"]
    new_refresh = response.cookies.get(REFRESH_COOKIE)
    assert new_access != first_access
    assert new_refresh and new_refresh != old_refresh

    # OLD token must be rejected — replay it explicitly.
    replayed = await _post_with_cookie(client, old_refresh)
    assert replayed.status_code == 401
    assert replayed.json()["error"]["code"] == "authentication_required"

    # NEW token must still work (single use).
    again = await _post_with_cookie(client, new_refresh)
    assert again.status_code == 200


async def test_concurrent_refresh_same_token_single_winner(
    signed_up,
) -> None:
    """The same refresh token used concurrently: exactly one rotation wins.

    Exercises the atomic GETDEL path against real Redis — no mocking.
    """
    token = signed_up.cookies.get(REFRESH_COOKIE)
    assert token

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c1, AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c2:
        c1.cookies.set(REFRESH_COOKIE, token)
        c2.cookies.set(REFRESH_COOKIE, token)
        r1, r2 = await asyncio.gather(
            c1.post("/api/v1/auth/refresh"),
            c2.post("/api/v1/auth/refresh"),
        )

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 401], f"expected one winner, got {statuses}"


async def test_refresh_without_cookie_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


async def test_logout_revokes_refresh_token(client: AsyncClient, signed_up) -> None:
    old_refresh = signed_up.cookies.get(REFRESH_COOKIE)
    assert old_refresh
    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    # Replay the revoked token explicitly — must fail because it was
    # revoked, not because the client no longer holds the cookie.
    revoked = await _post_with_cookie(client, old_refresh)
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "authentication_required"


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


async def test_me_with_invalid_token(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401


async def test_refresh_token_cannot_be_used_as_bearer(
    client: AsyncClient, signed_up
) -> None:
    refresh = signed_up.cookies.get(REFRESH_COOKIE)
    assert refresh
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert response.status_code == 401


async def test_access_token_cannot_be_used_as_refresh(
    client: AsyncClient, signed_up
) -> None:
    access = signed_up.json()["access_token"]
    response = await _post_with_cookie(client, access)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


async def test_me_returns_user_and_memberships(
    session: AsyncSession, client: AsyncClient, signed_up
) -> None:
    user = await session.scalar(select(User).where(User.email == "alice@example.com"))
    organization = await session.scalar(select(Organization))
    headers = await auth_headers(session, user, organization.id)

    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["active_organization_id"] == str(organization.id)
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["organization"]["slug"] == "acme-agency"
    assert body["memberships"][0]["role_name"] == "owner"


# ---------------------------------------------------------------------------
# Inactive users
# ---------------------------------------------------------------------------


async def test_login_inactive_user_rejected(session: AsyncSession, client: AsyncClient) -> None:
    await create_user(session, email="disabled@example.com", is_active=False)
    await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "disabled@example.com", "password": "Password123!"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert client.cookies.get(REFRESH_COOKIE) is None


async def test_refresh_inactive_user_rejected(
    session: AsyncSession, redis_client, client: AsyncClient
) -> None:
    from src.modules.auth.service import store_refresh_token

    user = await create_user(session, email="disabled@example.com", is_active=False)
    await session.commit()
    settings = get_settings()
    refresh, jti = create_refresh_token(user.id, settings)
    await store_refresh_token(redis_client, jti, refresh, settings)

    response = await _post_with_cookie(client, refresh)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


async def test_me_inactive_user_rejected(session: AsyncSession, client: AsyncClient) -> None:
    user = await create_user(session, email="disabled@example.com", is_active=False)
    await session.commit()

    token = create_access_token(user.id, get_settings())
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


# ---------------------------------------------------------------------------
# Cookie attributes
# ---------------------------------------------------------------------------


def test_refresh_cookie_attributes_dev_and_prod() -> None:
    from src.core.security import refresh_cookie_attributes

    def settings_for(env: str, web_url: str) -> Settings:
        return Settings(
            app_env=env,
            database_url="postgresql+asyncpg://u:p@h:5432/d",
            redis_url="redis://h:6379/0",
            jwt_secret="s" * 16,
            jwt_refresh_secret="r" * 16,
            encryption_key="e" * 16,
            web_url=web_url,
        )

    dev = refresh_cookie_attributes(settings_for("development", "http://localhost:3000"))
    assert dev["httponly"] is True
    assert dev["samesite"] == "lax"
    assert dev["path"] == "/api/v1/auth"
    assert dev["secure"] is False

    prod = refresh_cookie_attributes(settings_for("production", "https://app.example.com"))
    assert prod["secure"] is True
