"""Pure deterministic creative learning engine (Phase 8D).

This module is PURE: no database access, no API calls, no LLM. It
consumes Phase 8C entity results (signals, classification, fatigue,
provenance) as plain dicts and produces the learning hierarchy:

    OBSERVATION    - the 8C per-entity results themselves
    SIGNAL         - directional association of each metric vs the
                     in-scope baseline mean (deadband applied;
                     lower-is-better metrics inverted)
    PATTERN        - dimension groups (angle / hook / format / funnel
                     stage) with an explicit status ladder that includes
                     `conflicting`
    LEARNING       - evidence-strength-graded statements rendered from
                     observed numbers by deterministic templates
    RECOMMENDATION - typed, prioritized, review-only suggestions

Hard boundaries:

- no new KPI formulas: every number is a stored 8C signal value,
- no causal language: outputs describe observed associations only,
- missing data stays insufficient/None - never zero-filled,
- all weights and gates resolve from the versioned registries,
- engine output contains no timestamps (the service stamps persistence
  time), so identical inputs always produce identical reports.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from src.modules.creative.learning.thresholds import (
    CREATIVE_LEARNING_RULES_VERSION,
    LEARNING_CONFLICT_RATIO,
    LEARNING_MIN_ENTITIES,
    LEARNING_STABLE_MIN_ENTITIES,
    LEARNING_STALE_DAYS,
    PRIORITY_WEIGHT_CONCENTRATION_RISK,
    PRIORITY_WEIGHT_CONFLICTING_EVIDENCE,
    PRIORITY_WEIGHT_FATIGUE_SIGNAL,
    PRIORITY_WEIGHT_PATTERN_MODERATE,
    PRIORITY_WEIGHT_PATTERN_STRONG,
    PRIORITY_WEIGHT_PATTERN_WEAK,
    SAMPLE_MIN_IMPRESSIONS,
    SAMPLE_MIN_SPEND,
    TREND_DEADBAND_PERCENT,
    weight,
)
from src.modules.creative.performance.engine import (
    FATIGUE_SIGNAL,
    FATIGUE_WATCH,
    fingerprint,
    signal_value,
    signals_by_code,
)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")

# Metrics evaluated for directional signals. Polarity: True = higher is
# the positive direction for this metric.
_EVALUATED_METRICS: tuple[tuple[str, bool], ...] = (
    ("ctr", True),
    ("cpc", False),
    ("cpa_meta", False),
    ("roas_meta", True),
)

# Dimensions over which patterns are detected (context keys produced by
# Phase 8B/8C descriptors).
PATTERN_DIMENSIONS: tuple[str, ...] = (
    "angle",
    "hook_direction",
    "creative_format",
    "funnel_stage",
)

SIGNAL_POSITIVE = "positive"
SIGNAL_NEGATIVE = "negative"
SIGNAL_NEUTRAL = "neutral"
SIGNAL_INSUFFICIENT = "insufficient"

PATTERN_INSUFFICIENT_DATA = "insufficient_data"
PATTERN_CONFLICTING = "conflicting"
PATTERN_STALE = "stale"
PATTERN_STABLE = "stable"
PATTERN_SUPPORTED = "supported"
PATTERN_EMERGING = "emerging"

STRENGTH_STRONG = "strong"
STRENGTH_MODERATE = "moderate"
STRENGTH_WEAK = "weak"
STRENGTH_INSUFFICIENT = "insufficient"

REC_EXPLORE_MORE = "explore_more"
REC_EXPAND_ANGLE = "expand_angle"
REC_TEST_NEW_HOOK = "test_new_hook"
REC_TEST_NEW_FORMAT = "test_new_format"
REC_REFRESH_CREATIVE = "refresh_creative"
REC_INVESTIGATE_FATIGUE = "investigate_fatigue"
REC_REDUCE_CONCENTRATION = "reduce_concentration"
REC_INVESTIGATE_CONFLICTING = "investigate_conflicting_evidence"
REC_IMPROVE_COVERAGE = "improve_coverage"
REC_GATHER_MORE_EVIDENCE = "gather_more_evidence"

PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"


def _tv(code: str) -> Decimal:
    from src.modules.creative.learning.thresholds import value as threshold_value

    return threshold_value(code)


# ---------------------------------------------------------------------------
# Volume gate + baseline (OBSERVATION -> SIGNAL helpers)
# ---------------------------------------------------------------------------


def _passes_volume_gate(signals_map: Mapping[str, Mapping[str, Any]]) -> bool:
    impressions = signal_value(signals_map, "impressions")
    spend = signal_value(signals_map, "spend")
    return bool(
        impressions is not None
        and impressions >= _tv(SAMPLE_MIN_IMPRESSIONS)
        and spend is not None
        and spend >= _tv(SAMPLE_MIN_SPEND)
    )


def _metric_baseline(entries: Sequence[Mapping[str, Any]], code: str) -> Decimal | None:
    """In-scope baseline: Decimal mean of available values across entries
    passing the volume gate. None when no entry provides the metric."""
    values: list[Decimal] = []
    for entry in entries:
        if not _passes_volume_gate(entry["signals"]):
            continue
        value = signal_value(entry["signals"], code)
        if value is not None:
            values.append(value)
    if not values:
        return None
    return sum(values, _ZERO) / Decimal(len(values))


def _direction(
    value: Decimal | None, baseline: Decimal | None, higher_is_positive: bool
) -> str:
    if value is None or baseline is None:
        return SIGNAL_INSUFFICIENT
    deadband = _tv(TREND_DEADBAND_PERCENT)
    if baseline == _ZERO:
        return SIGNAL_INSUFFICIENT
    delta_percent = (value - baseline) / abs(baseline) * _HUNDRED
    if abs(delta_percent) < deadband:
        return SIGNAL_NEUTRAL
    positive_delta = delta_percent > _ZERO
    if higher_is_positive:
        return SIGNAL_POSITIVE if positive_delta else SIGNAL_NEGATIVE
    return SIGNAL_NEGATIVE if positive_delta else SIGNAL_POSITIVE


# ---------------------------------------------------------------------------
# Profiles (8D.4)
# ---------------------------------------------------------------------------


def build_profiles(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic per-entity learning profiles.

    Each input entry carries the 8C observation plus freshness:
    {entity, context, signals (list or map), classification_status,
     fatigue_status, days_covered, freshness_days}.
    """
    # Normalize signal lists (8C output) into lookup maps.
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        raw_signals = entry["signals"]
        signals_map = (
            signals_by_code(raw_signals) if isinstance(raw_signals, list) else raw_signals
        )
        normalized.append({**entry, "signals": signals_map})
    entries = normalized

    baselines = {code: _metric_baseline(entries, code) for code, _p in _EVALUATED_METRICS}

    profiles: list[dict[str, Any]] = []
    ordered = sorted(entries, key=lambda e: (e["entity"]["type"], e["entity"]["id"]))
    for entry in ordered:
        signals_map = entry["signals"]
        sufficient = _passes_volume_gate(signals_map)

        directions: dict[str, str] = {}
        for code, polarity in _EVALUATED_METRICS:
            directions[code] = _direction(
                signal_value(signals_map, code), baselines[code], polarity
            )

        strongest = _first_direction(directions, SIGNAL_POSITIVE)
        if strongest is None:
            strongest = _first_direction(directions, SIGNAL_NEUTRAL)
        weakest = _first_direction(directions, SIGNAL_NEGATIVE)

        internal_conflicts = sorted(
            code
            for code, _p in _EVALUATED_METRICS
            if code != "ctr"
            and directions.get(code) == SIGNAL_NEGATIVE
            and directions.get("ctr") == SIGNAL_POSITIVE
        )

        profiles.append(
            {
                "entity": dict(entry["entity"]),
                "context": dict(entry.get("context") or {}),
                "sufficiently_observed": sufficient,
                "days_covered": entry.get("days_covered"),
                "freshness_days": entry.get("freshness_days"),
                "signal_directions": directions,
                "baseline": {code: baselines[code] for code in baselines},
                "strongest_signal": strongest,
                "weakest_signal": weakest,
                "fatigue_status": entry.get("fatigue_status"),
                "classification_status": entry.get("classification_status"),
                "conflicting_internal_signals": internal_conflicts,
                "economics_available": signal_value(signals_map, "roas_meta") is not None,
            }
        )
    return profiles


