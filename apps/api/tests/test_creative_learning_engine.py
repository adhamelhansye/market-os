"""Deterministic learning engine tests (Phase 8D).

Covers: normal learning, insufficient data, stale data, conflicting
evidence, evidence strength grading, multi-entity patterns, fatigue
integration, concentration, coverage, recommendation prioritization,
deterministic ordering, snapshot reproducibility and Decimal precision.
"""

from decimal import Decimal

from src.modules.creative.learning import engine as le
from src.modules.creative.performance import engine as perf


def entry(
    entity_id,
    angle="A",
    ctr_val=0.02,
    *,
    fatigue="healthy",
    fresh=1,
    days=14,
    context_extra=None,
):
    totals = {
        "impressions": Decimal("20000"),
        "reach": Decimal("9000"),
        "clicks": Decimal(str(int(ctr_val * 10000))),
        "spend": Decimal("500"),
        "conversions": Decimal(10),
        "conversion_value": Decimal("800"),
    }
    context = {
        "angle": angle,
        "hook_direction": f"hook_{angle}",
        "creative_format": f"fmt_{angle}",
        "funnel_stage": "awareness",
    }
    if context_extra:
        context.update(context_extra)
    return {
        "entity": {"type": "creative_concept", "id": entity_id},
        "context": context,
        "signals": perf.extract_signals(totals),
        "classification_status": "stable",
        "fatigue_status": fatigue,
        "days_covered": days,
        "freshness_days": fresh,
    }


def scope(angles: dict[str, list[float]], **common):
    entries = [
        entry(f"{angle}-{i}", angle, ctr_val, **common)
        for angle, ctr_values in angles.items()
        for i, ctr_val in enumerate(ctr_values)
    ]
    profiles = le.build_profiles(entries)
    return entries, profiles, le.detect_patterns(profiles)


class TestSignalDirection:
    def test_positive_negative_vs_global_baseline(self):
        _e, profiles, _p = scope({"high": [0.024], "low": [0.012]})
        directions = {p["entity"]["id"]: p["signal_directions"]["ctr"] for p in profiles}
        assert directions["high-0"] == "positive"
        assert directions["low-0"] == "negative"

    def test_near_baseline_is_neutral(self):
        # Values within the deadband of each other produce no directional claim.
        _e, profiles, _p = scope({"flat": [0.0200, 0.0195]})
        assert all(p["signal_directions"]["ctr"] == "neutral" for p in profiles)

    def test_lower_is_better_metric_inverted(self):
        entries = [
            entry("cheap", "A", 0.02, context_extra=None),
            entry("pricey", "B", 0.02),
        ]
        # Give 'cheap' a lower CPC via lower spend.
        cheap_totals = {
            "impressions": Decimal("20000"),
            "clicks": Decimal("200"),
            "spend": Decimal("100"),
            "conversions": Decimal(10),
            "conversion_value": Decimal("800"),
        }
        entries[0]["signals"] = perf.extract_signals(cheap_totals)
        profiles = le.build_profiles(entries)
        d = {p["entity"]["id"]: p["signal_directions"]["cpc"] for p in profiles}
        assert d["cheap"] == "positive"  # lower cost is the positive direction
        assert d["pricey"] == "negative"

    def test_insufficient_volume_marked(self):
        totals = {
            "impressions": Decimal("10"),
            "clicks": Decimal("5"),
            "spend": Decimal("1"),
        }
        e = entry("tiny", "A", 0.05)
        e["signals"] = perf.extract_signals(totals)
        profile = le.build_profiles([e])[0]
        assert profile["sufficiently_observed"] is False


