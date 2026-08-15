"""Deterministic KPI engine.

This module is PURE: no database access, no API calls, no LLM. It receives
explicit Decimal numerators and denominators and returns typed measures with
an explicit status.

ZERO vs UNAVAILABLE:

- numerator/reportdenominator = 0 with a present partner → the value is
  computed and status is `available` (e.g. CTR 0 with 1000 impressions and
  0 clicks is a real zero).
- denominator is 0 or missing → the value is `unavailable` (with reason),
  never a fabricated zero and never Infinity.
- negative inputs are rejected as `invalid` (database constraints already
  forbid them; this is a defensive contract).
- nothing is available for a period that has no facts at all → the caller
  marks `insufficient_data`.

Period KPIs are ALWAYS computed from aggregated numerators/denominators
(total spend / total purchases, ...). Averaging daily or per-campaign
ratios is a bug and is tested against.

Rounding: full Decimal arithmetic, quantized only at the output boundary
(see definitions.PRECISION_*).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from src.modules.metrics.definitions import (
    PRECISION_MONEY,
    PRECISION_PERCENT,
    PRECISION_RATE,
)

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_INVALID = "invalid"

_ZERO = Decimal("0")


@dataclass(frozen=True)
class Measure:
    """A KPI value with an explicit status and reason.

    `value` is NULL whenever status is not `available`.
    """

    value: Decimal | None
    status: str = STATUS_AVAILABLE
    reason: str | None = None

    @classmethod
    def unavailable(cls, reason: str) -> Measure:
        return cls(value=None, status=STATUS_UNAVAILABLE, reason=reason)

    @classmethod
    def invalid(cls, reason: str) -> Measure:
        return cls(value=None, status=STATUS_INVALID, reason=reason)


def _decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Non-numeric input to KPI engine: {value!r}") from None


def _terms(numerator, denominator) -> tuple[Decimal, Decimal]:
    """Normalize inputs and reject negatives (defensive contract)."""
    num = _decimal(numerator)
    den = _decimal(denominator)
    for value, name in ((num, "numerator"), (den, "denominator")):
        if value < _ZERO:
            raise ValueError(f"Negative {name} passed to KPI engine")
    return num, den


def _ratio(
    numerator: Decimal | None,
    denominator: Decimal | None,
    *,
    numerator_label: str,
    denominator_label: str,
    precision: Decimal = PRECISION_RATE,
) -> Measure:
    """Shared safe ratio: zero denominator is unavailable, not Infinity.

    `precision` is the output quantization: money KPIs pass PRECISION_MONEY,
    ratios PRECISION_RATE (see definitions.PRECISION_*). Full Decimal
    arithmetic is performed before quantization.
    """
    if numerator is None:
        return Measure.unavailable(f"no {numerator_label}")
    if denominator is None:
        return Measure.unavailable(f"no {denominator_label}")
    num, den = _terms(numerator, denominator)
    if den == _ZERO:
        return Measure.unavailable(f"no {denominator_label}")
    if num == _ZERO:
        return Measure(value=_ZERO.quantize(precision), status=STATUS_AVAILABLE)
    return Measure(quantize(Decimal(num) / den, precision), STATUS_AVAILABLE)


def quantize(value: Decimal, precision: Decimal) -> Decimal:
    return value.quantize(precision)


def ctr(clicks, impressions) -> Measure:
    """CTR = clicks / impressions (ratio, 0 available; 0 impressions unavailable)."""
    return _ratio(clicks, impressions, numerator_label="clicks", denominator_label="impressions")


def cpc(spend, clicks) -> Measure:
    """CPC = spend / clicks (money per click)."""
    return _ratio(
        spend,
        clicks,
        numerator_label="spend",
        denominator_label="clicks",
        precision=PRECISION_MONEY,
    )


def cpm(spend, impressions) -> Measure:
    """CPM = spend / impressions × 1000 (money per thousand impressions)."""
    if spend is None:
        return Measure.unavailable("no spend")
    if impressions is None:
        return Measure.unavailable("no impressions")
    num, den = _terms(spend, impressions)
    if den == _ZERO:
        return Measure.unavailable("no impressions")
    value = (num / den * Decimal("1000")).quantize(PRECISION_MONEY)
    return Measure(value, STATUS_AVAILABLE)


def cvr(purchases, clicks) -> Measure:
    """CVR = purchases / clicks. The denominator is clicks, never swapped to sessions."""
    return _ratio(purchases, clicks, numerator_label="purchases", denominator_label="clicks")


def cpa(spend, purchases) -> Measure:
    """CPA = spend / purchases (money)."""
    return _ratio(
        spend,
        purchases,
        numerator_label="spend",
        denominator_label="purchases",
        precision=PRECISION_MONEY,
    )


def aov(revenue, purchases) -> Measure:
    """AOV = revenue / purchases (money)."""
    return _ratio(
        revenue,
        purchases,
        numerator_label="revenue",
        denominator_label="purchases",
        precision=PRECISION_MONEY,
    )


def roas(revenue, spend) -> Measure:
    """ROAS = revenue / spend (multiplier). Zero spend is unavailable, never Infinity."""
    return _ratio(revenue, spend, numerator_label="revenue", denominator_label="spend")


def mer(revenue, spend) -> Measure:
    """MER = business revenue / advertising spend (multiplier, blended)."""
    return _ratio(revenue, spend, numerator_label="business revenue", denominator_label="ad spend")


def contribution_margin(profit, revenue) -> Measure:
    """contribution_margin = contribution_profit / revenue (ratio)."""
    return _ratio(
        profit,
        revenue,
        numerator_label="contribution profit",
        denominator_label="revenue",
    )


_REASON_PREVIOUS_ZERO = "previous period is zero"
_REASON_NO_PREVIOUS = "no previous period data"
_REASON_NO_CURRENT = "no current period data"


@dataclass(frozen=True)
class Comparison:
    """Current vs previous with absolute and percent change.

    percentage_change is unavailable when there is no previous value or the
    previous value is zero (never a fabricated percent).
    """

    current: Decimal | None
    previous: Decimal | None
    absolute_change: Decimal | None
    percentage_change: Measure

    @classmethod
    def of(cls, current: Decimal | None, previous: Decimal | None) -> Comparison:
        if current is None:
            return cls(None, previous, None, Measure.unavailable(_REASON_NO_CURRENT))
        if previous is None:
            return cls(current, None, None, Measure.unavailable(_REASON_NO_PREVIOUS))
        current = _decimal(current)
        previous = _decimal(previous)
        absolute = current - previous
        if previous == _ZERO:
            return cls(
                current,
                previous,
                absolute,
                Measure.unavailable(_REASON_PREVIOUS_ZERO),
            )
        change_percent = (absolute / abs(previous) * Decimal("100")).quantize(PRECISION_PERCENT)
        return cls(current, previous, absolute, Measure(change_percent, STATUS_AVAILABLE))


def funnel_transition(current: Decimal | None, previous: Decimal | None) -> Measure:
    """conversion_rate for one funnel step = current / previous."""
    return _ratio(
        current, previous, numerator_label="current stage", denominator_label="previous stage"
    )


def dropoff_rate(current: Decimal | None, previous: Decimal | None) -> Measure:
    """dropoff_rate = 1 - (current / previous)."""
    conversion = funnel_transition(current, previous)
    if conversion.status != STATUS_AVAILABLE:
        return conversion
    value = (Decimal("1") - conversion.value).quantize(PRECISION_RATE)
    return Measure(value, STATUS_AVAILABLE)
