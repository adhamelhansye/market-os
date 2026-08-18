"""Research layer errors (Phase 6A).

Deterministic, machine-readable failures that map to stable HTTP
responses via the central `ApiError` handler. Validation failures
carry the exact rule that was violated so the client can prompt the
user instead of guessing.
"""

from __future__ import annotations

from typing import Any

from src.core.exceptions import ApiError, ConflictError, NotFoundError

ERROR_NOT_FOUND = "research_not_found"
ERROR_REQUIRES_CONFIRMATION = "requires_confirmation"
ERROR_INVALID_CLASSIFICATION = "invalid_classification"
ERROR_RESOURCE_CONFLICT = "resource_conflict"
ERROR_INVALID_STATE = "invalid_state"

#: Deterministic classification rule set — client may render any rule id.
MAX_RAW_EXCERPT_LENGTH = 25_000


class ResearchNotFoundError(NotFoundError):
    """Entity does not exist or is outside the caller's tenant."""

    code = ERROR_NOT_FOUND

    def __init__(self, entity: str, entity_id: str | None = None) -> None:
        message = f"{entity} not found in this business"
        details = {"entity": entity}
        if entity_id is not None:
            details["id"] = entity_id
        super().__init__(message, details=details)
        self.entity = entity
        self.entity_id = entity_id


class ResearchConfirmationError(ApiError):
    """A deterministic quality rule requires the user to confirm the input.

    Carries `reasons` (rule ids) and `classification` so the client can
    surface an explicit confirmation dialog before re-submitting.
    """

    status_code = 422
    code = ERROR_REQUIRES_CONFIRMATION

    def __init__(
        self,
        *,
        classification: str,
        reasons: list[str],
        details: list[str] | None = None,
    ) -> None:
        self.classification = classification
        self.reasons = reasons
        self.confirmation_details = details or []
        super().__init__(
            "Explicit confirmation required before storing this evidence/finding",
            details={
                "classification": classification,
                "reasons": reasons,
                "details": self.confirmation_details,
            },
        )


class ResearchClassificationError(ApiError):
    """Unknown classification / confidence / provenance / category value."""

    status_code = 422
    code = ERROR_INVALID_CLASSIFICATION

    def __init__(self, field: str, value: Any, allowed: frozenset[str]) -> None:
        self.field = field
        self.value = value
        self.allowed = allowed
        super().__init__(
            f"Invalid {field}: {value!r}",
            details={
                "field": field,
                "value": value,
                "allowed": sorted(allowed),
            },
        )


class ResearchResourceConflictError(ConflictError):
    """Duplicate or conflicting deterministic record (e.g. same content hash)."""

    code = ERROR_RESOURCE_CONFLICT

    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:
        self.reason = reason
        super().__init__(reason, details=details or {})


class ResearchInvalidStateError(ApiError):
    """Project status transition is not allowed."""

    status_code = 422
    code = ERROR_INVALID_STATE

    def __init__(self, current: str, requested: str, allowed: frozenset[str]) -> None:
        self.current = current
        self.requested = requested
        self.allowed = allowed
        super().__init__(
            f"Cannot move research project from {current!r} to {requested!r}",
            details={
                "current": current,
                "requested": requested,
                "allowed": sorted(allowed),
            },
        )


__all__ = [
    "ERROR_NOT_FOUND",
    "ERROR_REQUIRES_CONFIRMATION",
    "ERROR_INVALID_CLASSIFICATION",
    "ERROR_RESOURCE_CONFLICT",
    "ERROR_INVALID_STATE",
    "MAX_RAW_EXCERPT_LENGTH",
    "ResearchClassificationError",
    "ResearchConfirmationError",
    "ResearchInvalidStateError",
    "ResearchNotFoundError",
    "ResearchResourceConflictError",
]