class TestPatternDetection:
    def test_stable_pattern_with_four_consistent_entities(self):
        _e, _pr, patterns = scope({"strong": [0.03, 0.031, 0.029, 0.032], "weak": [0.002]})
        strong = next(p for p in patterns if p["value"] == "strong")
        assert strong["status"] == "stable"
        assert strong["dominant_direction"] == "positive"
        assert strong["evidence_strength"] == "strong"

    def test_conflicting_evidence_not_averaged(self):
        _e, _pr, patterns = scope({"mixed": [0.030, 0.028, 0.008]})
        mixed = next(p for p in patterns if p["value"] == "mixed")
        # 2 positive vs 1 negative -> minority share 0.3333 < 0.35 -> emerging.
        # With a harder conflict the status flips; verify both sides recorded.
        assert mixed["positive_count"] == 2 and mixed["negative_count"] == 1

        _e2, _pr2, patterns2 = scope({"split": [0.030, 0.008, 0.009, 0.031]})
        split = next(p for p in patterns2 if p["value"] == "split")
        assert split["status"] == "conflicting"
        assert split["supporting_entity_ids"] and split["contradicting_entity_ids"]

    def test_stale_overrides_supported(self):
        _e, _pr, patterns = scope({"old": [0.03, 0.029]}, fresh=30)
        old = next(p for p in patterns if p["value"] == "old")
        assert old["status"] == "stale"

    def test_single_entity_is_insufficient(self):
        _e, _pr, patterns = scope({"lonely": [0.04]})
        lonely = next(p for p in patterns if p["value"] == "lonely")
        assert lonely["status"] == "insufficient_data"
        assert lonely["dominant_direction"] is None
        assert lonely["evidence_strength"] == "insufficient"

    def test_dimensions_independent(self):
        _e, _pr, patterns = scope({"a1": [0.03, 0.031], "a2": [0.004]})
        dims = {p["dimension"] for p in patterns}
        assert dims == set(le.PATTERN_DIMENSIONS)


class TestLearnings:
    def test_learning_statement_is_associational(self):
        _e, pr, patterns = scope({"good": [0.03, 0.031, 0.029, 0.032], "bad": [0.002]})
        learnings = le.build_learnings(patterns)
        good = next(item for item in learnings if item["value"] == "good")
        assert "associated with stronger observed CTR" in good["statement"]
        assert "not causal" in good["statement"]
        # "bad" has a single entity (insufficient) -> no learning by design.
        assert all(item["value"] != "bad" for item in learnings)
        # Contrast is required: the baseline is the in-scope mean.
        _e2, _pr2, patterns2 = scope(
            {"weak_angle": [0.001, 0.0015], "strong_angle": [0.03, 0.031]}
        )
        weak_learning = next(
            item
            for item in le.build_learnings(patterns2)
            if item["value"] == "weak_angle"
        )
        assert "weaker observed CTR" in weak_learning["statement"]

    def test_no_learning_from_neutral_or_insufficient(self):
        # Alone in scope, near-identical values sit inside the deadband:
        # both directions neutral -> no learning claim.
        _e, _pr, patterns = scope({"flat": [0.0200, 0.0195]})
        assert le.build_learnings(patterns) == []
        # A single entity is insufficient_data -> no learning claim.
        _e2, _pr2, patterns2 = scope({"tiny": [0.05]})
        assert le.build_learnings(patterns2) == []


class TestConflictingEvidence:
    def test_conflict_breakdown_and_resolution_path(self):
        _e, _pr, patterns = scope({"split": [0.040, 0.008, 0.007, 0.041]})
        conflicts = le.conflicting_patterns(patterns)
        conflict = next(c for c in conflicts if c["value"] == "split")
        assert conflict["supporting"]["count"] == 2
        assert conflict["contradicting"]["count"] == 2
        assert "conflict ratio" in conflict["resolution_path"]

    def test_no_false_conflicts(self):
        _e, _pr, patterns = scope({"clean": [0.03, 0.031, 0.029, 0.032], "low": [0.001]})
        assert all(c["value"] != "clean" for c in le.conflicting_patterns(patterns))


class TestPortfolioIntelligence:
    def test_concentration_risk(self):
        _e, profiles, _p = scope({"dominant": [0.02] * 3, "minor": [0.02]})
        intel = le.build_portfolio_intelligence(profiles)
        assert intel["angle_concentration"]["risk"] is True
        assert intel["angle_concentration"]["top_value"] == "dominant"

    def test_role_balance_counts(self):
        _e, profiles, _p = scope({"a": [0.02, 0.02]})
        roles = {
            profiles[0]["entity"]["id"]: [{"role": "core"}],
            profiles[1]["entity"]["id"]: [{"role": "exploration"}],
        }
        intel = le.build_portfolio_intelligence(profiles, portfolio_roles=roles)
        assert intel["role_balance"] == {"core": 1, "exploration": 1}

    def test_coverage_gaps_from_canonical_taxonomy(self):
        _e, profiles, _p = scope({"a": [0.02, 0.021]})
        gaps = le.coverage_gaps(
            profiles,
            valid_hooks=["problem_agitation", "curiosity_gap", "urgency"],
            valid_formats=["static", "carousel"],
        )
        by_dim = {(g["dimension"], g["value"]) for g in gaps}
        assert ("creative_format", "carousel") in by_dim
        # The helper's contexts use fmt_<angle> formats, so canonical
        # static is also uncovered here.
        assert ("creative_format", "static") in by_dim
        fmt_gaps = {g["value"] for g in gaps if g["dimension"] == "creative_format"}
        assert all(gap_value not in {"fmt_a", "fmt_b"} for gap_value in fmt_gaps)


