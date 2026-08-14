"""Authentication business logic. No route-level authorization logic lives
in routers; all flows are implemented here and tested independently."""

import re
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.exceptions import ConflictError, InvalidCredentialsError
from src.core.rbac import DEFAULT_ROLES
from src.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    token_fingerprint,
    verify_password,
)
from src.db.models import Membership, Organization, Role, User

SLUG_PATTERN = re.compile(r"[^a-z0-9-]+")


def normalize_email(email: str) -> str:
    """Canonical email: trimmed and lowercased.

    Used for uniqueness and for every account lookup so that
    "Alice@Example.com", "alice@example.com" and " ALICE@example.com "
    all resolve to the same account.
    """
    return email.strip().lower()


def slugify(name: str) -> str:
    slug = SLUG_PATTERN.sub("-", name.lower()).strip("-")
    return slug or f"org-{uuid.uuid4().hex[:8]}"


async def unique_slug(session: AsyncSession, base_slug: str) -> str:
    candidate = base_slug
    suffix = 2
    while await session.scalar(select(Organization.id).where(Organization.slug == candidate)):
        candidate = f"{base_slug}-{suffix}"
        suffix += 1
    return candidate


async def signup(
    session: AsyncSession,
    *,
    name: str,
    email: str,
    password: str,
    organization_name: str,
    organization_type: str,
) -> tuple[User, Organization]:
    """Creates user + organization + owner role + membership atomically.

    The pre-check is a fast path only: the database unique constraints remain
    the final authority. A concurrent duplicate (or any other uniqueness
    violation) surfaces as IntegrityError and is converted to a 409 conflict
    instead of a 500.
    """
    email = normalize_email(email)
    existing = await session.scalar(select(User.id).where(User.email == email))
    if existing:
        raise ConflictError("An account with this email already exists")
    try:
        user = User(name=name, email=email, password_hash=hash_password(password))
        session.add(user)
        await session.flush()

        organization = Organization(
            name=organization_name,
            slug=await unique_slug(session, slugify(organization_name)),
            type=organization_type,
        )
        session.add(organization)
        await session.flush()

        owner_role = Role(
            organization_id=organization.id,
            name="owner",
            permissions_json=sorted(DEFAULT_ROLES["owner"]),
        )
        session.add(owner_role)
        await session.flush()

        session.add(
            Membership(
                user_id=user.id,
                organization_id=organization.id,
                role_id=owner_role.id,
                status="active",
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError("An account with this email already exists") from None
    return user, organization


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    """Returns the user on success; raises InvalidCredentialsError otherwise.

    Inactive users are treated exactly like unknown credentials: no tokens
    are ever issued for a disabled account.
    """
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        raise InvalidCredentialsError("Invalid email or password")
    return user


def issue_tokens(user: User, settings: Settings) -> tuple[str, str, str]:
    """Returns (access_token, refresh_token, refresh_jti)."""
    access = create_access_token(user.id, settings)
    refresh, jti = create_refresh_token(user.id, settings)
    return access, refresh, jti


async def store_refresh_token(
    redis: Redis, jti: str, token: str, settings: Settings
) -> None:
    key = f"refresh_token:{jti}"
    await redis.set(key, token_fingerprint(token), ex=settings.refresh_token_expire_days * 86400)


async def consume_refresh_token(redis: Redis, jti: str, token: str) -> bool:
    """Atomically claims the refresh session for `jti` (consumes it once).

    Uses GETDEL so that the validation (fingerprint comparison) and the
    revocation happen in a single atomic Redis operation. Concurrent
    requests presenting the same refresh token race for one read-delete:
    exactly one request wins (returns True); every loser observes a missing
    key and fails. Correct across multiple API instances — no process-local
    state is involved.
    """
    stored = await redis.getdel(f"refresh_token:{jti}")
    return stored is not None and stored == token_fingerprint(token)


async def revoke_refresh_token(redis: Redis, jti: str) -> None:
    await redis.delete(f"refresh_token:{jti}")


async def list_memberships(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Organization, Role]]:
    rows = await session.execute(
        select(Organization, Role)
        .join(Membership, Membership.organization_id == Organization.id)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.user_id == user_id, Membership.status == "active")
        .order_by(Organization.created_at)
    )
    return list(rows.all())


def utcnow() -> datetime:
    return datetime.now(UTC)