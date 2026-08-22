"""Deterministic optimization engine tests (Phase 8E).

Covers gate precedence (O1-O8), opportunity taxonomy, conflicting
evidence handling, concentration/coverage detection, scoring as
prioritization-only, input-order invariance and snapshot reproducibility.
"""

from decimal import Decimal

from src.modules.creative.learning import engine as le
from src.modules.creative.optimization import engine as oe
from src.modules.creative.performance import engine as perf


def entry(i, angle="A", ctr=0.02, *, fatigue="healthy", fresh=1, aligned=False,
          offer=False, messaging=False, proof=False, objection=False):
    totals = {
        "impressions": Decimal("20000"),
        "clicks": Decimal(str(int(ctr * 10000))),
        "spend": Decimal("500"),
        "conversions": Decimal(5),
        "conversion_value": Decimal("400"),
    }
    ctx = {
        "angle": angle,
        "hook_direction": f"hook_{angle}",
        "creative_format": f"fmt_{angle}",
        "funnel_stage": "awareness",
        "provenance_chain": [{"step": "entity", "id": i}],
    }
    if aligned or offer:
        ctx["offer_reference"] = "offer-1"
    if aligned or messaging:
        ctx["messaging_reference"] = "msg-1"
    if proof:
        ctx["reason_to_believe"] = "proof"
    if objection:
        ctx["objection"] = "objection"
    return {
        "entity": {"type": "creative_concept", "id": i},
        "context": ctx,
        "signals": perf.extract_signals(totals),
        "classification_status": "stable",
        "fatigue_status": fatigue,
        "days_covered": 14,
        "freshness_days": fresh,
    }


def build(angles: dict[str, list[float]], **common):
    entries = [
        entry(f"{angle}-{idx}", angle, ctr, **common)
        for angle, ctr_values in angles.items()
        for idx, ctr in enumerate(ctr_values)
    ]
    profiles = le.build_profiles(entries)
    patterns = le.detect_patterns(profiles)
    portfolio = le.build_portfolio_intelligence(profiles)
    strategy_ctx = {p["entity"]["id"]: p["context"] for p in profiles}
    return profiles, patterns, portfolio, strategy_ctx


class TestGatePrecedence:
    def test_o7_supported_enables_expansion(self):
        _e, patterns_built, _portfolio, ctx = build(
            {"winner": [0.03, 0.031, 0.029, 0.032], "low": [0.001]}
        )
        opps, blocked, _gaps = oe.build_opportunities(
            patterns=patterns_built, portfolio_intelligence={}, coverage_gaps=[],
            profiles=le.build_profiles(
                [entry("w1", "winner", 0.03), entry("w2", "winner", 0.031),
                 entry("w3", "winner", 0.029), entry("w4", "winner", 0.032),
                 entry("l1", "low", 0.001)]
            ),
            strategy_context_by_entity=ctx,
        )
        expand = next(o for o in opps if o["type"] == oe.OPT_EXPAND_SUPPORTED_ANGLE)
        assert expand["status"] == "supported_pattern"
        assert not any(b["target_reference"] == "winner" for b in blocked)

    def test_o1_insufficient_blocks_expansion(self):
        # A single-entity angle cannot produce an expansion recommendation.
        _e, _pr, patterns = scope_single()
        opps, blocked, _gaps = oe.build_opportunities(
            patterns=patterns, portfolio_intelligence={}, coverage_gaps=[],
            profiles=le.build_profiles([entry("solo", "lonely", 0.05)]),
            strategy_context_by_entity={"solo-0": {}},
        )
        assert all(o["type"] != oe.OPT_EXPAND_SUPPORTED_ANGLE for o in opps)

    def test_o2_stale_blocks_expansion(self):
        entries = [
            entry(f"s{i}", "old", 0.03, fresh=30) for i in range(3)
        ] + [entry("fresh-low", "new", 0.002)]
        profiles = le.build_profiles(entries)
        patterns = le.detect_patterns(profiles)
        opps, blocked, _gaps = oe.build_opportunities(
            patterns=patterns, portfolio_intelligence={}, coverage_gaps=[],
            profiles=profiles,
            strategy_context_by_entity={p["entity"]["id"]: {} for p in profiles},
        )
        stale_blocked = [b for b in blocked if b["blocked_by_gate"] == oe.GATE_STALE_DATA]
        assert stale_blocked, blocked
        assert all(b["target_reference"] == "old" for b in stale_blocked)
        assert all(o["target_reference"] != "old" for o in opps
                   if o["type"] == oe.OPT_EXPAND_SUPPORTED_ANGLE)

    def test_o3_conflicting_never_becomes_positive(self):
        entries = [entry(f"x{i}", "X", v) for i, v in enumerate([0.04, 0.006, 0.007, 0.041])]
        profiles = le.build_profiles(entries)
        patterns = le.detect_patterns(profiles)
        split = next(p for p in patterns if p["value"] == "X")
        assert split["status"] == le.PATTERN_CONFLICTING
        opps, _blocked, _g = oe.build_opportunities(
            patterns=patterns, portfolio_intelligence={}, coverage_gaps=[],
            profiles=profiles,
            strategy_context_by_entity={p["entity"]["id"]: {} for p in profiles},
        )
        assert not any(o["type"] == oe.OPT_EXPAND_SUPPORTED_ANGLE for o in opps)
        assert any(o["type"] == oe.OPT_INVESTIGATE_CONFLICTING for o in opps)


