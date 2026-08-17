"""Simulator service: deterministic orchestration and persistence.

The service is the only place that talks to the database for
simulations:

- validates the request (domain rules in `validation.py`);
- builds the assumption set from canonical metrics + economics
  (`inputs.py`) and derives scenario levels from the historical daily
  distribution (`scenarios.py`);
- delegates all math to `engine.py` (never recomputed here);
- persists the deterministic snapshot to the `simulations` table.
  Idempotency: `assumptions_hash` (SHA-256 of the resolved assumptions
  and reference window) plus model version form the unique identity —
  replaying identical inputs collapses to the same row, refreshed.

The service performs no autonomous action: no budget change, no
campaign edit, no provider mutation, no publishing.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Business,
    Simulation,
    SimulationAssumption,
    SimulationResult,
)
from src.modules.businesses.service import get_business
from src.modules.metrics.aggregation import Range
from src.modules.simulator import engine, inputs
from src.modules.simulator import scenarios as scenarios_module
from src.modules.simulator.constants import (
    ALL_SCENARIOS,
    DATA_QUALITY_INSUFFICIENT,
    DATA_QUALITY_MODERATE,
    DATA_QUALITY_STRONG,
    DATA_QUALITY_WEAK,
    ENTITY_TYPE_BUSINESS,
    MIN_OBSERVATIONS_MODERATE,
    MIN_OBSERVATIONS_STRONG,
    MIN_OBSERVATIONS_WEAK,
    SIMULATOR_VERSION,
)
from src.modules.simulator.engine import EngineRun
from src.modules.simulator.inputs import AssumptionSet
from src.modules.simulator.schemas import (
    AssumptionRead,
    BreakEvenRead,
    ProfitabilityRead,
    ScenarioMetricsRead,
    ScenarioResultRead,
    SensitivityTableRead,
    SimulationCreateRequest,
    SimulationOverrideInput,
    SimulationRead,
    SimulationSummaryRead,
    TargetComparisonRead,
)
from src.modules.simulator.validation import (
    validate_referenced_campaign,
    validate_simulation_request,
)


def assumptions_hash(assumptions: AssumptionSet) -> str:
    """Deterministic SHA-256 over the resolved assumptions + window.

    Money/ratio values are canonicalized (`normalize`) before hashing, so
    Decimal scale differences never break idempotency.
    """
    payload = "|".join(
        f"{a.name}={a.value.normalize() if a.value is not None else 'None'}"
        for a in assumptions.all_assumptions()
    )
    payload += f"|window={assumptions.reference_window_start}:{assumptions.reference_window_end}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evidence_strength(observation_count: int) -> str:
    if observation_count >= MIN_OBSERVATIONS_STRONG:
        return DATA_QUALITY_STRONG
    if observation_count >= MIN_OBSERVATIONS_MODERATE:
        return DATA_QUALITY_MODERATE
    if observation_count >= MIN_OBSERVATIONS_WEAK:
        return DATA_QUALITY_WEAK
    return DATA_QUALITY_INSUFFICIENT


def _request_snapshot(request: SimulationCreateRequest) -> dict[str, Any]:
    """Serialisable request snapshot (Decimal as strings) for rerun/audit."""
    return {
        "budget": str(request.budget),
        "duration_days": request.duration_days,
        "historical_window_days": request.historical_window_days,
        "entity_type": request.entity_type,
        "entity_id": str(request.entity_id) if request.entity_id else None,
        "target_cpa": str(request.target_cpa) if request.target_cpa is not None else None,
        "target_roas": str(request.target_roas) if request.target_roas is not None else None,
        "target_revenue": (
            str(request.target_revenue) if request.target_revenue is not None else None
        ),
        "target_profit": (
            str(request.target_profit) if request.target_profit is not None else None
        ),
        "overrides": {
            key: (str(value) if value is not None else None)
            for key, value in request.overrides.model_dump().items()
        },
    }


def _engine_run_snapshot(run: EngineRun) -> dict[str, Any]:
    return {
        "model_used": run.model_used,
        "calculation_path": run.calculation_path,
        "scenarios": run.scenarios_dict(),
        "reasons": run.reasons,
        "break_even": _serialize(run.break_even),
        "profitability": _serialize(run.profitability),
        "sensitivity": _serialize(run.sensitivity),
        "targets": _serialize(run.targets),
        "data_quality": run.data_quality,
        "evidence_strength": run.evidence_strength,
    }


def _serialize(model) -> dict[str, Any] | list | None:
    if model is None:
        return None
    if isinstance(model, list):
        return [_serialize(item) for item in model]
    return {
        key: (str(value) if isinstance(value, Decimal) else value)
        for key, value in model.model_dump().items()
    }


def _jsonable(value: Any) -> Any:
    """Deep-convert Decimals to strings for JSONB snapshots."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(v) for key, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Read-side reconstruction (single source: the persisted snapshots)
# ---------------------------------------------------------------------------


