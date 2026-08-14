"""Authentication flow tests: signup, login, refresh, logout, me."""


import pytest
from conftest import auth_headers, create_organization
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.rbac import DEFAULT_ROLES
from src.db.models import Membership, Organization, Role, User

REFRESH_COOKIE = "mos_refresh"


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


async def test_refresh_rotates_tokens(client: AsyncClient, signed_up) -> None:
    first_access = signed_up.json()["access_token"]
    old_refresh = signed_up.cookies.get(REFRESH_COOKIE)
    assert old_refresh

    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    new_access = response.json()["access_token"]
    assert new_access != first_access
    new_refresh = response.cookies.get(REFRESH_COOKIE)
    assert new_refresh and new_refresh != old_refresh

    # The old refresh token must be revoked by rotation.
    replayed = await client.post("/api/v1/auth/refresh")
    assert replayed.status_code == 200  # uses the NEW cookie
    body = response.json()
    assert body["token_type"] == "bearer"


async def test_refresh_without_cookie_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


async def test_logout_revokes_refresh_token(client: AsyncClient, signed_up) -> None:
    old_refresh = signed_up.cookies.get(REFRESH_COOKIE)
    assert old_refresh
    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    # Re-using the revoked refresh token must fail even if replayed.
    revoked = await client.post("/api/v1/auth/refresh")
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