class TestRecommendations:
    def test_fatigue_signal_recommends_refresh_high_priority(self):
        _e, profiles, _p = scope({"a": [0.02, 0.02]})
        profiles = le.build_profiles(
            [entry("fatigued", "b", 0.02, fatigue="fatigue_signal")]
        )
        recs = le.build_recommendations(profiles, [], {}, [])
        refresh = next(r for r in recs if r["type"] == "refresh_creative")
        assert refresh["priority"] == "high"
        assert refresh["review_only"] is True

    def test_watch_recommends_investigate(self):
        profiles = le.build_profiles([entry("w", "b", 0.02, fatigue="watch")])
        recs = le.build_recommendations(profiles, [], {}, [])
        assert any(r["type"] == "investigate_fatigue" for r in recs)

    def test_positive_angle_yields_expand_angle(self):
        _e, profiles, patterns = scope(
            {"winner": [0.03, 0.031, 0.029, 0.032], "loser": [0.001]}
        )
        recs = le.build_recommendations(profiles, patterns, {}, [])
        expand = next(r for r in recs if r["type"] == "expand_angle")
        assert expand["affected"]["value"] == "winner"

    def test_conflict_yields_investigation_recommendation(self):
        _e, profiles, patterns = scope({"split": [0.04, 0.006, 0.007, 0.041]})
        recs = le.build_recommendations(profiles, patterns, {}, [])
        assert any(r["type"] == "investigate_conflicting_evidence" for r in recs)

    def test_prioritization_deterministic_ordering(self):
        _e, profiles, patterns = scope(
            {"winner": [0.03, 0.031, 0.029, 0.032], "loser": [0.001]}
        )
        fatigued = le.build_profiles([entry("fz", "z", 0.02, fatigue="fatigue_signal")])
        recs = le.build_recommendations(profiles + fatigued, patterns, {}, [])
        scores = [(-r["priority_score"], r["type"]) for r in recs]
        assert scores == sorted(scores)
        again = le.build_recommendations(profiles + fatigued, patterns, {}, [])
        assert [(r["type"], str(r["priority_score"])) for r in again] == [
            (r["type"], str(r["priority_score"])) for r in recs
        ]


class TestReportReproducibility:
    def test_identical_inputs_identical_report(self):
        _e, profiles, patterns = scope(
            {"k": [0.03, 0.031, 0.029, 0.032], "l": [0.001]}
        )
        portfolio = le.build_portfolio_intelligence(profiles)
        coverage = le.coverage_gaps(profiles, valid_hooks=["x"], valid_formats=["y"])
        first = le.build_report(profiles, patterns, portfolio, coverage)
        second = le.build_report(list(reversed(profiles)), patterns, portfolio, coverage)
        assert first["fingerprint"] == second["fingerprint"]
        assert first["summary"] == second["summary"]

    def test_summary_learning_status_ladder(self):
        _e, _pr, patterns = scope({"one": [0.05]})
        report = le.build_report(le.build_profiles([]), [], {}, [])
        assert report["summary"]["learning_status"] == "insufficient_data"

        _e2, profiles2, patterns2 = scope(
            {"solid": [0.03, 0.031, 0.029, 0.032], "low": [0.001]}
        )
        report2 = le.build_report(profiles2, patterns2, {}, [])
        assert report2["summary"]["learning_status"] == "stable"

    def test_decimal_precision_preserved(self):
        _e, profiles, _p = scope({"precise": [0.031234, 0.029876]})
        pattern = next(p for p in le.detect_patterns(profiles) if p["value"] == "precise")
        assert isinstance(pattern["minority_share"], Decimal)