def _first_direction(
    directions: Mapping[str, str], wanted: str
) -> dict[str, str] | None:
    for code, _polarity in _EVALUATED_METRICS:
        if directions.get(code) == wanted:
            return {"code": code, "direction": wanted}
    return None


# ---------------------------------------------------------------------------
# Pattern detection (8D.5 + 8D.6)
# ---------------------------------------------------------------------------


def detect_patterns(profiles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Dimension-grouped patterns with an explicit status ladder.

    Precedence (first match wins):
      conflicting > stale > insufficient_data > stable > supported >
      emerging

    A directional pattern only exists when at least
    LEARNING_MIN_ENTITIES members are sufficiently observed; below that
    the status is insufficient_data and carries no directional claim.
    """
    min_entities = int(_tv(LEARNING_MIN_ENTITIES))
    stable_min = int(_tv(LEARNING_STABLE_MIN_ENTITIES))
    stale_days = int(_tv(LEARNING_STALE_DAYS))
    conflict_ratio = _tv(LEARNING_CONFLICT_RATIO)

    patterns: list[dict[str, Any]] = []
    for dimension in PATTERN_DIMENSIONS:
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for profile in profiles:
            key = (profile.get("context") or {}).get(dimension)
            if key in (None, ""):
                continue
            groups.setdefault(str(key), []).append(profile)

        for group_value in sorted(groups):
            members = groups[group_value]
            sufficient_members = [m for m in members if m["sufficiently_observed"]]
            observed_entities = len(sufficient_members)

            positives = sum(
                1
                for m in sufficient_members
                if m["signal_directions"].get("ctr") == SIGNAL_POSITIVE
            )
            negatives = sum(
                1
                for m in sufficient_members
                if m["signal_directions"].get("ctr") == SIGNAL_NEGATIVE
            )
            neutrals = observed_entities - positives - negatives

            minority = min(positives, negatives)
            minority_share = (
                Decimal(minority) / Decimal(observed_entities)
                if observed_entities > 0
                else _ZERO
            )
            consistent = observed_entities > 0 and minority == 0
            if positives > negatives:
                dominant = SIGNAL_POSITIVE
            elif negatives > positives:
                dominant = SIGNAL_NEGATIVE
            else:
                dominant = SIGNAL_NEUTRAL

            max_freshness = max(
                (
                    m["freshness_days"]
                    for m in sufficient_members
                    if m.get("freshness_days") is not None
                ),
                default=None,
            )

            if observed_entities < min_entities:
                status = PATTERN_INSUFFICIENT_DATA
            elif minority_share >= conflict_ratio:
                status = PATTERN_CONFLICTING
            elif max_freshness is not None and max_freshness > stale_days:
                status = PATTERN_STALE
            elif observed_entities >= stable_min and consistent:
                status = PATTERN_STABLE
            elif consistent:
                status = PATTERN_SUPPORTED
            else:
                status = PATTERN_EMERGING

            patterns.append(
                {
                    "dimension": dimension,
                    "value": group_value,
                    "status": status,
                    "dominant_direction": (
                        dominant if status != PATTERN_INSUFFICIENT_DATA else None
                    ),
                    "metric": "ctr",
                    "observed_entities": observed_entities,
                    "total_entities": len(members),
                    "positive_count": positives,
                    "negative_count": negatives,
                    "neutral_count": neutrals,
                    "minority_share": minority_share.quantize(Decimal("0.0001")),
                    "max_freshness_days": max_freshness,
                    "supporting_entity_ids": _ids_with_direction(
                        sufficient_members, SIGNAL_POSITIVE
                    ),
                    "contradicting_entity_ids": _ids_with_direction(
                        sufficient_members, SIGNAL_NEGATIVE
                    ),
                    "evidence_strength": _pattern_strength(status),
                    "rules_version": CREATIVE_LEARNING_RULES_VERSION,
                }
            )

    patterns.sort(key=lambda p: (p["dimension"], p["value"]))
    return patterns


def _ids_with_direction(
    members: Sequence[Mapping[str, Any]], direction: str
) -> list[str]:
    return sorted(
        m["entity"]["id"]
        for m in members
        if m["signal_directions"].get("ctr") == direction
    )


def _pattern_strength(status: str) -> str:
    return {
        PATTERN_STABLE: STRENGTH_STRONG,
        PATTERN_SUPPORTED: STRENGTH_MODERATE,
        PATTERN_EMERGING: STRENGTH_WEAK,
        PATTERN_CONFLICTING: STRENGTH_WEAK,
        PATTERN_STALE: STRENGTH_MODERATE,
        PATTERN_INSUFFICIENT_DATA: STRENGTH_INSUFFICIENT,
    }[status]


# ---------------------------------------------------------------------------
# Learnings (8D.2 level 4) - deterministic statements from patterns
# ---------------------------------------------------------------------------


def build_learnings(patterns: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Evidence-backed learning records derived ONLY from patterns.

    Statements are deterministic templates over observed counts; they
    describe association, never causation.
    """
    learnings: list[dict[str, Any]] = []
    for pattern in patterns:
        if pattern["status"] == PATTERN_INSUFFICIENT_DATA:
            continue
        dominant = pattern["dominant_direction"]
        if dominant not in (SIGNAL_POSITIVE, SIGNAL_NEGATIVE):
            continue
        direction_word = "stronger" if dominant == SIGNAL_POSITIVE else "weaker"
        statement = (
            f"{pattern['value']} is associated with {direction_word} observed CTR "
            f"in {pattern['observed_entities']} sufficiently observed creative(s); "
            f"association observed, not causal."
        )
        learnings.append(
            {
                "dimension": pattern["dimension"],
                "value": pattern["value"],
                "learning_type": "metric_association",
                "statement": statement,
                "status": pattern["status"],
                "evidence_strength": pattern["evidence_strength"],
                "observed_entities": pattern["observed_entities"],
                "positive_count": pattern["positive_count"],
                "negative_count": pattern["negative_count"],
                "supporting_entity_ids": pattern["supporting_entity_ids"],
                "contradicting_entity_ids": pattern["contradicting_entity_ids"],
                "rules_version": CREATIVE_LEARNING_RULES_VERSION,
            }
        )
    learnings.sort(key=lambda item: (item["dimension"], item["value"]))
    return learnings


def conflicting_patterns(patterns: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Conflicts with explicit supporting/contradicting breakdown (8D.6).

    Conflicts are never averaged into a single directional claim; the
    caller receives both sides plus what additional observation would
    reduce the uncertainty.
    """
    conflicts = []
    for pattern in patterns:
        if pattern["status"] != PATTERN_CONFLICTING:
            continue
        conflicts.append(
            {
                "dimension": pattern["dimension"],
                "value": pattern["value"],
                "supporting": {
                    "count": pattern["positive_count"],
                    "entity_ids": pattern["supporting_entity_ids"],
                },
                "contradicting": {
                    "count": pattern["negative_count"],
                    "entity_ids": pattern["contradicting_entity_ids"],
                },
                "minority_share": pattern["minority_share"],
                "max_freshness_days": pattern["max_freshness_days"],
                "resolution_path": (
                    "observe additional creatives of this value with "
                    "sufficient volume to move the minority share below the "
                    "conflict ratio"
                ),
            }
        )
    return conflicts


# ---------------------------------------------------------------------------
# Portfolio intelligence (8D.11) - concentration/redundancy/coverage
# ---------------------------------------------------------------------------


def build_portfolio_intelligence(
    profiles: Sequence[Mapping[str, Any]],
    *,
    portfolio_roles: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Concentration, redundancy and coverage signals over contexts.

    ``portfolio_roles`` maps concept id -> list of {portfolio_id, role}
    assignments; when provided, exploration-vs-core balance is computed.
    """
    angle_counts: dict[str, int] = {}
    format_counts: dict[str, int] = {}
    hook_counts: dict[str, int] = {}
    total = len(profiles)

    for profile in profiles:
        context = profile.get("context") or {}
        angle = context.get("angle")
        fmt = context.get("creative_format")
        hook = context.get("hook_direction")
        if angle:
            angle_counts[str(angle)] = angle_counts.get(str(angle), 0) + 1
        if fmt:
            format_counts[str(fmt)] = format_counts.get(str(fmt), 0) + 1
        if hook:
            hook_counts[str(hook)] = hook_counts.get(str(hook), 0) + 1

    def _concentration(counts: Mapping[str, int]) -> dict[str, Any]:
        if total == 0 or not counts:
            return {"risk": False, "top_share": None, "distribution": {}}
        top_value = max(sorted(counts), key=lambda k: counts[k])
        share = Decimal(counts[top_value]) / Decimal(total)
        return {
            "risk": bool(share > Decimal("0.5")),
            "top_value": top_value,
            "top_share": share.quantize(Decimal("0.0001")),
            "distribution": dict(sorted(counts.items())),
        }

    role_balance: dict[str, int] | None = None
    if portfolio_roles is not None:
        role_balance = {"core": 0, "exploration": 0}
        for assignments in portfolio_roles.values():
            for assignment in assignments:
                role = str(assignment.get("role") or "").lower()
                if role in role_balance:
                    role_balance[role] += 1

    return {
        "concept_count": total,
        "angle_concentration": _concentration(angle_counts),
        "format_concentration": _concentration(format_counts),
        "hook_distribution": dict(sorted(hook_counts.items())),
        "role_balance": role_balance,
    }


def coverage_gaps(
    profiles: Sequence[Mapping[str, Any]],
    *,
    valid_hooks: Sequence[str],
    valid_formats: Sequence[str],
) -> list[dict[str, Any]]:
    """Canonical taxonomy values not yet covered by any concept context."""
    used_hooks = {
        str((p.get("context") or {}).get("hook_direction"))
        for p in profiles
        if (p.get("context") or {}).get("hook_direction")
    }
    used_formats = {
        str((p.get("context") or {}).get("creative_format"))
        for p in profiles
        if (p.get("context") or {}).get("creative_format")
    }
    gaps: list[dict[str, Any]] = []
    for hook in sorted(set(valid_hooks) - used_hooks):
        gaps.append({"dimension": "hook_direction", "value": hook})
    for fmt in sorted(set(valid_formats) - used_formats):
        gaps.append({"dimension": "creative_format", "value": fmt})
    return gaps


# ---------------------------------------------------------------------------
# Recommendations (8D.8 + 8D.9 + 8D.12)
# ---------------------------------------------------------------------------


def build_recommendations(
    profiles: Sequence[Mapping[str, Any]],
    patterns: Sequence[Mapping[str, Any]],
    portfolio: Mapping[str, Any],
    coverage: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Typed, evidence-backed, review-only recommendations.

    Deterministic priority: a named-weight sum (Decimal). Ties break by
    (type, affected ref). No randomness, no predictions, no actions.
    """
    recommendations: list[dict[str, Any]] = []

    def _add(
        rec_type: str,
        reason_code: str,
        statement: str,
        affected: Mapping[str, Any] | None,
        factors: Sequence[str],
        evidence_refs: Sequence[Mapping[str, Any]],
    ) -> None:
        score = _ZERO
        applied_weights: list[dict[str, Any]] = []
        for factor in factors:
            w = weight(factor)
            score += w
            applied_weights.append({"factor": factor, "weight": w})
        if score >= _tv("priority_high_min_score"):
            priority = PRIORITY_HIGH
        elif score >= _tv("priority_medium_min_score"):
            priority = PRIORITY_MEDIUM
        else:
            priority = PRIORITY_LOW
        recommendations.append(
            {
                "type": rec_type,
                "reason_code": reason_code,
                "statement": statement,
                "affected": dict(affected) if affected else None,
                "factors": applied_weights,
                "priority_score": score,
                "priority": priority,
                "evidence": [dict(ref) for ref in evidence_refs],
                "review_only": True,
                "status": "informational",
                "rules_version": CREATIVE_LEARNING_RULES_VERSION,
            }
        )

    # 1-2. Fatigue integration (8D.12): consume 8C fatigue statuses.
    for profile in profiles:
        fatigue = profile.get("fatigue_status")
        if fatigue == FATIGUE_SIGNAL:
            _add(
                REC_REFRESH_CREATIVE,
                "fatigue_signal_observed",
                "Fatigue signal observed on this creative; review a refresh "
                "(iteration on dimension values) rather than continued reuse.",
                profile["entity"],
                (PRIORITY_WEIGHT_FATIGUE_SIGNAL,),
                [
                    {
                        "kind": "fatigue_status",
                        "entity_id": profile["entity"]["id"],
                        "value": fatigue,
                    }
                ],
            )
        elif fatigue == FATIGUE_WATCH:
            _add(
                REC_INVESTIGATE_FATIGUE,
                "fatigue_watch_observed",
                "Early fatigue indicators observed on this creative; review "
                "the underlying windows before further reuse.",
                profile["entity"],
                (),
                [
                    {
                        "kind": "fatigue_status",
                        "entity_id": profile["entity"]["id"],
                        "value": fatigue,
                    }
                ],
            )

    # 3. Concentration risk from portfolio intelligence.
    angle_conc = portfolio.get("angle_concentration") or {}
    if angle_conc.get("risk"):
        _add(
            REC_REDUCE_CONCENTRATION,
            "angle_concentration_risk",
            f"Most concepts concentrate on angle '{angle_conc.get('top_value')}'; "
            "review diversification to preserve portfolio diversity.",
            {"dimension": "angle", "value": angle_conc.get("top_value")},
            (PRIORITY_WEIGHT_CONCENTRATION_RISK,),
            [{"kind": "concentration", "share": angle_conc.get("top_share")}],
        )

    # 4. Conflicting evidence investigation (8D.6).
    for pattern in patterns:
        if pattern["status"] != PATTERN_CONFLICTING:
            continue
        _add(
            REC_INVESTIGATE_CONFLICTING,
            "pattern_conflicting",
            "Contradicting observations exist for this value; additional "
            "observation is needed before drawing any directional "
            "conclusion.",
            {"dimension": pattern["dimension"], "value": pattern["value"]},
            (PRIORITY_WEIGHT_CONFLICTING_EVIDENCE,),
            [
                {
                    "kind": "conflicting_pattern",
                    "supporting_entity_ids": pattern["supporting_entity_ids"],
                    "contradicting_entity_ids": pattern["contradicting_entity_ids"],
                }
            ],
        )

    # 5-7. Positive association patterns (association language only).
    strength_weight = {
        STRENGTH_STRONG: PRIORITY_WEIGHT_PATTERN_STRONG,
        STRENGTH_MODERATE: PRIORITY_WEIGHT_PATTERN_MODERATE,
        STRENGTH_WEAK: PRIORITY_WEIGHT_PATTERN_WEAK,
    }
    for pattern in patterns:
        status = pattern["status"]
        if pattern["dominant_direction"] != SIGNAL_POSITIVE:
            continue
        if status not in (PATTERN_STABLE, PATTERN_SUPPORTED):
            continue
        factor = strength_weight[pattern["evidence_strength"]]
        base = {
            "dimension": pattern["dimension"],
            "value": pattern["value"],
        }
        refs = [{"kind": "pattern", **{k: pattern[k] for k in (
            "dimension", "value", "observed_entities", "evidence_strength"
        )}}]
        if pattern["dimension"] == "angle":
            _add(
                REC_EXPAND_ANGLE,
                "positive_angle_association",
                "This angle is associated with stronger observed CTR across "
                "sufficiently observed creatives; exploring more concepts "
                "with it preserves diversity elsewhere.",
                base,
                (factor,),
                refs,
            )
        elif pattern["dimension"] == "hook_direction":
            _add(
                REC_EXPLORE_MORE,
                "positive_hook_association",
                "This hook direction is associated with stronger observed "
                "CTR; reviewing additional hooks in the same direction is "
                "supported by current evidence.",
                base,
                (factor,),
                refs,
            )
        elif pattern["dimension"] == "creative_format":
            _add(
                REC_EXPLORE_MORE,
                "positive_format_association",
                "This format is associated with stronger observed CTR; "
                "additional formats of this kind may be worth reviewing.",
                base,
                (factor,),
                refs,
            )

    # 8. Emerging positive associations: gather more evidence.
    for pattern in patterns:
        if pattern["status"] == PATTERN_EMERGING and pattern[
            "dominant_direction"
        ] == SIGNAL_POSITIVE:
            _add(
                REC_GATHER_MORE_EVIDENCE,
                "emerging_positive_association",
                "An emerging positive association exists but observation "
                "volume is still limited; more sufficiently observed "
                "creatives are needed.",
                {"dimension": pattern["dimension"], "value": pattern["value"]},
                (PRIORITY_WEIGHT_PATTERN_WEAK,),
                [{"kind": "pattern", "observed_entities": pattern["observed_entities"]}],
            )

    # 9. Coverage gaps (canonical taxonomy values never used).
    for gap in list(coverage)[:5]:
        if gap["dimension"] == "hook_direction":
            rec_type = REC_TEST_NEW_HOOK
            statement = (
                "No concept uses this canonical hook direction yet; testing "
                "it would increase coverage."
            )
        else:
            rec_type = REC_TEST_NEW_FORMAT
            statement = (
                "No concept uses this canonical creative format yet; "
                "testing it would increase format coverage."
            )
        _add(rec_type, "coverage_gap", statement, gap, (), [dict(gap)])

    # Deterministic ordering: priority score desc, then type, then ref.
    def _sort_key(rec: Mapping[str, Any]) -> tuple[Any, ...]:
        affected = rec.get("affected") or {}
        return (
            -rec["priority_score"],
            str(affected.get("dimension", "")),
            str(affected.get("value", "")),
            rec["type"],
            str(affected.get("id", "")),
        )

    recommendations.sort(key=_sort_key)
    return recommendations


# ---------------------------------------------------------------------------
# Report assembly (8D.7 payload; fingerprinted for reproducibility)
# ---------------------------------------------------------------------------


def build_report(
    profiles: Sequence[Mapping[str, Any]],
    patterns: Sequence[Mapping[str, Any]],
    portfolio: Mapping[str, Any],
    coverage: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    # Deterministic profile order regardless of caller input order.
    ordered_profiles = sorted(
        profiles, key=lambda p: (p["entity"]["type"], p["entity"]["id"])
    )
    learnings = build_learnings(patterns)
    conflicts = conflicting_patterns(patterns)
    recommendations = build_recommendations(
        ordered_profiles, patterns, portfolio, coverage
    )

    summary = {
        "entities_total": len(ordered_profiles),
        "entities_sufficient": sum(
            1 for p in ordered_profiles if p["sufficiently_observed"]
        ),
        "patterns_total": len(patterns),
        "patterns_by_status": {
            status: sum(1 for p in patterns if p["status"] == status)
            for status in (
                PATTERN_STABLE,
                PATTERN_SUPPORTED,
                PATTERN_EMERGING,
                PATTERN_CONFLICTING,
                PATTERN_STALE,
                PATTERN_INSUFFICIENT_DATA,
            )
        },
        "learnings_total": len(learnings),
        "recommendations_total": len(recommendations),
        "learning_status": _overall_learning_status(patterns, profiles),
    }

    report = {
        "rules_versions": {
            "engine": CREATIVE_LEARNING_RULES_VERSION,
        },
        "summary": summary,
        "profiles": ordered_profiles,
        "patterns": list(patterns),
        "learnings": learnings,
        "conflicting_evidence": conflicts,
        "portfolio_intelligence": dict(portfolio),
        "coverage_gaps": list(coverage),
        "recommendations": recommendations,
    }
    report["fingerprint"] = fingerprint(to_jsonable_payload(report))
    return report


def _overall_learning_status(
    patterns: Sequence[Mapping[str, Any]], profiles: Sequence[Mapping[str, Any]]
) -> str:
    """Business-level learning status from the pattern set."""
    sufficient = sum(1 for p in profiles if p["sufficiently_observed"])
    if not profiles or sufficient < int(_tv(LEARNING_MIN_ENTITIES)):
        return PATTERN_INSUFFICIENT_DATA
    statuses = {p["status"] for p in patterns}
    if PATTERN_CONFLICTING in statuses:
        return PATTERN_CONFLICTING
    if PATTERN_STALE in statuses:
        return PATTERN_STALE
    if PATTERN_STABLE in statuses:
        return PATTERN_STABLE
    if PATTERN_SUPPORTED in statuses:
        return PATTERN_SUPPORTED
    if sufficient >= int(_tv(LEARNING_MIN_ENTITIES)):
        return PATTERN_EMERGING
    return PATTERN_INSUFFICIENT_DATA


def to_jsonable_payload(value: Any) -> Any:
    """Reuse the shared JSON-safe conversion (Decimal/date/UUID safe)."""
    from src.modules.creative.performance.engine import to_jsonable

    return to_jsonable(value)


__all__ = [
    "CREATIVE_LEARNING_RULES_VERSION",
    "PATTERN_DIMENSIONS",
    "SIGNAL_POSITIVE",
    "SIGNAL_NEGATIVE",
    "SIGNAL_NEUTRAL",
    "SIGNAL_INSUFFICIENT",
    "PATTERN_INSUFFICIENT_DATA",
    "PATTERN_CONFLICTING",
    "PATTERN_STALE",
    "PATTERN_STABLE",
    "PATTERN_SUPPORTED",
    "PATTERN_EMERGING",
    "build_profiles",
    "detect_patterns",
    "build_learnings",
    "conflicting_patterns",
    "build_portfolio_intelligence",
    "coverage_gaps",
    "build_recommendations",
    "build_report",
]
