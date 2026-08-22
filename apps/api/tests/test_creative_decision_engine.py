"""Deterministic decision-plan engine tests (Phase 8F).

Covers verbatim 8E consumption, blocked appendix isolation, ordering,
fingerprint stability/timestamp independence, review merge/progress and
banned-vocabulary guarantees.
"""

from decimal import Decimal

from src.modules.creative.decision import engine as de


def opportunity(oid, *, priority="high", score="5.0", dimension="angle",
                target="C", category="expansion", **overrides):
    base = {
        "opportunity_id": oid,
        "type": "expand_supported_angle",
        "dimension": dimension,
        "target_reference": target,
        "status": "supported_pattern",
        "evidence_strength": "strong",
        "learning_value": "low",
        "priority": priority,
        "priority_score": Decimal(score),
        "rationale": "associated with stronger observed CTR",
        "supporting_entity_ids": ["c-2", "c-1"],
        "contradicting_entity_ids": [],
        "data_sufficiency": "sufficient",
        "freshness_days": 1,
        "provenance": [{"entity_id": "c-1", "chain": [{"step": "entity"}]}],
        "category": category,
        "review_only": True,
        "rules_version": "copt-v1",
    }
    base.update(overrides)
    return base


class TestPlanAssembly:
    def test_normal_assembly_preserves_8e_values_verbatim(self):
        payload = {"opportunities": [opportunity("a:1", score="5.0", priority="high")],
                   "blocked_opportunities": [], "provenance_index": []}
        plan = de.build_plan(optimization_payload=payload,
                             source_optimization_fingerprint="opt-fp")
        item = plan["items"][0]
        assert item["priority_score"] == Decimal("5.0")
        assert item["priority"] == "high"
        assert item["evidence_strength"] == "strong"
        assert item["learning_value"] == "low"
        assert item["review_only"] is True
        assert item["execution_status"] == "not_executed"
        assert item["review_state"] == de.REVIEW_STATE_PROPOSED

    def test_empty_optimization_snapshot(self):
        plan = de.build_plan(optimization_payload={"opportunities": [],
                                                   "blocked_opportunities": []},
                             source_optimization_fingerprint=None)
        assert plan["items"] == []
        empty = de.empty_plan()
        assert empty["plan_status"] == de.PLAN_STATUS_UNAVAILABLE
        assert empty["summary"]["reason"] == "no_optimization_snapshot"

    def test_blocked_never_actionable_appendix_only(self):
        payload = {
            "opportunities": [],
            "blocked_opportunities": [
                {"type": "expand_supported_angle", "dimension": "angle",
                 "target_reference": "X", "blocked_by_gate": "conflicting_evidence",
                 "reason_code": "expansion_blocked", "statement": "blocked"}
            ],
            "provenance_index": [],
        }
        plan = de.build_plan(optimization_payload=payload, source_optimization_fingerprint="fp")
        assert plan["items"] == []
        entry = plan["blocked_appendix"][0]
        assert entry["actionable"] is False
        assert entry["blocked_by_gate"] == "conflicting_evidence"

    def test_suggested_review_focus_mapping(self):
        cases = {
            "expansion": de.REVIEW_FOCUS_EXPANSION,
            "fatigue": de.REVIEW_FOCUS_FATIGUE,
            "investigation": de.REVIEW_FOCUS_INVESTIGATION,
            "alignment": de.REVIEW_FOCUS_ALIGNMENT,
            "concentration": de.REVIEW_FOCUS_CONCENTRATION,
            "coverage": de.REVIEW_FOCUS_COVERAGE,
            None: de.REVIEW_FOCUS_DEFAULT,
        }
        for category, expected in cases.items():
            assert de.suggested_review_focus(category) == expected

    def test_no_second_scoring_system(self):
        # The engine must not add any numeric field beyond what 8E provided.
        payload = {"opportunities": [opportunity("a:1")], "blocked_opportunities": [],
                   "provenance_index": []}
        plan = de.build_plan(optimization_payload=payload,
                             source_optimization_fingerprint="fp")
        item = plan["items"][0]
        numeric_keys = {k for k, v in item.items() if isinstance(v, Decimal)}
        assert numeric_keys == {"priority_score"}