def scope_single():
    entries = [entry("solo", "lonely", 0.05)]
    profiles = le.build_profiles(entries)
    patterns = le.detect_patterns(profiles)
    return entries, profiles, patterns


class TestOpportunityTypes:
    def test_fatigue_signal_yields_refresh_only(self):
        profiles = le.build_profiles([entry("fz", "z", 0.02, fatigue="fatigue_signal")])
        opps, _b, _g = oe.build_opportunities(
            patterns=[], portfolio_intelligence={}, coverage_gaps=[],
            profiles=profiles, strategy_context_by_entity={"fz": {}},
        )
        refresh = next(o for o in opps if o["type"] == oe.OPT_REFRESH_FATIGUED)
        assert refresh["review_only"] is True
        assert "No automatic action" in refresh["rationale"]

    def test_concentration_opportunity(self):
        _e, patterns_built, portfolio_built, ctx = build({"dominant": [0.02] * 3, "minor": [0.02]})
        portfolio = {"angle_concentration": {"risk": True, "top_value": "dominant"}}
        opps, _b, _g = oe.build_opportunities(
            patterns=[], portfolio_intelligence=portfolio, coverage_gaps=[],
            profiles=le.build_profiles([entry("a", "dominant", 0.02)]),
            strategy_context_by_entity=ctx,
        )
        conc = next(o for o in opps if o["type"] == oe.OPT_REDUCE_ANGLE_CONCENTRATION)
        assert "reduces concentration risk" in conc["rationale"]
        assert "will improve" not in conc["rationale"].lower()

    def test_funnel_coverage_gap(self):
        profiles = le.build_profiles([entry("a", "A", 0.02)])
        opps, _b, _g = oe.build_opportunities(
            patterns=[], portfolio_intelligence={}, coverage_gaps=[],
            profiles=profiles, strategy_context_by_entity={"a-0": {}},
        )
        missing_stages = {
            o["target_reference"]
            for o in opps
            if o["type"] == oe.OPT_IMPROVE_FUNNEL_COVERAGE
        }
        assert "purchase" in missing_stages
        assert "retention" in missing_stages

    def test_proof_and_objection_coverage(self):
        profiles = le.build_profiles([entry("p", "A", 0.02)])
        opps, _b, _g = oe.build_opportunities(
            patterns=[], portfolio_intelligence={}, coverage_gaps=[],
            profiles=profiles, strategy_context_by_entity={"p-0": {}},
            proof_coverage_present=False, objection_coverage_present=False,
        )
        types = {o["type"] for o in opps}
        assert oe.OPT_IMPROVE_PROOF_COVERAGE in types
        assert oe.OPT_IMPROVE_OBJECTION_COVERAGE in types

    def test_offer_and_message_alignment_validation(self):
        profiles = le.build_profiles([entry("n", "A", 0.02)])  # no refs at all
        opps, _b, _g = oe.build_opportunities(
            patterns=[], portfolio_intelligence={}, coverage_gaps=[],
            profiles=profiles, strategy_context_by_entity={"n-0": {}},
        )
        types = {o["type"] for o in opps}
        assert oe.OPT_VALIDATE_OFFER_ALIGNMENT in types
        assert oe.OPT_VALIDATE_MESSAGE_ALIGNMENT in types

    def test_aligned_entities_do_not_trigger_alignment_validation(self):
        profiles = le.build_profiles([entry("ok", "A", 0.02, aligned=True)])
        opps, _b, _g = oe.build_opportunities(
            patterns=[], portfolio_intelligence={}, coverage_gaps=[],
            profiles=profiles, strategy_context_by_entity={
                "ok-0": {"offer_reference": "o", "messaging_reference": "m"}
            },
        )
        types = {o["type"] for o in opps}
        assert oe.OPT_VALIDATE_OFFER_ALIGNMENT not in types


