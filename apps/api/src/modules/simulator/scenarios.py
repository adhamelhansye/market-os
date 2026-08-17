"""Scenario derivation (Phase 5A).

Scenarios are NOT blind ±20% guesses: downside / expected / upside are
derived from the historical distribution of the daily funnel ratios
(CTR, CPC, CPM, CVR, AOV, CPA) over the reference window using the
25th / 50th / 75th percentiles (nearest-rank, deterministic).

- `expected` always equals the window aggregate assumptions (what the
  user sees in the assumption list), so the numbers never disagree;
- `downside` / `upside` are the 25th / 75th percentiles of the daily
  ratio distributions. When fewer than 7 valid days exist, the tail
  scenarios are marked unavailable rather than invented.

Multi-currency: daily series are loaded restricted to the business
currency, exactly like every other canonical aggregation.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Business
from src.modules.metrics.aggregation import (
    Range,
    ad_timeseries,
    campaign_timeseries,
    commerce_timeseries,
)
from src.modules.simulator.constants import (
    ENTITY_TYPE_CAMPAIGN,
    MIN_OBSERVATIONS_WEAK,
    PERCENTILE_DOWNSIDE,
    PERCENTILE_UPSIDE,
    PRECISION_MONEY,
    PRECISION_RATE,
)
from src.modules.simulator.inputs import AssumptionSet

ZERO = Decimal("0")
THOUSAND = Decimal("1000")


@dataclass(frozen=True)
class DailyRatios:
    """Per-day funnel ratios over the reference window (sorted by date)."""

    dates: tuple[date, ...] = ()
    ctr: tuple[Decimal, ...] = ()
    cpc: tuple[Decimal, ...] = ()
    cpm: tuple[Decimal, ...] = ()
    cvr: tuple[Decimal, ...] = ()
    aov: tuple[Decimal, ...] = ()
    cpa: tuple[Decimal, ...] = ()

    def series_for(self, name: str) -> tuple[Decimal, ...]:
        return getattr(self, name)


@dataclass(frozen=True)
class LevelValues:
    """One scenario level's ratio values (all optional, never fabricated)."""

    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cpm: Decimal | None = None
    cvr: Decimal | None = None
    aov: Decimal | None = None
    cpa: Decimal | None = None


@dataclass(frozen=True)
class ScenarioProfile:
    """Deterministic per-level values for the funnel's ratio inputs."""

    downside: LevelValues
    expected: LevelValues
    upside: LevelValues

    def level(self, name: str) -> LevelValues:
        return {
            "downside": self.downside,
            "expected": self.expected,
            "upside": self.upside,
        }[name]


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == ZERO:
        return None
    return numerator / denominator


def _quantize(value: Decimal | None, precision: Decimal) -> Decimal | None:
    return value.quantize(precision) if value is not None else None


