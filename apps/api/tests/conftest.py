"""Test setup: build a dedicated PostgreSQL test database, run Alembic
migrations, and wire FastAPI dependency overrides for DB/Redis.

Environment variables are configured BEFORE importing application code so
that Settings picks up the test environment (APP_ENV=test disables rate
limiting).
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET", "test-jwt-secret-" + "x" * 32)
os.environ["JWT_REFRESH_SECRET"] = os.environ.get("JWT_REFRESH_SECRET", "test-refresh-" + "y" * 32)
os.environ["ENCRYPTION_KEY"] = os.environ.get("ENCRYPTION_KEY", "test-encryption-key-value")
os.environ["WEB_URL"] = os.environ.get("WEB_URL", "http://localhost:3000")

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://marketingos:marketingos_dev@localhost:5432/marketingos_test",
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = TEST_REDIS_URL

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings  # noqa: E402
from src.core.dependencies import get_db_session, get_redis_client  # noqa: E402
from src.core.security import create_access_token, hash_password  # noqa: E402
from src.db.models import Business, Membership, Organization, Role, User  # noqa: E402
from src.main import app  # noqa: E402

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _create_test_database() -> None:
    """Creates the test database (and runs Alembic migrations) if missing."""
    import asyncpg
    from alembic.config import Config

    from alembic import command

    parsed = urlparse(TEST_DATABASE_URL)
    db_name = parsed.path.lstrip("/")
    maintenance_url = urlunparse(parsed._replace(scheme="postgresql", path="/postgres"))

    async def _ensure_database() -> None:
        conn = await asyncpg.connect(maintenance_url)
        try:
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
            if not exists:
                await conn.execute(f'CREATE DATABASE "{db_name}"')
        finally:
            await conn.close()

    asyncio.run(_ensure_database())

    cfg = Config(str(os.path.join(API_DIR, "alembic.ini")))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _bootstrap() -> None:
    _create_test_database()


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    test_engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()


@pytest_asyncio.fixture(scope="session")
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as db:
        yield db


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(session: AsyncSession) -> AsyncIterator[None]:
    """Wipes all rows between tests (children first)."""
    yield
    for table in (
        "bundle_items",
        "inventory_snapshots",
        "product_prices",
        "product_costs",
        "shipping_rules",
        "discounts",
        "bundles",
        "products",
        "business_profiles",
        "business_goals",
        "memberships",
        "invitations",
        "businesses",
        "roles",
        "organizations",
        "users",
    ):
        await session.execute(text(f"DELETE FROM {table}"))
    await session.commit()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
) -> AsyncIterator[AsyncClient]:
    async def _db_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as db:
            yield db

    async def _redis_override() -> AsyncIterator[Redis]:
        yield redis_client

    app.dependency_overrides[get_db_session] = _db_override
    app.dependency_overrides[get_redis_client] = _redis_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


async def create_user(session: AsyncSession, *, email: str | None = None, **overrides) -> User:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password(overrides.pop("password", "Password123!")),
        name=overrides.pop("name", "Test User"),
        **overrides,
    )
    session.add(user)
    await session.flush()
    return user


async def create_organization(
    session: AsyncSession, *, name: str | None = None, type: str = "business", **overrides
) -> Organization:
    org = Organization(
        name=name or f"Org-{uuid.uuid4().hex[:6]}",
        slug=overrides.pop("slug", f"org-{uuid.uuid4().hex[:8]}"),
        type=type,
        **overrides,
    )
    session.add(org)
    await session.flush()
    return org


async def create_role(
    session: AsyncSession,
    *,
    name: str,
    organization_id: uuid.UUID | None,
    permissions: list[str],
) -> Role:
    role = Role(organization_id=organization_id, name=name, permissions_json=sorted(permissions))
    session.add(role)
    await session.flush()
    return role


async def create_membership(
    session: AsyncSession,
    *,
    user: User,
    organization: Organization,
    role: Role,
    status: str = "active",
) -> Membership:
    membership = Membership(
        user_id=user.id, organization_id=organization.id, role_id=role.id, status=status
    )
    session.add(membership)
    await session.flush()
    return membership


async def create_business(
    session: AsyncSession,
    *,
    organization: Organization,
    managed_by: Organization | None = None,
    name: str | None = None,
) -> Business:
    business = Business(
        organization_id=organization.id,
        managed_by_organization_id=managed_by.id if managed_by else None,
        name=name or f"Biz-{uuid.uuid4().hex[:6]}",
    )
    session.add(business)
    await session.flush()
    return business


async def auth_headers(
    session: AsyncSession, user: User, organization_id: uuid.UUID
) -> dict[str, str]:
    token = create_access_token(user.id, get_settings())
    return {"Authorization": f"Bearer {token}", "X-Organization-Id": str(organization_id)}


async def create_tenant(
    session: AsyncSession,
    *,
    org_type: str = "business",
    permissions: list[str] | None = None,
    managed_by=None,
    business_name: str | None = None,
) -> dict:
    """Builds a complete tenant: user, organization, owner role, membership
    and a business. Returns dict with user/org/business/headers."""
    from src.core.rbac import DEFAULT_ROLES

    user = await create_user(session)
    org = await create_organization(session, type=org_type)
    perms = permissions or sorted(DEFAULT_ROLES["owner"])
    role = await create_role(session, name="owner", organization_id=org.id, permissions=perms)
    await create_membership(session, user=user, organization=org, role=role)
    business = await create_business(
        session, organization=org, managed_by=managed_by, name=business_name
    )
    await session.commit()
    return {
        "user": user,
        "org": org,
        "role": role,
        "business": business,
        "headers": await auth_headers(session, user, org.id),
    }


@pytest_asyncio.fixture
async def tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)