class TestScoring:
    def test_score_is_decimal_not_probability(self):
        _e, patterns_built, _portfolio, ctx = build(
            {"w": [0.03, 0.031, 0.029, 0.032], "l": [0.001]}
        )
        profiles = le.build_profiles(
            [entry(f"w{i}", "w", c) for i, c in enumerate([0.03, 0.031, 0.029, 0.032])]
            + [entry("l", "l", 0.001)]
        )
        patterns = le.detect_patterns(profiles)
        opps, _b, _g = oe.build_opportunities(
            patterns=patterns, portfolio_intelligence={}, coverage_gaps=[],
            profiles=profiles, strategy_context_by_entity=ctx,
        )
        expand = next(o for o in opps if o["type"] == oe.OPT_EXPAND_SUPPORTED_ANGLE)
        assert isinstance(expand["priority_score"], Decimal)
        assert "not a probability" in expand["score_note"]

    def test_contradiction_penalty_lowers_priority(self):
        profiles = le.build_profiles([entry("base", "K", 0.02)])
        pattern_supported = {
            "dimension": "angle",
            "value": "K",
            "status": le.PATTERN_SUPPORTED,
            "dominant_direction": "positive",
            "evidence_strength": "moderate",
            "observed_entities": 3,
            "positive_count": 2,
            "negative_count": 0,
            "supporting_entity_ids": ["k1"],
            "contradicting_entity_ids": [],
            "max_freshness_days": 1,
            "minority_share": Decimal("0"),
            "total_entities": 3,
            "neutral_count": 1,
            "metric": "ctr",
            "rules_version": "clearning-v1",
        }
        clean, _b, _g = oe.build_opportunities(
            patterns=[pattern_supported], portfolio_intelligence={},
            coverage_gaps=[], profiles=profiles,
            strategy_context_by_entity={"k1": {}},
        )
        contradicted = dict(pattern_supported)
        contradicted["contradicting_entity_ids"] = ["k9", "k10", "k11", "k12", "k13"]
        penalized, _b2, _g2 = oe.build_opportunities(
            patterns=[contradicted], portfolio_intelligence={},
            coverage_gaps=[], profiles=profiles,
            strategy_context_by_entity={"k1": {}},
        )
        clean_opp = next(
            o for o in clean if o["type"] == oe.OPT_EXPAND_SUPPORTED_ANGLE
        )
        penalized_opp = next(
            o for o in penalized if o["type"] == oe.OPT_EXPAND_SUPPORTED_ANGLE
        )
        assert penalized_opp["priority_score"] < clean_opp["priority_score"]


