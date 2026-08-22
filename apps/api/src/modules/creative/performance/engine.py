"""Pure deterministic creative performance engine (Phase 8C).

This module is PURE: no database access, no API calls, no LLM. It receives
explicit Decimal facts (aggregated by the service layer from the canonical
metrics view) and returns typed conclusions with explicit statuses.

Hard boundaries:

- No predicted numbers: every value is computed from observed facts.
- Missing data is ``unavailable`` / ``insufficient_data`` — never zero.
- KPI formulas are REUSED from the shared kpi_engine (no competing math);
  conversion-based ratios keep their Meta-reported source label because
  commerce purchases/revenue are never attributed at ad grain.
- Every conclusion carries evidence: observed values, threshold codes and
  named rule identifiers.
- Thresholds resolve only from the versioned registry (thresholds.py),
  which itself reuses the diagnostics baselines.

Rule sets are individually versioned so historical snapshots stay
interpretable after rules evolve.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.modules.creative.performance.thresholds import (
    CLASSIFICATION_MIN_DAYS,
    CTR_CRITICAL,
    CTR_LOW,
    DECLINE_PERCENT,
    FATIGUE_MIN_OBSERVATIONS,
    FATIGUE_WINDOW_DAYS,
    FREQUENCY_HIGH,
    SAMPLE_MIN_CLICKS,
    SAMPLE_MIN_CONVERSIONS,
    SAMPLE_MIN_IMPRESSIONS,
    SAMPLE_MIN_SPEND,
    SCALING_MIN_DAYS,
    TREND_DEADBAND_PERCENT,
    TREND_MIN_OBSERVATIONS,
    UNIT_COUNT,
    UNIT_DAYS,
    UNIT_MONEY,
    UNIT_MULTIPLIER,
    UNIT_RATIO,
)
from src.modules.creative.performance.thresholds import (
    value as threshold_value,
)
from src.modules.metrics.definitions import (
    PRECISION_PERCENT,
    PRECISION_RATE,
    PROVIDER_META,
)
from src.modules.metrics.kpi_engine import (
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_UNAVAILABLE,
    Comparison,
    Measure,
    cpa,
    cpc,
    cpm,
    ctr,
    cvr,
    roas,
)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")

RULES_PROVIDER = PROVIDER_META

FATIGUE_RULES_VERSION = "cfat-1"
CLASSIFICATION_RULES_VERSION = "cclass-1"
READINESS_RULES_VERSION = "cready-1"
COMPARISON_RULES_VERSION = "ccmp-1"

# --- Observed-fact provenance labels --------------------------------------

SOURCE_META_REPORTED = "meta_reported"
SOURCE_DERIVED = "derived"

_RAW_FACT_CODES: tuple[str, ...] = (
    "impressions",
    "reach",
    "clicks",
    "link_clicks",
    "landing_page_views",
    "spend",
    "conversions",
    "conversion_value",
)

_COUNT_CODES = frozenset(
    {"impressions", "reach", "clicks", "link_clicks", "landing_page_views", "conversions"}
)

# --- Status vocabularies ---------------------------------------------------

FATIGUE_HEALTHY = "healthy"
FATIGUE_WATCH = "watch"
FATIGUE_SIGNAL = "fatigue_signal"

CLASSIFICATION_INSUFFICIENT_DATA = "insufficient_data"
CLASSIFICATION_DEVELOPING = "developing"
CLASSIFICATION_STABLE = "stable"
CLASSIFICATION_UNDERPERFORMING = "underperforming"
CLASSIFICATION_STRONG = "strong"
CLASSIFICATION_FATIGUE_SIGNAL = "fatigue_signal"

READINESS_NOT_READY = "not_ready"
READINESS_INSUFFICIENT_DATA = "insufficient_data"
READINESS_READY_FOR_REVIEW = "ready_for_review"
READINESS_STRONG_CANDIDATE = "strong_candidate_for_review"
READINESS_FATIGUE_RISK = "fatigue_risk"

TREND_RISING = "rising"
TREND_STABLE = "stable"
TREND_FALLING = "falling"
TREND_UNAVAILABLE = "unavailable"


def _signal(
    code: str,
    value: Decimal | None,
    status: str,
    reason: str | None,
    unit: str,
    source: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "value": value,
        "status": status,
        "reason": reason,
        "unit": unit,
        "source": source,
    }


def _unit_for_code(code: str) -> str:
    if code in _COUNT_CODES:
        return UNIT_COUNT
    if code in ("spend", "conversion_value", "cpc", "cpm"):
        return UNIT_MONEY
    if code in ("cpa",):
        return UNIT_MONEY
    return UNIT_RATIO


def _measure_to_signal(
    code: str, measure: Measure, *, unit: str, source: str
) -> dict[str, Any]:
    return _signal(code, measure.value, measure.status, measure.reason, unit, source)


def _frequency(impressions: Decimal | None, reach: Decimal | None) -> Measure:
    """frequency = impressions / reach (mirrors the diagnostics identity)."""
    if impressions is None or reach is None:
        return Measure.unavailable("no impressions/reach")
    im = Decimal(impressions)
    rc = Decimal(reach)
    if rc <= _ZERO:
        return Measure.unavailable("no reach")
    if im < _ZERO:
        return Measure.unavailable("negative impressions")
    return Measure((im / rc).quantize(PRECISION_RATE), STATUS_AVAILABLE)


# ---------------------------------------------------------------------------
# Signal extraction (8C.3)
# ---------------------------------------------------------------------------


def extract_signals(totals: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Signals for one observation period, computed ONLY from totals present.

    Raw facts carry provider-reported provenance. Derived ratios reuse the
    shared KPI engine; conversion-denominated ratios are suffixed ``_meta``
    and labelled meta_reported because commerce purchases/revenue are never
    attributed to ads.
    """
    signals: list[dict[str, Any]] = []
    for code in _RAW_FACT_CODES:
        value = totals.get(code)
        if value is None:
            signals.append(
                _signal(
                    code,
                    None,
                    STATUS_UNAVAILABLE,
                    "no observed facts",
                    _unit_for_code(code),
                    SOURCE_META_REPORTED,
                )
            )
        else:
            signals.append(
                _signal(
                    code,
                    Decimal(value),
                    STATUS_AVAILABLE,
                    None,
                    _unit_for_code(code),
                    SOURCE_META_REPORTED,
                )
            )

    signals.append(
        _measure_to_signal(
            "ctr",
            ctr(totals.get("clicks"), totals.get("impressions")),
            unit=UNIT_RATIO,
            source=SOURCE_DERIVED,
        )
    )
    signals.append(
        _measure_to_signal(
            "cpc",
            cpc(totals.get("spend"), totals.get("clicks")),
            unit=UNIT_MONEY,
            source=SOURCE_DERIVED,
        )
    )
    signals.append(
        _measure_to_signal(
            "cpm",
            cpm(totals.get("spend"), totals.get("impressions")),
            unit=UNIT_MONEY,
            source=SOURCE_DERIVED,
        )
    )
    # Meta-attribution only: conversions/conversion_value are provider
    # reported, never conflated with commerce orders.
    signals.append(
        _measure_to_signal(
            "cvr_meta",
            cvr(totals.get("conversions"), totals.get("clicks")),
            unit=UNIT_RATIO,
            source=SOURCE_META_REPORTED,
        )
    )
    signals.append(
        _measure_to_signal(
            "cpa_meta",
            cpa(totals.get("spend"), totals.get("conversions")),
            unit=UNIT_MONEY,
            source=SOURCE_META_REPORTED,
        )
    )
    signals.append(
        _measure_to_signal(
            "roas_meta",
            roas(totals.get("conversion_value"), totals.get("spend")),
            unit=UNIT_MULTIPLIER,
            source=SOURCE_META_REPORTED,
        )
    )
    signals.append(
        _measure_to_signal(
            "frequency",
            _frequency(
                None if totals.get("impressions") is None else Decimal(totals["impressions"]),
                None if totals.get("reach") is None else Decimal(totals["reach"]),
            ),
            unit=UNIT_MULTIPLIER,
            source=SOURCE_DERIVED,
        )
    )
    return signals


