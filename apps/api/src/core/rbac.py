"""Centralized RBAC definitions.

The backend is the single source of truth for authorization. Frontend
hiding of controls is a UX concern only.
"""

PERMISSIONS = frozenset(
    {
        "org:read",
        "org:manage",
        "members:read",
        "members:manage",
        "business:read",
        "business:write",
        "creative:lifecycle",
        "dashboard:read",
        "settings:read",
        "settings:write",
    }
)

OWNER_PERMISSIONS = frozenset(PERMISSIONS)
ADMIN_PERMISSIONS = frozenset(
    {
        "org:read",
        "org:manage",
        "members:read",
        "members:manage",
        "business:read",
        "business:write",
        "creative:lifecycle",
        "dashboard:read",
        "settings:read",
        "settings:write",
    }
)
MEMBER_PERMISSIONS = frozenset(
    {
        "org:read",
        "members:read",
        "business:read",
        "business:write",
        "dashboard:read",
        "settings:read",
    }
)
VIEWER_PERMISSIONS = frozenset(
    {
        "org:read",
        "members:read",
        "business:read",
        "dashboard:read",
    }
)

DEFAULT_ROLES: dict[str, frozenset[str]] = {
    "owner": OWNER_PERMISSIONS,
    "admin": ADMIN_PERMISSIONS,
    "member": MEMBER_PERMISSIONS,
    "viewer": VIEWER_PERMISSIONS,
}


def validate_permissions(permissions: list[str]) -> None:
    unknown = set(permissions) - set(PERMISSIONS)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unknown permissions: {names}")