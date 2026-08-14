"""Idempotent seed: creates the four system-wide default roles
(owner, admin, member, viewer) with organization_id = NULL.

Usage (api container): python -m infra.scripts.seed
"""

import asyncio

from sqlalchemy import select

from src.core.config import get_settings
from src.core.rbac import DEFAULT_ROLES
from src.db.models import Role
from src.db.session import create_db_session_factory


async def seed() -> int:
    settings = get_settings()
    session_factory = create_db_session_factory(settings)
    created = 0
    async with session_factory() as session:
        for name, permissions in DEFAULT_ROLES.items():
            existing = await session.scalar(select(Role).where(Role.organization_id.is_(None), Role.name == name))
            if existing is None:
                session.add(Role(name=name, permissions_json=sorted(permissions)))
                created += 1
        await session.commit()
    return created


def main() -> None:
    created = asyncio.run(seed())
    print(f"Seed complete: {created} default role(s) created.")


if __name__ == "__main__":
    main()