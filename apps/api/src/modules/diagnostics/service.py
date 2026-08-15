"""Diagnostics service: read-only orchestration for the diagnostics router.

Everything computed lives in the engine; this module only wires ranges,
scopes results per business and validates filters. The diagnostics engine
reuses the metrics service and KPI engine — it never queries providers and
never recomputes KPI formulas.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.modules.diagnostics import engine
from src.modules.diagnostics.errors import DiagnosticsFilterError
from src.modules.diagnostics.severity import is_valid as severity_is_valid
from src.modules.metrics.aggregation import Range

_ALLOWED_ENTITY_TYPES = (
    engine.ENTITY_TYPE_BUSINESS,
    engine.ENTITY_TYPE_CAMPAIGN,
    engine.ENTITY_TYPE_AD_SET,
    engine.ENTITY_TYPE_AD,
)

_ALLOWED_CATEGORIES = (
    "traffic",
    "creative",
    "conversion",
    "offer",
    "funnel",
    "economics",
    "tracking",
    "data_quality",
    "performance",
    "scaling_readiness",
)

_ALLOWED_STATUSES = ("detected", "resolved", "insufficient_data")


def _validate_filter(
    *, entity_type: str | None, severity: str | None, category: str | None, status: str | None
) -> None:
    if entity_type is not None and entity_type not in _ALLOWED_ENTITY_TYPES:
        raise DiagnosticsFilterError(f"Unsupported entity_type: {entity_type}")
    if severity is not None and not severity_is_valid(severity):
        raise DiagnosticsFilterError(f"Unknown severity: {severity}")
    if category is not None and category not in _ALLOWED_CATEGORIES:
        raise DiagnosticsFilterError(f"Unknown category: {category}")
    if status is not None and status not in _ALLOWED_STATUSES:
        raise DiagnosticsFilterError(f"Unknown status: {status}")


async def diagnostics_for_business(
    session: AsyncSession,
    business,
    range: Range,
    settings: Settings,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    severity: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> dict:
    _validate_filter(entity_type=entity_type, severity=severity, category=category, status=status)
    await engine.validate_entity_filter(session, business.id, entity_type, entity_id)
    data = await engine.diagnose_business(session, business, range, settings)
    filtered = engine.filter_findings(
        data["findings"],
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        severity=severity,
        category=category,
        status=status,
    )
    data["findings"] = [engine.finding_view(finding, range) for finding in filtered]
    data["summary"] = engine.summary_of(filtered)
    if entity_type == engine.ENTITY_TYPE_CAMPAIGN and entity_id is not None:
        data["campaign_states"] = [
            state
            for state in data["campaign_states"]
            if str(state["campaign_id"]) == str(entity_id)
        ]
    return data


async def diagnostics_summary(
    session: AsyncSession,
    business,
    range: Range,
    settings: Settings,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    severity: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> dict:
    data = await diagnostics_for_business(
        session,
        business,
        range,
        settings,
        entity_type=entity_type,
        entity_id=entity_id,
        severity=severity,
        category=category,
        status=status,
    )
    return data["summary"]


async def campaign_diagnostics(
    session: AsyncSession,
    business,
    campaign_id: uuid.UUID,
    range: Range,
    settings: Settings,
) -> dict:
    data = await engine.diagnose_campaign(session, business, campaign_id, range, settings)
    data["findings"] = [engine.finding_view(finding, range) for finding in data["findings"]]
    return data


__all__ = [
    "diagnostics_for_business",
    "diagnostics_summary",
    "campaign_diagnostics",
]