def signals_by_code(signals: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {signal["code"]: dict(signal) for signal in signals}


def signal_value(signals_map: Mapping[str, Mapping[str, Any]], code: str) -> Decimal | None:
    """Available value for a signal code, otherwise None."""
    entry = signals_map.get(code)
    if entry is None or entry.get("status") != STATUS_AVAILABLE or entry.get("value") is None:
        return None
    return Decimal(entry["value"])


# ---------------------------------------------------------------------------
# Aggregation helpers over daily rows
# ---------------------------------------------------------------------------


def _sum_rows(rows: Sequence[Mapping[str, Any]], code: str) -> Decimal | None:
    total = _ZERO
    seen = False
    for row in rows:
        value = row.get(code)
        if value is None:
            continue
        total += Decimal(value)
        seen = True
    return total if seen else None


def _window_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, Decimal | None]:
    return {code: _sum_rows(rows, code) for code in _RAW_FACT_CODES}


# ---------------------------------------------------------------------------
# Trend signal (8C.3) — half-split comparison inside the requested range
# ---------------------------------------------------------------------------


def trend_from_daily(daily_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministic trend: aggregate first half vs second half by date.

    Ratios are computed per half from aggregated numerators/denominators
    (never averaged). Direction uses the TREND_DEADBAND_PERCENT deadband.
    """
    rows = sorted(daily_rows, key=lambda row: row["date"])
    minimum = int(threshold_value(TREND_MIN_OBSERVATIONS))
    if len(rows) < minimum:
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "reason": f"requires at least {minimum} observed days",
            "metrics": {},
        }
    split = len(rows) - len(rows) // 2
    first_half, second_half = rows[:split], rows[split:]

    def _half_measure(half: Sequence[Mapping[str, Any]], code: str) -> Measure:
        if code == "ctr":
            return ctr(_sum_rows(half, "clicks"), _sum_rows(half, "impressions"))
        return Measure(_sum_rows(half, code), STATUS_AVAILABLE)

    metrics: dict[str, dict[str, Any]] = {}
    deadband = threshold_value(TREND_DEADBAND_PERCENT)
    for code in ("ctr", "spend"):
        previous = _half_measure(first_half, code)
        current = _half_measure(second_half, code)
        if previous.status != STATUS_AVAILABLE or current.status != STATUS_AVAILABLE:
            metrics[code] = {
                "direction": TREND_UNAVAILABLE,
                "comparison": Comparison.of(None, previous.value).__dict__,
            }
            continue
        comparison = Comparison.of(current.value, previous.value)
        percent = comparison.percentage_change
        if percent.status != STATUS_AVAILABLE:
            direction = TREND_UNAVAILABLE
        elif abs(percent.value) < deadband:
            direction = TREND_STABLE
        elif percent.value > _ZERO:
            direction = TREND_RISING
        else:
            direction = TREND_FALLING
        metrics[code] = {
            "direction": direction,
            "current": current.value,
            "previous": previous.value,
            "absolute_change": comparison.absolute_change,
            "percentage_change": percent,
        }
    return {"status": STATUS_AVAILABLE, "reason": None, "metrics": metrics}


# ---------------------------------------------------------------------------
# Fatigue detection (8C.5)
# ---------------------------------------------------------------------------


def detect_fatigue(range_end: date, daily_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Windowed fatigue detection from observed daily performance.

    Windows: recent = last FATIGUE_WINDOW_DAYS days ending at range_end;
    prior = the same length immediately before. Each window needs at least
    FATIGUE_MIN_OBSERVATIONS distinct observed days, otherwise the result
    is insufficient_data (never a guess).

    Signals (each recorded with evidence):
    - ctr_decline: window CTR fell by >= DECLINE_PERCENT percent
    - cost_escalation: CPA(meta) rose by >= DECLINE_PERCENT percent
      (both windows must have conversions > 0)
    - frequency_pressure: frequency >= FREQUENCY_HIGH AND increased

    Score: 0 -> healthy, 1 -> watch, >=2 -> fatigue_signal.
    """
    window = int(threshold_value(FATIGUE_WINDOW_DAYS))
    min_observed = int(threshold_value(FATIGUE_MIN_OBSERVATIONS))
    recent_start = range_end - timedelta(days=window - 1)
    prior_end = recent_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=window - 1)

    rows_by_date: dict[date, Mapping[str, Any]] = {}
    for row in daily_rows:
        rows_by_date[row["date"]] = row
    recent_dates = sorted(d for d in rows_by_date if recent_start <= d <= range_end)
    prior_dates = sorted(d for d in rows_by_date if prior_start <= d <= prior_end)

    windows_info = {
        "days": int(window),
        "min_observed": min_observed,
        "recent": {"start": recent_start, "end": range_end, "observed_days": len(recent_dates)},
        "prior": {"start": prior_start, "end": prior_end, "observed_days": len(prior_dates)},
    }

    if len(recent_dates) < min_observed or len(prior_dates) < min_observed:
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "reason": "fatigue requires observations in both windows",
            "score": None,
            "windows": windows_info,
            "signals": [],
            "rules_version": FATIGUE_RULES_VERSION,
        }

    recent = _window_totals([rows_by_date[d] for d in recent_dates])
    prior = _window_totals([rows_by_date[d] for d in prior_dates])

    ctr_recent = ctr(recent["clicks"], recent["impressions"])
    ctr_prior = ctr(prior["clicks"], prior["impressions"])
    cpa_recent = cpa(recent["spend"], recent["conversions"])
    cpa_prior = cpa(prior["spend"], prior["conversions"])
    freq_recent = _frequency(recent["impressions"], recent["reach"])
    freq_prior = _frequency(prior["impressions"], prior["reach"])

    def _relative_change(current: Measure, baseline: Measure) -> Measure:
        if current.status != STATUS_AVAILABLE or baseline.status != STATUS_AVAILABLE:
            return Measure.unavailable("baseline/current unavailable")
        base = Decimal(baseline.value)
        if base == _ZERO:
            return Measure.unavailable("baseline zero")
        change = (Decimal(current.value) - base) / base * _HUNDRED
        return Measure(change.quantize(PRECISION_PERCENT), STATUS_AVAILABLE)

    signals: list[dict[str, Any]] = []

    ctr_change = _relative_change(ctr_recent, ctr_prior)
    signals.append(
        {
            "code": "ctr_decline",
            "triggered": bool(
                ctr_change.status == STATUS_AVAILABLE
                and ctr_change.value <= -threshold_value(DECLINE_PERCENT)
            ),
            "evidence": {
                "metric": "ctr",
                "recent": ctr_recent.value,
                "prior": ctr_prior.value,
                "change_percent": ctr_change.value,
                "threshold_code": "decline_percent",
                "threshold_value": threshold_value(DECLINE_PERCENT),
                "operator": "lte",
                "applied_to": "-change_percent",
            },
        }
    )

    cost_change = _relative_change(cpa_recent, cpa_prior)
    signals.append(
        {
            "code": "cost_escalation",
            "triggered": bool(
                cost_change.status == STATUS_AVAILABLE
                and cost_change.value >= threshold_value(DECLINE_PERCENT)
            ),
            "evidence": {
                "metric": "cpa_meta",
                "recent": cpa_recent.value,
                "prior": cpa_prior.value,
                "change_percent": cost_change.value,
                "threshold_code": "decline_percent",
                "threshold_value": threshold_value(DECLINE_PERCENT),
                "operator": "gte",
                "applied_to": "change_percent",
            },
        }
    )

    freq_triggered = bool(
        freq_recent.status == STATUS_AVAILABLE
        and freq_prior.status == STATUS_AVAILABLE
        and freq_recent.value >= threshold_value(FREQUENCY_HIGH)
        and freq_recent.value > freq_prior.value
    )
    signals.append(
        {
            "code": "frequency_pressure",
            "triggered": freq_triggered,
            "evidence": {
                "metric": "frequency",
                "recent": freq_recent.value,
                "prior": freq_prior.value,
                "threshold_code": "frequency_high",
                "threshold_value": threshold_value(FREQUENCY_HIGH),
                "operator": "gte_and_increasing",
            },
        }
    )

    score = sum(1 for s in signals if s["triggered"])
    if score >= 2:
        status = FATIGUE_SIGNAL
    elif score == 1:
        status = FATIGUE_WATCH
    else:
        status = FATIGUE_HEALTHY

    return {
        "status": status,
        "reason": None,
        "score": score,
        "windows": windows_info,
        "signals": signals,
        "rules_version": FATIGUE_RULES_VERSION,
    }


