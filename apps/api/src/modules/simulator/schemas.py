"""Typed API contracts for the deterministic simulator (Phase 5A).

All money fields are Decimal (serialized as strings by the app encoder).
Unvailable values are `None` (never fabricated zeros). Scenarios and
sensitivity results carry explicit status fields so the frontend can
distinguish "zero" from "unavailable".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from src.modules.metrics.schemas import RangeRead

# ---------------------------------------------------------------------------
# Assumption objects
# ---------------------------------------------------------------------------


class AssumptionRead(BaseModel):
    """A single assumption with full provenance."""

    name: str
    value: Decimal | None = None
    unit: str = "ratio"
    source: str = "system_default"
    source_entity: str | None = None
    historical_value: Decimal | None = None
    override: bool = False
    confidence: str = "insufficient"
    date_range: RangeRead | None = None
    unavailable_reason: str | None = None


# ---------------------------------------------------------------------------
# Scenario output
# ---------------------------------------------------------------------------


class ScenarioMetricsRead(BaseModel):
    """Metrics for one scenario (downside / expected / upside)."""

    budget: Decimal | None = None
    impressions: float | None = None
    clicks: float | None = None
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cpm: Decimal | None = None
    purchases: float | None = None
    cvr: Decimal | None = None
    cpa: Decimal | None = None
    aov: Decimal | None = None
    revenue: Decimal | None = None
    roas: Decimal | None = None
    mer: Decimal | None = None
    gross_revenue: Decimal | None = None
    refund_amount: Decimal | None = None
    net_revenue: Decimal | None = None
    contribution_profit: Decimal | None = None
    contribution_margin: Decimal | None = None


class ScenarioResultRead(BaseModel):
    label: str
    metrics: ScenarioMetricsRead
    available: bool = True
    reason: str | None = None


# ---------------------------------------------------------------------------
# Break-even analysis
# ---------------------------------------------------------------------------


class BreakEvenRead(BaseModel):
    break_even_cpa: Decimal | None = None
    break_even_roas: Decimal | None = None
    simulated_cpa: Decimal | None = None
    simulated_roas: Decimal | None = None
    minimum_cvr: Decimal | None = None
    maximum_cpc: Decimal | None = None
    minimum_aov: Decimal | None = None
    maximum_cpa: Decimal | None = None
    minimum_roas: Decimal | None = None


# ---------------------------------------------------------------------------
# Profitability
# ---------------------------------------------------------------------------


class ProfitabilityRead(BaseModel):
    status: str = "unavailable"
    roas: Decimal | None = None
    break_even_roas: Decimal | None = None
    contribution_profit: Decimal | None = None
    reason: str | None = None


# ---------------------------------------------------------------------------
# Sensitivity
# ---------------------------------------------------------------------------


class SensitivityRowRead(BaseModel):
    variable: str
    change_percent: Decimal
    new_value: Decimal | None = None
    revenue: Decimal | None = None
    profit: Decimal | None = None
    cpa: Decimal | None = None
    roas: Decimal | None = None


class SensitivityTableRead(BaseModel):
    variable: str
    rows: list[SensitivityRowRead] = Field(default_factory=list)
    baseline_profit: Decimal | None = None


# ---------------------------------------------------------------------------
# Goal comparison
# ---------------------------------------------------------------------------


class TargetComparisonRead(BaseModel):
    metric_code: str
    target_value: Decimal | None = None
    simulated_value: Decimal | None = None
    status: str = "unavailable"
    reason: str | None = None


# ---------------------------------------------------------------------------
# Simulation request
# ---------------------------------------------------------------------------


class SimulationOverrideInput(BaseModel):
    """User overrides for individual assumptions."""

    budget: Decimal | None = None
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cpm: Decimal | None = None
    cvr: Decimal | None = None
    aov: Decimal | None = None
    refund_rate: Decimal | None = None
    contribution_margin: Decimal | None = None
    shipping_cost: Decimal | None = None
    payment_fees: Decimal | None = None


class SimulationCreateRequest(BaseModel):
    """Request to create a simulation."""

    budget: Decimal = Field(..., description="Simulated ad spend for the period.")
    duration_days: int = Field(
        default=30, ge=1, le=90, description="Duration in days for the simulation."
    )
    historical_window_days: int = Field(
        default=30, ge=7, le=90, description="Historical reference window."
    )
    entity_type: str = Field(default="business")
    entity_id: uuid.UUID | None = None
    target_cpa: Decimal | None = None
    target_roas: Decimal | None = None
    target_revenue: Decimal | None = None
    target_profit: Decimal | None = None
    overrides: SimulationOverrideInput = Field(default_factory=SimulationOverrideInput)


# ---------------------------------------------------------------------------
# Simulation response
# ---------------------------------------------------------------------------


class SimulationRead(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    organization_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None = None
    model_version: str
    assumptions_hash: str
    model_used: str
    calculation_path: str
    assumptions: list[AssumptionRead] = Field(default_factory=list)
    reference_window: RangeRead | None = None
    scenarios: dict[str, ScenarioResultRead] = Field(default_factory=dict)
    break_even: BreakEvenRead = Field(default_factory=dict)
    profitability: ProfitabilityRead = Field(default_factory=ProfitabilityRead)
    sensitivity: list[SensitivityTableRead] = Field(default_factory=list)
    targets: list[TargetComparisonRead] = Field(default_factory=list)
    data_quality: str = "insufficient"
    evidence_strength: str = "insufficient"
    currency: str = "USD"
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    assumptions_snapshot: list[Any] = Field(default_factory=list)
    results_snapshot: dict[str, Any] = Field(default_factory=dict)


class SimulationSummaryRead(BaseModel):
    business_id: uuid.UUID
    total: int = 0
    simulations: list[SimulationRead] = Field(default_factory=list)


__all__ = [
    "AssumptionRead",
    "BreakEvenRead",
    "ProfitabilityRead",
    "ScenarioMetricsRead",
    "ScenarioResultRead",
    "SensitivityRowRead",
    "SensitivityTableRead",
    "SimulationCreateRequest",
    "SimulationOverrideInput",
    "SimulationRead",
    "SimulationSummaryRead",
    "TargetComparisonRead",
]