class TestPlanAssembly:
    def _plan(self, angles, **kw):
        profiles, patterns, portfolio, ctx = build(angles, **kw)
        return oe.build_plan(
            profiles=profiles, patterns=patterns,
            portfolio_intelligence=portfolio, coverage_gaps=[],
            strategy_context_by_entity=ctx,
        )

    def test_status_ladder(self):
        empty = oe.empty_plan()
        assert empty["optimization_status"] == "unavailable"

        insufficient = self._plan({"tiny": [0.05]})
        # Single entity -> nothing sufficiently observed.
        insufficient = oe.build_plan(
            profiles=le.build_profiles([entry("t", "tiny", 0.05)]),
            patterns=le.detect_patterns(le.build_profiles([entry("t", "tiny", 0.05)])),
            portfolio_intelligence={}, coverage_gaps=[],
            strategy_context_by_entity={"t-0": {}},
        )
        assert insufficient["optimization_status"] == oe.PLAN_INSUFFICIENT_DATA

        ready = self._plan({"strong": [0.03, 0.031, 0.029, 0.032], "low": [0.001]})
        assert ready["optimization_status"] == oe.PLAN_TEST_READY

        # Below LEARNING_MIN_ENTITIES even fatigue evidence cannot lift the
        # plan past insufficient_data.
        lone_fatigue = oe.build_plan(
            profiles=le.build_profiles([entry("f", "f", 0.02, fatigue="fatigue_signal")]),
            patterns=[], portfolio_intelligence={}, coverage_gaps=[],
            strategy_context_by_entity={"f-0": {}},
        )
        assert lone_fatigue["optimization_status"] == oe.PLAN_INSUFFICIENT_DATA

        review_only = oe.build_plan(
            profiles=le.build_profiles([entry("f1", "f", 0.02, fatigue="fatigue_signal"),
                                        entry("f2", "f", 0.02, fatigue="watch")]),
            patterns=[], portfolio_intelligence={}, coverage_gaps=[],
            strategy_context_by_entity={"f1": {}, "f2": {}},
        )
        assert review_only["optimization_status"] == oe.PLAN_REVIEW_READY

    def test_no_forbidden_states_or_words_in_payload(self):
        plan = self._plan({"strong": [0.03, 0.031, 0.029, 0.032], "low": [0.001]})
        text = str(plan).lower()
        for forbidden in ("guaranteed", "'optimized'", "will improve",
                          "expected winner", "winning creative"):
            assert forbidden not in text, forbidden
        # The phrase may only appear in its explicit negation form.
        assert text.count("probability of success") == text.count(
            "not a probability of success"
        )

    def test_input_order_invariance_and_reproducibility(self):
        # IDENTICAL entity set in both runs - only input ORDER differs.
        entries = [entry(f"k{i}", "k", c) for i, c in enumerate([0.03, 0.031, 0.029, 0.032])]
        entries += [entry("j-0", "j", 0.001)]

        def run(items):
            profiles = le.build_profiles(items)
            patterns = le.detect_patterns(profiles)
            portfolio = le.build_portfolio_intelligence(profiles)
            ctx = {p["entity"]["id"]: p["context"] for p in profiles}
            return oe.build_plan(
                profiles=profiles, patterns=patterns,
                portfolio_intelligence=portfolio, coverage_gaps=[],
                strategy_context_by_entity=ctx,
            )

        first = run(entries)
        second = run(list(reversed(entries)))
        assert first["fingerprint"] == second["fingerprint"]
        assert first == second

    def test_duplicate_opportunities_removed(self):
        pattern = {
            "dimension": "angle", "value": "dup", "status": le.PATTERN_STABLE,
            "dominant_direction": "positive", "evidence_strength": "strong",
            "observed_entities": 4, "positive_count": 4, "negative_count": 0,
            "supporting_entity_ids": ["d1", "d2"], "contradicting_entity_ids": [],
            "max_freshness_days": 1, "minority_share": Decimal("0"),
            "neutral_count": 0, "total_entities": 4, "metric": "ctr",
            "rules_version": "clearning-v1",
        }
        unique = oe.dedupe_opportunities(
            oe.build_opportunities(
                patterns=[pattern, dict(pattern)],
                portfolio_intelligence={}, coverage_gaps=[],
                profiles=le.build_profiles([entry("d1", "dup", 0.03)]),
                strategy_context_by_entity={"d1": {}},
            )[0]
        )
        ids = [o["opportunity_id"] for o in unique]
        assert len(ids) == len(set(ids))

    def test_review_only_always_true(self):
        plan = self._plan({"strong": [0.03, 0.031, 0.029, 0.032], "low": [0.001]})
        assert all(o["review_only"] is True for o in plan["opportunities"])

    def test_provenance_chains_travel(self):
        plan = self._plan({"strong": [0.03, 0.031, 0.029, 0.032], "low": [0.001]}, aligned=True)
        chains = [row["chain"] for row in plan["provenance_index"]]
        assert any(chain for chain in chains)