def _assumptions_from_snapshot(rows: list[dict[str, Any]]) -> list[AssumptionRead]:
    out: list[AssumptionRead] = []
    for row in rows:
        out.append(
            AssumptionRead(
                name=row["name"],
                value=_decimal(row.get("value")),
                unit=row.get("unit", "ratio"),
                source=row.get("source", "system_default"),
                source_entity=row.get("source_entity"),
                historical_value=_decimal(row.get("historical_value")),
                override=bool(row.get("override", False)),
                confidence=row.get("confidence", "insufficient"),
                unavailable_reason=row.get("unavailable_reason"),
            )
        )
    return out


def _scenario_result(level: str, results: dict[str, Any]) -> ScenarioResultRead:
    reason = (results.get("reasons") or {}).get(level)
    metrics = (results.get("scenarios") or {}).get(level)
    return ScenarioResultRead(
        label=level,
        metrics=ScenarioMetricsRead(**(metrics or {})),
        available=metrics is not None,
        reason=reason,
    )


def _to_read(row: Simulation) -> SimulationRead:
    assumptions_raw: list[dict[str, Any]] = row.assumptions_snapshot or []
    results: dict[str, Any] = row.results_snapshot or {}
    return SimulationRead(
        id=row.id,
        business_id=row.business_id,
        organization_id=row.organization_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        model_version=row.model_version,
        assumptions_hash=row.assumptions_hash,
        model_used=results.get("model_used", "unavailable"),
        calculation_path=results.get("calculation_path", "unavailable"),
        assumptions=_assumptions_from_snapshot(assumptions_raw),
        scenarios={level: _scenario_result(level, results) for level in ALL_SCENARIOS},
        break_even=BreakEvenRead(**results.get("break_even") or {}),
        profitability=ProfitabilityRead(**results.get("profitability") or {}),
        sensitivity=[SensitivityTableRead(**table) for table in (results.get("sensitivity") or [])],
        targets=[TargetComparisonRead(**target) for target in (results.get("targets") or [])],
        data_quality=results.get("data_quality", DATA_QUALITY_INSUFFICIENT),
        evidence_strength=results.get("evidence_strength", DATA_QUALITY_INSUFFICIENT),
        currency=row.currency,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        assumptions_snapshot=row.assumptions_snapshot,
        results_snapshot=row.results_snapshot,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def _compute(
    session: AsyncSession,
    business: Business,
    request: SimulationCreateRequest,
) -> tuple[AssumptionSet, EngineRun, int]:
    """Build assumptions + profile + engine run for a request."""
    assumptions = await inputs.build_assumption_set(
        session,
        business,
        budget=request.budget,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        historical_window_days=request.historical_window_days,
        overrides=request.overrides,
        target_cpa=request.target_cpa,
        target_roas=request.target_roas,
    )
    window = Range(
        kind="custom",
        start=assumptions.reference_window_start,
        end=assumptions.reference_window_end,
        previous_start=None,
        previous_end=None,
    )
    daily = await scenarios_module.load_daily_ratios(
        session,
        business,
        window,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
    )
    profile = scenarios_module.build_scenario_profile(assumptions, daily)
    observation_count = scenarios_module.best_observation_count(daily)
    run = engine.run_simulation(
        assumptions=assumptions,
        profile=profile,
        evidence_strength=_evidence_strength(observation_count),
        target_cpa=request.target_cpa,
        target_roas=request.target_roas,
        target_revenue=request.target_revenue,
        target_profit=request.target_profit,
    )
    return assumptions, run, observation_count


async def create_simulation(
    session: AsyncSession,
    business: Business,
    *,
    request: SimulationCreateRequest,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
) -> Simulation:
    """Validate, compute and persist a simulation (idempotent)."""
    validate_simulation_request(request)
    if request.entity_type != ENTITY_TYPE_BUSINESS and request.entity_id is not None:
        await validate_referenced_campaign(session, business.id, request.entity_id)

    assumptions, run, observation_count = await _compute(session, business, request)
    hash_value = assumptions_hash(assumptions)

    assumptions_rows = [
        {
            "name": a.name,
            "value": a.value,
            "unit": a.unit,
            "source": a.source,
            "source_entity": a.source_entity,
            "historical_value": a.historical_value,
            "override": a.override,
            "confidence": a.confidence,
            "unavailable_reason": a.unavailable_reason,
        }
        for a in assumptions.all_assumptions()
    ]

    stmt = (
        pg_insert(Simulation)
        .values(
            organization_id=organization_id,
            business_id=business.id,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            model_version=SIMULATOR_VERSION,
            assumptions_hash=hash_value,
            model_used=run.model_used,
            calculation_path=run.calculation_path,
            data_quality=run.data_quality,
            evidence_strength=run.evidence_strength,
            currency=business.currency,
            budget=request.budget,
            duration_days=request.duration_days,
            historical_window_days=request.historical_window_days,
            reference_start=assumptions.reference_window_start,
            reference_end=assumptions.reference_window_end,
            input_snapshot=_request_snapshot(request),
            assumptions_snapshot=_jsonable(assumptions_rows),
            results_snapshot=_jsonable(_engine_run_snapshot(run)),
            created_by=created_by,
        )
        .on_conflict_do_update(
            index_elements=[
                "organization_id",
                "business_id",
                "entity_type",
                "entity_id",
                "assumptions_hash",
                "model_version",
            ],
            set_={
                "model_used": run.model_used,
                "calculation_path": run.calculation_path,
                "data_quality": run.data_quality,
                "evidence_strength": run.evidence_strength,
                "input_snapshot": _request_snapshot(request),
                "assumptions_snapshot": _jsonable(assumptions_rows),
                "results_snapshot": _jsonable(_engine_run_snapshot(run)),
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(Simulation)
    )
    row = await session.execute(stmt)
    simulation = row.scalar_one()

    await _replace_assumption_rows(session, simulation.id, assumptions_rows)
    await _replace_result_rows(session, simulation.id, run)

    await session.commit()
    return simulation


async def _replace_assumption_rows(
    session: AsyncSession, simulation_id: uuid.UUID, rows: list[dict]
) -> None:
    existing = list(
        await session.scalars(
            select(SimulationAssumption).where(SimulationAssumption.simulation_id == simulation_id)
        )
    )
    for row in existing:
        await session.delete(row)
    await session.flush()
    for data in rows:
        session.add(SimulationAssumption(simulation_id=simulation_id, **data))
    await session.flush()


async def _replace_result_rows(
    session: AsyncSession, simulation_id: uuid.UUID, run: EngineRun
) -> None:
    existing = list(
        await session.scalars(
            select(SimulationResult).where(SimulationResult.simulation_id == simulation_id)
        )
    )
    for row in existing:
        await session.delete(row)
    await session.flush()
    for level in ALL_SCENARIOS:
        reason = run.reasons.get(level)
        metrics = run.scenarios.get(level)
        session.add(
            SimulationResult(
                simulation_id=simulation_id,
                scenario=level,
                metrics=(_jsonable(metrics.to_dict()) if metrics is not None else None),
                available=metrics is not None,
                reason=reason,
            )
        )
    await session.flush()


async def get_simulation(
    session: AsyncSession,
    business_id: uuid.UUID,
    simulation_id: uuid.UUID,
) -> Simulation | None:
    return await session.scalar(
        select(Simulation).where(
            Simulation.business_id == business_id,
            Simulation.id == simulation_id,
        )
    )


async def list_simulations(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    limit: int = 20,
) -> SimulationSummaryRead:
    total = await session.scalar(
        select(func.count()).select_from(Simulation).where(Simulation.business_id == business_id)
    )
    rows = list(
        await session.scalars(
            select(Simulation)
            .where(Simulation.business_id == business_id)
            .order_by(Simulation.created_at.desc())
            .limit(limit)
        )
    )
    return SimulationSummaryRead(
        business_id=business_id,
        total=int(total or 0),
        simulations=[_to_read(row) for row in rows],
    )


def request_from_snapshot(input_snapshot: dict[str, Any]) -> SimulationCreateRequest:
    """Rebuild the original request from a persisted input snapshot.

    Money values were stored as strings; Decimal(str(...)) restores them
    exactly (no float round-trip).
    """
    return SimulationCreateRequest(
        budget=Decimal(str(input_snapshot["budget"])),
        duration_days=int(input_snapshot["duration_days"]),
        historical_window_days=int(input_snapshot["historical_window_days"]),
        entity_type=input_snapshot["entity_type"],
        entity_id=(
            uuid.UUID(input_snapshot["entity_id"]) if input_snapshot.get("entity_id") else None
        ),
        target_cpa=_decimal(input_snapshot.get("target_cpa")),
        target_roas=_decimal(input_snapshot.get("target_roas")),
        target_revenue=_decimal(input_snapshot.get("target_revenue")),
        target_profit=_decimal(input_snapshot.get("target_profit")),
        overrides=SimulationOverrideInput(
            **{
                key: _decimal(value)
                for key, value in (input_snapshot.get("overrides") or {}).items()
            }
        ),
    )


async def rerun_simulation(
    session: AsyncSession,
    business: Business,
    simulation: Simulation,
    *,
    organization_id: uuid.UUID,
) -> Simulation:
    """Recompute a persisted simulation against current data.

    The original request is rebuilt from the input snapshot and re-run
    through the same deterministic pipeline. Identical resolved
    assumptions collapse to the same row (upsert); changed history
    produces a fresh row with a new assumptions_hash.
    """
    request = request_from_snapshot(simulation.input_snapshot or {})
    validate_simulation_request(request)
    if request.entity_type != ENTITY_TYPE_BUSINESS and request.entity_id is not None:
        await validate_referenced_campaign(session, business.id, request.entity_id)
    return await create_simulation(
        session,
        business,
        request=request,
        organization_id=organization_id,
        created_by=simulation.created_by,
    )


def to_read(row: Simulation) -> SimulationRead:
    return _to_read(row)


__all__ = [
    "assumptions_hash",
    "create_simulation",
    "get_simulation",
    "get_business",
    "list_simulations",
    "request_from_snapshot",
    "rerun_simulation",
    "to_read",
]