def percentile(values: tuple[Decimal, ...], q: Decimal) -> Decimal | None:
    """Nearest-rank percentile, deterministic (sorted ascending)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(q / Decimal("100") * Decimal(len(ordered)))
    rank = max(1, min(rank, len(ordered)))
    return ordered[rank - 1]


async def load_daily_ratios(
    session: AsyncSession,
    business: Business,
    window: Range,
    *,
    entity_type: str,
    entity_id: uuid.UUID | None,
) -> DailyRatios:
    """Load daily funnel ratios for the reference window.

    Advertising series are campaign-scoped when simulating a campaign;
    commerce series (purchases / revenue / refunds) are always
    business-scoped — the canonical layer has no per-campaign orders.
    """
    if entity_type == ENTITY_TYPE_CAMPAIGN and entity_id is not None:
        ad_rows = await campaign_timeseries(
            session,
            business.id,
            window,
            currency=business.currency,
            campaign_id=entity_id,
        )
    else:
        ad_rows = await ad_timeseries(session, business.id, window, currency=business.currency)
    commerce_rows = await commerce_timeseries(
        session, business.id, window, currency=business.currency
    )

    ad_by_day: dict[date, dict] = {
        row["date"]: row for row in ad_rows if row.get("date") is not None
    }
    commerce_by_day: dict[date, dict] = {
        row["date"]: row for row in commerce_rows if row.get("date") is not None
    }

    dates: list[date] = []
    ctr: list[Decimal] = []
    cpc: list[Decimal] = []
    cpm: list[Decimal] = []
    cvr: list[Decimal] = []
    aov: list[Decimal] = []
    cpa: list[Decimal] = []

    for day in sorted(set(ad_by_day) | set(commerce_by_day)):
        ad = ad_by_day.get(day, {})
        com = commerce_by_day.get(day, {})
        spend = ad.get("spend")
        impressions = ad.get("impressions")
        clicks = ad.get("clicks")
        purchases = com.get("purchases")
        revenue = com.get("revenue")

        spend = Decimal(str(spend)) if spend is not None else None
        impressions = Decimal(str(impressions)) if impressions is not None else None
        clicks = Decimal(str(clicks)) if clicks is not None else None
        purchases = Decimal(str(purchases)) if purchases is not None else None
        revenue = Decimal(str(revenue)) if revenue is not None else None

        if impressions is not None and impressions > ZERO and clicks is not None:
            ctr.append((clicks / impressions).quantize(PRECISION_RATE))
            cpm.append((spend / impressions * THOUSAND).quantize(PRECISION_MONEY))
        if spend is not None and spend > ZERO and clicks is not None:
            cpc.append((spend / clicks).quantize(PRECISION_MONEY))
        if clicks is not None and clicks > ZERO and purchases is not None:
            cvr.append((purchases / clicks).quantize(PRECISION_RATE))
        if purchases is not None and purchases > ZERO and revenue is not None:
            aov.append((revenue / purchases).quantize(PRECISION_MONEY))
        if purchases is not None and purchases > ZERO and spend is not None:
            cpa.append((spend / purchases).quantize(PRECISION_MONEY))

        has_any = any(
            value is not None for value in (spend, impressions, clicks, purchases, revenue)
        )
        if has_any:
            dates.append(day)

    return DailyRatios(
        dates=tuple(dates),
        ctr=tuple(ctr),
        cpc=tuple(cpc),
        cpm=tuple(cpm),
        cvr=tuple(cvr),
        aov=tuple(aov),
        cpa=tuple(cpa),
    )


def _tails(series: tuple[Decimal, ...]) -> tuple[Decimal | None, Decimal | None]:
    """(downside, upside) percentile values, unavailable below 7 days."""
    if len(series) < MIN_OBSERVATIONS_WEAK:
        return None, None
    return (
        percentile(series, PERCENTILE_DOWNSIDE),
        percentile(series, PERCENTILE_UPSIDE),
    )


def build_scenario_profile(assumptions: AssumptionSet, daily: DailyRatios) -> ScenarioProfile:
    """Derive the scenario profile from assumptions + daily distribution.

    Expected always mirrors the assumption set (single source of truth
    for what the user sees). Downside / upside use the 25th / 75th
    percentiles of the daily series when enough evidence exists.
    """
    down_ctr, up_ctr = _tails(daily.ctr)
    down_cpc, up_cpc = _tails(daily.cpc)
    down_cpm, up_cpm = _tails(daily.cpm)
    down_cvr, up_cvr = _tails(daily.cvr)
    down_aov, up_aov = _tails(daily.aov)
    down_cpa, up_cpa = _tails(daily.cpa)

    return ScenarioProfile(
        downside=LevelValues(
            ctr=down_ctr,
            cpc=down_cpc,
            cpm=down_cpm,
            cvr=down_cvr,
            aov=down_aov,
            cpa=down_cpa,
        ),
        expected=LevelValues(
            ctr=assumptions.ctr.value,
            cpc=assumptions.cpc.value,
            cpm=assumptions.cpm.value,
            cvr=assumptions.cvr.value,
            aov=assumptions.aov.value,
            cpa=assumptions.cpa.value,
        ),
        upside=LevelValues(
            ctr=up_ctr,
            cpc=up_cpc,
            cpm=up_cpm,
            cvr=up_cvr,
            aov=up_aov,
            cpa=up_cpa,
        ),
    )


def best_observation_count(daily: DailyRatios) -> int:
    """Largest number of valid daily observations across the ratio series.

    Used to grade evidence strength: percentiles are only meaningful
    once at least `MIN_OBSERVATIONS_WEAK` valid days exist.
    """
    return max(
        (
            len(daily.ctr),
            len(daily.cpc),
            len(daily.cpm),
            len(daily.cvr),
            len(daily.aov),
            len(daily.cpa),
        ),
        default=0,
    )


__all__ = [
    "DailyRatios",
    "LevelValues",
    "ScenarioProfile",
    "best_observation_count",
    "build_scenario_profile",
    "load_daily_ratios",
    "percentile",
]