# ---------------------------------------------------------------------------
# Classification (8C.6)
# ---------------------------------------------------------------------------


def classify(
    signals_map: Mapping[str, Mapping[str, Any]],
    *,
    days_covered: int,
    break_even_roas: Decimal | None,
    fatigue_status: str,
    ctr_trend_direction: str | None,
) -> dict[str, Any]:
    """Deterministic classification. Ordered rules, first match wins.

    R1 insufficient_data : volume/runway gate unmet
    R2 fatigue_signal    : fatigue engine reports fatigue_signal
    R3 underperforming   : negative economics OR critical-low CTR
    R4 strong            : healthy CTR AND conversion evidence AND
                           economics not negative AND trend not falling
    R5 developing        : volume met but runway below scaling minimum
    R6 stable            : everything else
    """
    evidence: list[dict[str, Any]] = []

    def _add_evidence(signal_code: str) -> None:
        entry = signals_map.get(signal_code)
        if entry is not None:
            evidence.append({"code": signal_code, "value": entry.get("value")})

    impressions = signal_value(signals_map, "impressions")
    spend = signal_value(signals_map, "spend")
    ctr_value = signal_value(signals_map, "ctr")
    conversions = signal_value(signals_map, "conversions")
    roas_value = signal_value(signals_map, "roas_meta")

    economics_negative = (
        roas_value is not None and break_even_roas is not None and roas_value < break_even_roas
    )

    # R1 — volume gate
    if (
        days_covered < int(threshold_value(CLASSIFICATION_MIN_DAYS))
        or impressions is None
        or impressions < threshold_value(SAMPLE_MIN_IMPRESSIONS)
        or spend is None
        or spend < threshold_value(SAMPLE_MIN_SPEND)
    ):
        _add_evidence("impressions")
        _add_evidence("spend")
        return _classification_result(
            CLASSIFICATION_INSUFFICIENT_DATA,
            "R1_volume_gate",
            ["volume gate unmet"],
            evidence,
        )

    # R2 — fatigue override
    if fatigue_status == FATIGUE_SIGNAL:
        return _classification_result(
            CLASSIFICATION_FATIGUE_SIGNAL,
            "R2_fatigue",
            ["fatigue engine reported fatigue_signal"],
            evidence,
        )

    # R3 — clear underperformance
    if economics_negative:
        _add_evidence("roas_meta")
        return _classification_result(
            CLASSIFICATION_UNDERPERFORMING,
            "R3_underperformance",
            ["meta ROAS below break-even"],
            evidence,
        )
    if ctr_value is not None and ctr_value < threshold_value(CTR_CRITICAL):
        _add_evidence("ctr")
        return _classification_result(
            CLASSIFICATION_UNDERPERFORMING,
            "R3_underperformance",
            ["CTR below critical floor"],
            evidence,
        )

    # R4 — strong with conversion evidence
    if (
        ctr_value is not None
        and ctr_value >= threshold_value(CTR_LOW)
        and conversions is not None
        and conversions >= threshold_value(SAMPLE_MIN_CONVERSIONS)
        and not economics_negative
        and ctr_trend_direction != TREND_FALLING
    ):
        _add_evidence("ctr")
        _add_evidence("conversions")
        _add_evidence("roas_meta")
        return _classification_result(
            CLASSIFICATION_STRONG,
            "R4_strong",
            ["CTR at/above low baseline", "conversion evidence present"],
            evidence,
        )

    # R5 — short runway
    if days_covered < int(threshold_value(SCALING_MIN_DAYS)):
        return _classification_result(
            CLASSIFICATION_DEVELOPING,
            "R5_short_runway",
            ["observed days below scaling minimum"],
            [{"code": "days_covered", "value": days_covered}],
        )

    # R6 — stable baseline
    return _classification_result(
        CLASSIFICATION_STABLE,
        "R6_baseline",
        ["volume sufficient, no stronger rule matched"],
        evidence,
    )


