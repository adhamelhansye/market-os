"""Simulator inputs — building assumptions from historical evidence.

The simulator consumes internal normalized data (metrics aggregation,
economics profile) and explicit user overrides. Assumptions are
structured objects with provenance so the user can see where every
number came from.

Priority:

    explicit user override
    >
    campaign-level historical evidence
    >
    business-level historical evidence
    >
    unit economics profile
    >
    unavailable (never invented)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Business
from src.modules.economics.service import summary_data
from src.modules.metrics import aggregation
from src.modules.metrics.aggregation import Range
from src.modules.simulator.constants import (
    ALLOWED_HISTORICAL_WINDOWS,
    DATA_QUALITY_INSUFFICIENT,
    DATA_QUALITY_MODERATE,
    DATA_QUALITY_STRONG,
    DATA_QUALITY_WEAK,
    ENTITY_TYPE_CAMPAIGN,
    MIN_OBSERVATIONS_MODERATE,
    MIN_OBSERVATIONS_STRONG,
    MIN_OBSERVATIONS_WEAK,
    PRECISION_MONEY,
    PRECISION_RATE,
    SOURCE_BUSINESS_HISTORY,
    SOURCE_CAMPAIGN_HISTORY,
    SOURCE_ECONOMICS,
    SOURCE_SYSTEM_DEFAULT,
    SOURCE_USER_INPUT,
)
from src.modules.simulator.errors import SimulatorFilterError
from src.modules.simulator.schemas import (
    AssumptionRead,
    RangeRead,
    SimulationOverrideInput,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")
THOUSAND = Decimal("1000")


@dataclass(frozen=True)
class HistoricalSummary:
    """Aggregated historical facts from canonical metric_facts."""

    impressions: Decimal | None = None
    clicks: Decimal | None = None
    spend: Decimal | None = None
    purchases: Decimal | None = None
    revenue: Decimal | None = None
    conversions: Decimal | None = None
    conversion_value: Decimal | None = None
    refunds: Decimal | None = None
    observation_days: int = 0


@dataclass(frozen=True)
class AssumptionSet:
    """The complete set of assumptions for a simulation, each with provenance."""

    budget: AssumptionValue
    ctr: AssumptionValue
    cpc: AssumptionValue
    cpm: AssumptionValue
    cvr: AssumptionValue
    aov: AssumptionValue
    cpa: AssumptionValue
    refund_rate: AssumptionValue
    contribution_profit_per_order: AssumptionValue
    break_even_cpa: AssumptionValue
    break_even_roas: AssumptionValue
    reference_window_start: date | None
    reference_window_end: date | None

    def all_assumptions(self) -> list[AssumptionValue]:
        return [
            self.budget,
            self.ctr,
            self.cpc,
            self.cpm,
            self.cvr,
            self.aov,
            self.cpa,
            self.refund_rate,
            self.contribution_profit_per_order,
            self.break_even_cpa,
            self.break_even_roas,
        ]

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self.all_assumptions()]


@dataclass(frozen=True)
class AssumptionValue:
    name: str
    value: Decimal | None
    unit: str
    source: str
    source_entity: str | None = None
    historical_value: Decimal | None = None
    override: bool = False
    confidence: str = "insufficient"
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": str(self.value) if self.value is not None else None,
            "unit": self.unit,
            "source": self.source,
            "source_entity": self.source_entity,
            "historical_value": (
                str(self.historical_value) if self.historical_value is not None else None
            ),
            "override": self.override,
            "confidence": self.confidence,
            "unavailable_reason": self.unavailable_reason,
        }

    def to_read(self, date_range: RangeRead | None = None) -> AssumptionRead:
        return AssumptionRead(
            name=self.name,
            value=self.value,
            unit=self.unit,
            source=self.source,
            source_entity=self.source_entity,
            historical_value=self.historical_value,
            override=self.override,
            confidence=self.confidence,
            date_range=date_range,
            unavailable_reason=self.unavailable_reason,
        )


def _confidence_for_observations(count: int) -> str:
    if count >= MIN_OBSERVATIONS_STRONG:
        return DATA_QUALITY_STRONG
    if count >= MIN_OBSERVATIONS_MODERATE:
        return DATA_QUALITY_MODERATE
    if count >= MIN_OBSERVATIONS_WEAK:
        return DATA_QUALITY_WEAK
    return DATA_QUALITY_INSUFFICIENT


def _resolve_window(today: date, *, window_days: int) -> Range:
    """Build a historical reference Range ending yesterday."""
    if window_days not in ALLOWED_HISTORICAL_WINDOWS:
        raise SimulatorFilterError(
            f"Unsupported historical_window_days: {window_days}. "
            f"Allowed: {sorted(ALLOWED_HISTORICAL_WINDOWS)}"
        )
    end = today - _date_delta(1)
    start = end - _date_delta(window_days - 1)
    return Range(kind="custom", start=start, end=end, previous_start=None, previous_end=None)


def _date_delta(days: int) -> Any:
    from datetime import timedelta

    return timedelta(days=days)


async def _load_historical(
    session: AsyncSession,
    business: Business,
    window: Range,
    *,
    entity_type: str,
    entity_id: uuid.UUID | None,
) -> tuple[HistoricalSummary, str, str | None]:
    """Load historical ad + commerce totals for the window.

    Returns (summary, source, source_entity_name). Source distinguishes
    campaign-level history from business-level history.
    """
    if entity_type == ENTITY_TYPE_CAMPAIGN and entity_id is not None:
        ad_totals = await aggregation.ad_totals(
            session,
            business.id,
            window,
            currency=business.currency,
            entity="campaign",
            entity_id=entity_id,
        )
        source = SOURCE_CAMPAIGN_HISTORY
        source_entity = "campaign"
    else:
        ad_totals = await aggregation.ad_totals(
            session, business.id, window, currency=business.currency
        )
        source = SOURCE_BUSINESS_HISTORY
        source_entity = None

    commerce_totals = await aggregation.commerce_totals(
        session, business.id, window, currency=business.currency
    )

    obs = int(ad_totals.get("rows", 0) or 0)

    impressions = _to_decimal(ad_totals.get("impressions"))
    clicks = _to_decimal(ad_totals.get("clicks"))
    spend = _to_decimal(ad_totals.get("spend"))
    conversions = _to_decimal(ad_totals.get("conversions"))
    conversion_value = _to_decimal(ad_totals.get("conversion_value"))

    purchases = _to_decimal(commerce_totals.get("purchases"))
    revenue = _to_decimal(commerce_totals.get("revenue"))
    refunds = _to_decimal(commerce_totals.get("refunds"))

    summary = HistoricalSummary(
        impressions=impressions,
        clicks=clicks,
        spend=spend,
        purchases=purchases,
        revenue=revenue,
        conversions=conversions,
        conversion_value=conversion_value,
        refunds=refunds,
        observation_days=obs,
    )
    return summary, source, source_entity


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == ZERO:
        return None
    return (numerator / denominator).quantize(PRECISION_RATE)


def _money_ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == ZERO:
        return None
    return (numerator / denominator).quantize(PRECISION_MONEY)


def _historical_ctr(h: HistoricalSummary) -> Decimal | None:
    return _ratio(h.clicks, h.impressions)


def _historical_cpc(h: HistoricalSummary) -> Decimal | None:
    return _money_ratio(h.spend, h.clicks)


def _historical_cpm(h: HistoricalSummary) -> Decimal | None:
    if h.spend is None or h.impressions is None or h.impressions == ZERO:
        return None
    return (h.spend / h.impressions * THOUSAND).quantize(PRECISION_MONEY)


def _historical_cvr(h: HistoricalSummary) -> Decimal | None:
    return _ratio(h.purchases, h.clicks)


def _historical_aov(h: HistoricalSummary) -> Decimal | None:
    return _money_ratio(h.revenue, h.purchases)


def _historical_cpa(h: HistoricalSummary) -> Decimal | None:
    return _money_ratio(h.spend, h.purchases)


def _historical_refund_rate(h: HistoricalSummary) -> Decimal | None:
    if h.revenue is None or h.refunds is None or h.revenue == ZERO:
        return None
    return (h.refunds / h.revenue).quantize(PRECISION_RATE)


async def build_assumption_set(
    session: AsyncSession,
    business: Business,
    *,
    budget: Decimal,
    entity_type: str,
    entity_id: uuid.UUID | None,
    historical_window_days: int,
    overrides: SimulationOverrideInput,
    target_cpa: Decimal | None = None,
    target_roas: Decimal | None = None,
) -> AssumptionSet:
    """Build the complete assumption set for a simulation.

    Resolution priority:
      1. explicit user override (source = user_input)
      2. campaign history (source = campaign_history)
      3. business history (source = business_history)
      4. unit economics profile (source = economics)
      5. goal targets (source = goal, for target-only fields)
      6. unavailable (never fabricated)
    """
    today = date.today()

    if historical_window_days not in ALLOWED_HISTORICAL_WINDOWS:
        raise SimulatorFilterError(
            f"Unsupported historical_window_days: {historical_window_days}. "
            f"Allowed: {sorted(ALLOWED_HISTORICAL_WINDOWS)}"
        )

    window = _resolve_window(today, window_days=historical_window_days)
    history, hist_source, hist_entity = await _load_historical(
        session, business, window, entity_type=entity_type, entity_id=entity_id
    )

    confidence = _confidence_for_observations(history.observation_days)

    # Budget — always user_input (the scenario spend)
    budget_assumption = AssumptionValue(
        name="budget",
        value=budget.quantize(PRECISION_MONEY) if budget is not None else None,
        unit="money",
        source=SOURCE_USER_INPUT,
        override=True,
        confidence=DATA_QUALITY_STRONG,
    )

    # CTR
    hist_ctr = _historical_ctr(history)
    if overrides.ctr is not None:
        ctr_assumption = AssumptionValue(
            name="ctr",
            value=overrides.ctr.quantize(PRECISION_RATE),
            unit="ratio",
            source=SOURCE_USER_INPUT,
            historical_value=hist_ctr,
            override=True,
            confidence=DATA_QUALITY_STRONG,
        )
    elif hist_ctr is not None:
        ctr_assumption = AssumptionValue(
            name="ctr",
            value=hist_ctr,
            unit="ratio",
            source=hist_source,
            source_entity=hist_entity,
            historical_value=hist_ctr,
            override=False,
            confidence=confidence,
        )
    else:
        ctr_assumption = AssumptionValue(
            name="ctr",
            value=None,
            unit="ratio",
            source=SOURCE_SYSTEM_DEFAULT,
            override=False,
            confidence=DATA_QUALITY_INSUFFICIENT,
            unavailable_reason="no historical impressions or clicks",
        )

    # CPC
    hist_cpc = _historical_cpc(history)
    if overrides.cpc is not None:
        cpc_assumption = AssumptionValue(
            name="cpc",
            value=overrides.cpc.quantize(PRECISION_MONEY),
            unit="money",
            source=SOURCE_USER_INPUT,
            historical_value=hist_cpc,
            override=True,
            confidence=DATA_QUALITY_STRONG,
        )
    elif hist_cpc is not None:
        cpc_assumption = AssumptionValue(
            name="cpc",
            value=hist_cpc,
            unit="money",
            source=hist_source,
            source_entity=hist_entity,
            historical_value=hist_cpc,
            override=False,
            confidence=confidence,
        )
    else:
        cpc_assumption = AssumptionValue(
            name="cpc",
            value=None,
            unit="money",
            source=SOURCE_SYSTEM_DEFAULT,
            override=False,
            confidence=DATA_QUALITY_INSUFFICIENT,
            unavailable_reason="no historical spend or clicks",
        )

    # CPM
    hist_cpm = _historical_cpm(history)
    if overrides.cpm is not None:
        cpm_assumption = AssumptionValue(
            name="cpm",
            value=overrides.cpm.quantize(PRECISION_MONEY),
            unit="money",
            source=SOURCE_USER_INPUT,
            historical_value=hist_cpm,
            override=True,
            confidence=DATA_QUALITY_STRONG,
        )
    elif hist_cpm is not None:
        cpm_assumption = AssumptionValue(
            name="cpm",
            value=hist_cpm,
            unit="money",
            source=hist_source,
            source_entity=hist_entity,
            historical_value=hist_cpm,
            override=False,
            confidence=confidence,
        )
    else:
        cpm_assumption = AssumptionValue(
            name="cpm",
            value=None,
            unit="money",
            source=SOURCE_SYSTEM_DEFAULT,
            override=False,
            confidence=DATA_QUALITY_INSUFFICIENT,
            unavailable_reason="no historical spend or impressions",
        )

    # CVR
    hist_cvr = _historical_cvr(history)
    if overrides.cvr is not None:
        cvr_assumption = AssumptionValue(
            name="cvr",
            value=overrides.cvr.quantize(PRECISION_RATE),
            unit="ratio",
            source=SOURCE_USER_INPUT,
            historical_value=hist_cvr,
            override=True,
            confidence=DATA_QUALITY_STRONG,
        )
    elif hist_cvr is not None:
        cvr_assumption = AssumptionValue(
            name="cvr",
            value=hist_cvr,
            unit="ratio",
            source=hist_source,
            source_entity=hist_entity,
            historical_value=hist_cvr,
            override=False,
            confidence=confidence,
        )
    else:
        cvr_assumption = AssumptionValue(
            name="cvr",
            value=None,
            unit="ratio",
            source=SOURCE_SYSTEM_DEFAULT,
            override=False,
            confidence=DATA_QUALITY_INSUFFICIENT,
            unavailable_reason="no historical purchases or clicks",
        )

    # AOV
    hist_aov = _historical_aov(history)
    if overrides.aov is not None:
        aov_assumption = AssumptionValue(
            name="aov",
            value=overrides.aov.quantize(PRECISION_MONEY),
            unit="money",
            source=SOURCE_USER_INPUT,
            historical_value=hist_aov,
            override=True,
            confidence=DATA_QUALITY_STRONG,
        )
    elif hist_aov is not None:
        aov_assumption = AssumptionValue(
            name="aov",
            value=hist_aov,
            unit="money",
            source=hist_source,
            source_entity=hist_entity,
            historical_value=hist_aov,
            override=False,
            confidence=confidence,
        )
    else:
        aov_assumption = AssumptionValue(
            name="aov",
            value=None,
            unit="money",
            source=SOURCE_SYSTEM_DEFAULT,
            override=False,
            confidence=DATA_QUALITY_INSUFFICIENT,
            unavailable_reason="no historical revenue or purchases",
        )

    # CPA — derived quantity (spend per purchase), no user override.
    # Only used by Model C when clicks/impressions evidence is missing.
    hist_cpa = _historical_cpa(history)
    if hist_cpa is not None:
        cpa_assumption = AssumptionValue(
            name="cpa",
            value=hist_cpa,
            unit="money",
            source=hist_source,
            source_entity=hist_entity,
            historical_value=hist_cpa,
            override=False,
            confidence=confidence,
        )
    else:
        cpa_assumption = AssumptionValue(
            name="cpa",
            value=None,
            unit="money",
            source=SOURCE_SYSTEM_DEFAULT,
            override=False,
            confidence=DATA_QUALITY_INSUFFICIENT,
            unavailable_reason="no historical spend or purchases",
        )

    # Refund rate
    hist_refund = _historical_refund_rate(history)
    if overrides.refund_rate is not None:
        refund_assumption = AssumptionValue(
            name="refund_rate",
            value=overrides.refund_rate.quantize(PRECISION_RATE),
            unit="ratio",
            source=SOURCE_USER_INPUT,
            historical_value=hist_refund,
            override=True,
            confidence=DATA_QUALITY_STRONG,
        )
    elif hist_refund is not None:
        refund_assumption = AssumptionValue(
            name="refund_rate",
            value=hist_refund,
            unit="ratio",
            source=hist_source,
            source_entity=hist_entity,
            historical_value=hist_refund,
            override=False,
            confidence=confidence,
        )
    else:
        refund_assumption = AssumptionValue(
            name="refund_rate",
            value=None,
            unit="ratio",
            source=SOURCE_SYSTEM_DEFAULT,
            override=False,
            confidence=DATA_QUALITY_INSUFFICIENT,
            unavailable_reason="no historical revenue or refunds",
        )

    # Unit economics per order — from economics profile
    econ_profile = await summary_data(session, business)
    avg_unit_profit = econ_profile.get("average_contribution_profit")
    be_cpa_range = econ_profile.get("break_even_cpa_range")
    be_roas = econ_profile.get("break_even_roas")

    if overrides.contribution_margin is not None:
        profit_per_order = AssumptionValue(
            name="contribution_profit_per_order",
            value=overrides.contribution_margin.quantize(PRECISION_MONEY),
            unit="money",
            source=SOURCE_USER_INPUT,
            override=True,
            confidence=DATA_QUALITY_STRONG,
        )
    elif avg_unit_profit is not None:
        profit_per_order = AssumptionValue(
            name="contribution_profit_per_order",
            value=avg_unit_profit,
            unit="money",
            source=SOURCE_ECONOMICS,
            override=False,
            confidence=DATA_QUALITY_STRONG,
        )
    else:
        profit_per_order = AssumptionValue(
            name="contribution_profit_per_order",
            value=None,
            unit="money",
            source=SOURCE_SYSTEM_DEFAULT,
            override=False,
            confidence=DATA_QUALITY_INSUFFICIENT,
            unavailable_reason="no unit economics configured",
        )

    break_even_cpa_value = be_cpa_range[0] if be_cpa_range else None
    break_even_cpa_assumption = AssumptionValue(
        name="break_even_cpa",
        value=break_even_cpa_value,
        unit="money",
        source=(SOURCE_ECONOMICS if break_even_cpa_value is not None else SOURCE_SYSTEM_DEFAULT),
        override=False,
        confidence=(confidence if break_even_cpa_value else DATA_QUALITY_INSUFFICIENT),
        unavailable_reason=None if break_even_cpa_value else "no unit economics",
    )

    break_even_roas_assumption = AssumptionValue(
        name="break_even_roas",
        value=be_roas,
        unit="ratio",
        source=(SOURCE_ECONOMICS if be_roas is not None else SOURCE_SYSTEM_DEFAULT),
        override=False,
        confidence=confidence if be_roas else DATA_QUALITY_INSUFFICIENT,
        unavailable_reason=None if be_roas else "no positive contribution profit",
    )

    return AssumptionSet(
        budget=budget_assumption,
        ctr=ctr_assumption,
        cpc=cpc_assumption,
        cpm=cpm_assumption,
        cvr=cvr_assumption,
        aov=aov_assumption,
        cpa=cpa_assumption,
        refund_rate=refund_assumption,
        contribution_profit_per_order=profit_per_order,
        break_even_cpa=break_even_cpa_assumption,
        break_even_roas=break_even_roas_assumption,
        reference_window_start=window.start,
        reference_window_end=window.end,
    )


__all__ = [
    "AssumptionSet",
    "AssumptionValue",
    "HistoricalSummary",
    "build_assumption_set",
]
