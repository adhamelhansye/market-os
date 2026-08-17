"""Simulator request validation (Phase 5A).

Pydantic field constraints cover shape; this module enforces the domain
rules the schema cannot express:

- `budget` must be strictly positive money;
- `historical_window_days` must be one of the supported windows;
- `entity_type` must be supported, and campaign scope requires a
  campaign id (business scope must not carry one);
- ratio overrides (ctr, cvr, refund_rate) must be fractions in [0, 1];
- money overrides must be strictly positive.

Nothing here ever fabricates a value: an invalid request is rejected
with a 4xx before any calculation starts.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.simulator.constants import (
    ALL_ENTITY_TYPES,
    ALLOWED_HISTORICAL_WINDOWS,
    ENTITY_TYPE_BUSINESS,
    ENTITY_TYPE_CAMPAIGN,
)
from src.modules.simulator.errors import SimulatorFilterError, SimulatorInputError
from src.modules.simulator.schemas import SimulationCreateRequest

ZERO = Decimal("0")
ONE = Decimal("1")


def _require_ratio(value: Decimal | None, name: str) -> None:
    if value is None:
        return
    if value < ZERO or value > ONE:
        raise SimulatorInputError(f"{name} must be a fraction between 0 and 1")


def _require_positive_money(value: Decimal | None, name: str) -> None:
    if value is None:
        return
    if value <= ZERO:
        raise SimulatorInputError(f"{name} must be strictly positive")


def validate_simulation_request(request: SimulationCreateRequest) -> None:
    """Reject malformed simulation requests before any calculation."""
    if request.budget is None or request.budget <= ZERO:
        raise SimulatorInputError("budget must be strictly positive")
    if request.duration_days < 1 or request.duration_days > 90:
        raise SimulatorFilterError(
            f"Unsupported duration_days: {request.duration_days}. Allowed: 1 to 90."
        )
    if request.historical_window_days not in ALLOWED_HISTORICAL_WINDOWS:
        raise SimulatorFilterError(
            f"Unsupported historical_window_days: {request.historical_window_days}. "
            f"Allowed: {sorted(ALLOWED_HISTORICAL_WINDOWS)}"
        )
    if request.entity_type not in ALL_ENTITY_TYPES:
        raise SimulatorFilterError(
            f"Unsupported entity_type: {request.entity_type}. Allowed: {sorted(ALL_ENTITY_TYPES)}"
        )
    if request.entity_type == ENTITY_TYPE_CAMPAIGN and request.entity_id is None:
        raise SimulatorInputError("entity_id is required when entity_type is 'campaign'")
    if request.entity_type == ENTITY_TYPE_BUSINESS and request.entity_id is not None:
        raise SimulatorInputError("entity_id must be null when entity_type is 'business'")

    _require_ratio(request.overrides.ctr, "ctr")
    _require_ratio(request.overrides.cvr, "cvr")
    _require_ratio(request.overrides.refund_rate, "refund_rate")
    _require_positive_money(request.overrides.cpc, "cpc")
    _require_positive_money(request.overrides.cpm, "cpm")
    _require_positive_money(request.overrides.aov, "aov")
    _require_positive_money(request.overrides.contribution_margin, "contribution_margin")
    _require_positive_money(request.overrides.shipping_cost, "shipping_cost")
    _require_positive_money(request.overrides.payment_fees, "payment_fees")


async def validate_referenced_campaign(
    session: AsyncSession, business_id: uuid.UUID, campaign_id: uuid.UUID
) -> None:
    """Raise a 404-equivalent on unknown / cross-tenant campaign ids.

    Reuses the same tenant-aware resolver the metrics router uses, so
    cross-tenant access always lands in a `not_found` 404 and never
    leaks existence.
    """
    from src.modules.metrics.aggregation import resolve_entity

    await resolve_entity(session, business_id, "campaign", campaign_id)


__all__ = [
    "validate_referenced_campaign",
    "validate_simulation_request",
]