def _classification_result(
    status: str, rule: str, reasons: list[str], evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "status": status,
        "rule": rule,
        "reasons": reasons,
        "evidence": evidence,
        "rules_version": CLASSIFICATION_RULES_VERSION,
    }


# ---------------------------------------------------------------------------
# Scaling readiness (8C.7) — informational only, never an action
# ---------------------------------------------------------------------------


def scaling_readiness(
    signals_map: Mapping[str, Mapping[str, Any]],
    *,
    days_covered: int,
    fatigue_status: str,
    classification_status: str,
    break_even_roas: Decimal | None,
) -> dict[str, Any]:
    """Readiness-to-review signal. Ordered gates, first match wins.

    G1 insufficient_data          : evidence minima unmet (reuses the
                                    diagnostics scaling gates)
    G2 fatigue_risk               : fatigue watch/fatigue_signal
    G3 not_ready                  : known-negative economics
    G4 strong_candidate_for_review: classification strong
    G5 ready_for_review           : otherwise
    """
    impressions = signal_value(signals_map, "impressions")
    spend = signal_value(signals_map, "spend")
    conversions = signal_value(signals_map, "conversions")
    roas_value = signal_value(signals_map, "roas_meta")

    min_spend = threshold_value(SAMPLE_MIN_SPEND)
    min_impressions = threshold_value(SAMPLE_MIN_IMPRESSIONS)
    min_days = int(threshold_value(SCALING_MIN_DAYS))
    min_conversions = threshold_value(SAMPLE_MIN_CONVERSIONS)

    def _gate(
        code: str,
        value: Decimal | None,
        unit: str,
        minimum: Decimal | int,
    ) -> dict[str, Any]:
        met = value is not None and value >= minimum
        return {
            "code": code,
            "value": value,
            "unit": unit,
            "threshold_value": minimum,
            "met": bool(met),
        }

    gates: list[dict[str, Any]] = [
        _gate("sample_min_spend", spend, UNIT_MONEY, min_spend),
        _gate("sample_min_impressions", impressions, UNIT_COUNT, min_impressions),
        _gate("scaling_min_days", days_covered, UNIT_DAYS, min_days),
        _gate("sample_min_conversions", conversions, UNIT_COUNT, min_conversions),
    ]

    if not all(gate["met"] for gate in gates):
        return _readiness_result(READINESS_INSUFFICIENT_DATA, False, gates)
    if fatigue_status in (FATIGUE_WATCH, FATIGUE_SIGNAL):
        return _readiness_result(READINESS_FATIGUE_RISK, False, gates)
    if (
        roas_value is not None
        and break_even_roas is not None
        and roas_value < break_even_roas
    ):
        return _readiness_result(READINESS_NOT_READY, False, gates)
    if classification_status == CLASSIFICATION_STRONG:
        return _readiness_result(READINESS_STRONG_CANDIDATE, True, gates)
    return _readiness_result(READINESS_READY_FOR_REVIEW, True, gates)