class TestDeterminism:
    def test_ordering_by_score_then_dimension_target_type_id(self):
        payload = {"opportunities": [
            opportunity("b:2", priority="medium", score="3.0", dimension="hook", target="h"),
            opportunity("a:1", priority="high", score="5.0"),
            opportunity("c:3", priority="medium", score="3.0", dimension="angle", target="z"),
        ], "blocked_opportunities": [], "provenance_index": []}
        plan = de.build_plan(optimization_payload=payload, source_optimization_fingerprint="fp")
        order = [(i["opportunity_id"]) for i in plan["items"]]
        assert order == ["a:1", "c:3", "b:2"]

    def test_input_order_invariance_and_fingerprint_stability(self):
        payload_a = {"opportunities": [
            opportunity("a:1"), opportunity("b:2"), opportunity("c:3")],
            "blocked_opportunities": [], "provenance_index": []}
        reversed_payload = dict(payload_a, opportunities=list(
            reversed(payload_a["opportunities"])))
        p1 = de.build_plan(optimization_payload=payload_a,
                           source_optimization_fingerprint="fp")
        p2 = de.build_plan(optimization_payload=reversed_payload,
                           source_optimization_fingerprint="fp")
        assert p1["fingerprint"] == p2["fingerprint"]
        assert p1["items"] == p2["items"]
        again = de.build_plan(optimization_payload=dict(payload_a),
                              source_optimization_fingerprint="fp")
        assert again["fingerprint"] == p1["fingerprint"]

    def test_different_inputs_change_fingerprint(self):
        base = {"opportunities": [opportunity("a:1")], "blocked_opportunities": [],
                "provenance_index": []}
        p1 = de.build_plan(optimization_payload=base, source_optimization_fingerprint="fp1")
        p2 = de.build_plan(optimization_payload=base, source_optimization_fingerprint="fp2")
        assert p1["fingerprint"] != p2["fingerprint"]
        changed = dict(base, opportunities=[opportunity("a:1", score="4.5")])
        p3 = de.build_plan(optimization_payload=changed, source_optimization_fingerprint="fp1")
        assert p1["fingerprint"] != p3["fingerprint"]

    def test_decimal_precision_preserved_verbatim(self):
        payload = {"opportunities": [opportunity("a:1", score="12.3456789012345678")],
                   "blocked_opportunities": [], "provenance_index": []}
        item = de.build_plan(optimization_payload=payload,
                             source_optimization_fingerprint="fp")["items"][0]
        assert str(item["priority_score"]) == "12.3456789012345678"


class TestReviewMergeAndProgress:
    def _plan_items(self):
        payload = {"opportunities": [opportunity("a:1"), opportunity("b:2")],
                   "blocked_opportunities": [], "provenance_index": []}
        return de.build_plan(optimization_payload=payload,
                             source_optimization_fingerprint="fp")["items"]

    def test_default_state_proposed_when_no_review(self):
        items = self._plan_items()
        merged = de.merge_review_state(items[0], {})
        assert merged["review_state"] == "proposed"
        assert merged["review_source_plan_fingerprint"] is None

    def test_merge_overlays_live_review_state(self):
        items = self._plan_items()
        reviews = {"a:1": {"review_state": "dismissed", "note": "dup",
                           "source_plan_fingerprint": "old-fp", "updated_at": None}}
        merged = de.merge_review_state(items[0], reviews)
        assert merged["review_state"] == "dismissed"
        assert merged["review_note"] == "dup"
        assert merged["review_source_plan_fingerprint"] == "old-fp"

    def test_review_progress_counts_all_states(self):
        items = self._plan_items()
        reviews = {
            "a:1": {"review_state": "acknowledged"},
            "b:2": {"review_state": "deferred"},
        }
        progress = de.review_progress(items, reviews)
        assert progress["total_items"] == 2
        assert progress["reviewed_items"] == 2
        assert progress["remaining_items"] == 0
        assert progress["acknowledged"] == 1
        assert progress["deferred"] == 1
        assert progress["proposed"] == 0

    def test_unreviewed_progress(self):
        progress = de.review_progress(self._plan_items(), {})
        assert progress["remaining_items"] == 2 and progress["reviewed_items"] == 0


class TestBannedVocabulary:
    def test_plan_contains_no_execution_language(self):
        payload = {"opportunities": [opportunity("a:1")], "blocked_opportunities": [],
                   "provenance_index": []}
        text = str(de.build_plan(optimization_payload=payload,
                                 source_optimization_fingerprint="fp")).lower()
        for forbidden in ("guaranteed", "expected winner", "winning creative",
                          "probability of success", "'optimized'", "will improve"):
            assert forbidden not in text, forbidden

    def test_allowed_states_exclude_execution_semantics(self):
        banned = {"approved", "implemented", "executed", "applied", "launched",
                  "scaled", "killed"}
        assert not banned & set(de.ALLOWED_REVIEW_STATES)

    def test_provenance_preserved_unchanged(self):
        chain = [{"entity_id": "c-1", "chain": [{"step": "campaign", "id": "cmp"}]}]
        payload = {"opportunities": [opportunity("a:1")],
                   "blocked_opportunities": [], "provenance_index": chain}
        plan = de.build_plan(optimization_payload=payload,
                             source_optimization_fingerprint="fp")
        assert plan["provenance_index"] == chain