def _readiness_result(
    status: str, ready_for_review: bool, gates: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "status": status,
        "ready_for_review": ready_for_review,
        "gates": gates,
        "rules_version": READINESS_RULES_VERSION,
    }


# ---------------------------------------------------------------------------
# Entity comparison (8C.4)
# ---------------------------------------------------------------------------

_COMPARISON_METRICS = ("ctr", "cvr_meta", "cpa_meta", "roas_meta")
_LOWER_IS_BETTER = frozenset({"cpa_meta"})
_COMPARISON_EXCLUDED_REASONS = {
    "impressions": "below sample_min_impressions",
    "clicks": "below sample_min_clicks",
}


def compare_entities(
    entries: Sequence[Mapping[str, Any]], primary_metric: str = "ctr"
) -> dict[str, Any]:
    """Deterministic ranking of entities on one primary metric.

    Entries failing the explicit minimum-data gates (sample impressions and
    sample clicks) are excluded with reasons — never silently dropped.
    Ties break by entity id (ascending), so the same inputs always produce
    the same order.
    """
    if primary_metric not in _COMPARISON_METRICS:
        raise ValueError(f"Unsupported comparison metric: {primary_metric}")
    lower_is_better = primary_metric in _LOWER_IS_BETTER

    ranked: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for entry in entries:
        entity = entry["entity"]
        signals_map = entry["signals"]
        impressions = signal_value(signals_map, "impressions")
        clicks = signal_value(signals_map, "clicks")

        failure_reasons: list[str] = []
        if impressions is None or impressions < threshold_value(SAMPLE_MIN_IMPRESSIONS):
            failure_reasons.append(_COMPARISON_EXCLUDED_REASONS["impressions"])
        if clicks is None or clicks < threshold_value(SAMPLE_MIN_CLICKS):
            failure_reasons.append(_COMPARISON_EXCLUDED_REASONS["clicks"])

        metric_value = signal_value(signals_map, primary_metric)
        if metric_value is None:
            failure_reasons.append(f"{primary_metric} unavailable")

        if failure_reasons:
            excluded.append({"entity": entity, "reasons": failure_reasons})
            continue
        ranked.append({"entity": entity, "value": metric_value})

    # Deterministic ordering: ties break by entity id ascending, so the
    # same inputs always produce the same order. Sort by id first, then a
    # stable sort by value in comparison direction.
    ranked.sort(key=lambda item: str(item["entity"]["id"]))
    ranked.sort(
        key=lambda item: item["value"],
        reverse=not lower_is_better,
    )

    for position, item in enumerate(ranked, start=1):
        item["rank"] = position

    spread: dict[str, Any] | None = None
    if len(ranked) >= 2:
        best = ranked[0]["value"]
        worst = ranked[-1]["value"]
        comparison = Comparison.of(best, worst)
        spread = {
            "best_entity_id": ranked[0]["entity"]["id"],
            "worst_entity_id": ranked[-1]["entity"]["id"],
            "absolute_change": comparison.absolute_change,
            "percentage_change": comparison.percentage_change.value
            if comparison.percentage_change.status == STATUS_AVAILABLE
            else None,
        }

    return {
        "primary_metric": primary_metric,
        "lower_is_better": lower_is_better,
        "gates": {
            "sample_min_impressions": threshold_value(SAMPLE_MIN_IMPRESSIONS),
            "sample_min_clicks": threshold_value(SAMPLE_MIN_CLICKS),
        },
        "ranked": ranked,
        "excluded": excluded,
        "spread": spread,
        "rules_version": COMPARISON_RULES_VERSION,
    }


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def fingerprint(payload: Mapping[str, Any]) -> str:
    """Stable sha256 fingerprint of a JSON-serializable payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_jsonable(value: Any) -> Any:
    """Recursively convert Decimals/dates/UUIDs into JSON-safe primitives."""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "FATIGUE_RULES_VERSION",
    "CLASSIFICATION_RULES_VERSION",
    "READINESS_RULES_VERSION",
    "COMPARISON_RULES_VERSION",
    "FATIGUE_HEALTHY",
    "FATIGUE_WATCH",
    "FATIGUE_SIGNAL",
    "CLASSIFICATION_INSUFFICIENT_DATA",
    "CLASSIFICATION_DEVELOPING",
    "CLASSIFICATION_STABLE",
    "CLASSIFICATION_UNDERPERFORMING",
    "CLASSIFICATION_STRONG",
    "CLASSIFICATION_FATIGUE_SIGNAL",
    "READINESS_NOT_READY",
    "READINESS_INSUFFICIENT_DATA",
    "READINESS_READY_FOR_REVIEW",
    "READINESS_STRONG_CANDIDATE",
    "READINESS_FATIGUE_RISK",
    "TREND_RISING",
    "TREND_STABLE",
    "TREND_FALLING",
    "TREND_UNAVAILABLE",
    "extract_signals",
    "signals_by_code",
    "signal_value",
    "trend_from_daily",
    "detect_fatigue",
    "classify",
    "scaling_readiness",
    "compare_entities",
    "fingerprint",
    "to_jsonable",
]
