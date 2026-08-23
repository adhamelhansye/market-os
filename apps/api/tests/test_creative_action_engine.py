"""Deterministic action-preparation engine tests (Phase 8G)."""

from src.modules.creative.action import engine as ae


def item(oid, kind_category, *, dimension="angle", target="problem_agitation",
         supporting=("c-1", "c-2"), rationale="associated with stronger observed CTR"):
    return {
        "opportunity_id": oid,
        "type": f"{kind_category}_op",
        "dimension": dimension,
        "target_reference": target,
        "status": "supported_pattern",
        "priority": "high",
        "priority_score": "5.0",
        "rationale": rationale,
        "supporting_entity_ids": list(supporting),
        "contradicting_entity_ids": [],
        "category": kind_category,
        "review_only": True,
    }


CONTEXTS = {
    "c-1": {"funnel_stage": "awareness", "angle": "problem_agitation",
            "hook_direction": "problem_agitation", "creative_format": "static",
            "message": "m", "offer_reference": None},
    "c-2": {"funnel_stage": "awareness", "angle": "problem_agitation",
            "hook_direction": "problem_agitation", "creative_format": "static"},
}


class TestCategoryMapping:
    def test_expansion_translates(self):
        r = ae.translate_opportunity(item=item("a:1", "expansion"),
                                     concept_contexts=CONTEXTS, business_id="b1",
                                     source_plan_fingerprint="pf")
        assert "skip" not in r and r["kind"] == "expansion"
        assert r["supported_value"] == "problem_agitation"

    def test_coverage_gap_translates_with_scope_fallback(self):
        gap = item("h:1", "coverage_gap", dimension="hook_direction", target="urgency",
                   supporting=())
        scope = {"z1": {"hook_direction": "x", "creative_format": "carousel"}}
        r = ae.translate_opportunity(item=gap, concept_contexts={}, business_id="b1",
                                     source_plan_fingerprint="pf", scope_contexts=scope)
        assert "skip" not in r
        assert r["spec"]["hook_direction"] == "urgency"
        assert r["spec"]["creative_format"] == "carousel"  # scope fallback

    def test_coverage_gap_without_scope_is_skipped_not_invented(self):
        gap = item("h:2", "coverage_gap", dimension="hook_direction", target="urgency",
                   supporting=())
        r = ae.translate_opportunity(item=gap, concept_contexts={}, business_id="b1",
                                     source_plan_fingerprint="pf")
        assert r["skip"]["reason_code"] == "missing_required_taxonomy_field"

    def test_fatigue_translates_from_entity_context(self):
        ctx = {"f1": {"funnel_stage": "awareness", "angle": "A",
                      "hook_direction": "curiosity_gap",
                      "creative_format": "short_video"}}
        r = ae.translate_opportunity(
            item=item("f:1", "fatigue", supporting=("f1",)),
            concept_contexts=ctx, business_id="b1", source_plan_fingerprint="pf")
        assert r["kind"] == "fatigue"
        assert r["test_variable"] == "creative_refresh"
        assert len(r["variants"]) == 2

    def test_investigation_never_becomes_draft(self):
        r = ae.translate_opportunity(item=item("i:1", "investigation"),
                                     concept_contexts=CONTEXTS, business_id="b1",
                                     source_plan_fingerprint="pf")
        assert r["skip"]["reason_code"] == "category_investigation"

    def test_alignment_never_becomes_draft(self):
        r = ae.translate_opportunity(item=item("g:1", "alignment"),
                                     concept_contexts=CONTEXTS, business_id="b1",
                                     source_plan_fingerprint="pf")
        assert r["skip"]["reason_code"] == "category_alignment"

    def test_concentration_never_becomes_draft(self):
        conc = item("c:1", "concentration", dimension="portfolio", target="A",
                    supporting=())
        r = ae.translate_opportunity(item=conc, concept_contexts=CONTEXTS,
                                     business_id="b1", source_plan_fingerprint="pf")
        assert r["skip"]["reason_code"] == "category_concentration"


class TestFieldSourcing:
    def test_objective_and_metric_from_stage(self):
        r = ae.translate_opportunity(item=item("a:1", "expansion"),
                                     concept_contexts=CONTEXTS, business_id="b1",
                                     source_plan_fingerprint="pf")
        assert r["spec"]["objective"] == "awareness"
        assert r["spec"]["success_metric"] == "CTR"

    def test_purchase_stage_maps_to_cpa(self):
        ctx = {**CONTEXTS, "p": dict(CONTEXTS["c-1"], funnel_stage="purchase")}
        r = ae.translate_opportunity(
            item=item("p:1", "expansion", supporting=("p",)),
            concept_contexts=ctx, business_id="b1", source_plan_fingerprint="pf")
        assert r["spec"]["objective"] == "purchase"
        assert r["spec"]["success_metric"] == "CPA"

    def test_missing_format_skips_instead_of_inventing(self):
        sparse = {"c-1": {"funnel_stage": "awareness", "angle": "A",
                          "hook_direction": "h", "creative_format": None}}
        r = ae.translate_opportunity(item=item("a:9", "expansion", supporting=("c-1",)),
                                     concept_contexts=sparse, business_id="b1",
                                     source_plan_fingerprint="pf")
        assert r["skip"]["reason_code"] == "missing_required_taxonomy_field"

    def test_absent_offer_stays_absent(self):
        r = ae.translate_opportunity(item=item("a:1", "expansion"),
                                     concept_contexts=CONTEXTS, business_id="b1",
                                     source_plan_fingerprint="pf")
        assert r["spec"]["offer_reference"] is None


class TestDeterministicIds:
    def test_draft_test_id_shape_and_stability(self):
        first = ae.draft_test_id("b1", "expand_supported_angle:angle:C")
        second = ae.draft_test_id("b1", "expand_supported_angle:angle:C")
        assert first == second
        assert first.startswith("draft_") and len(first) <= 80

    def test_arbitrary_characters_safe(self):
        weird = 'expand_supported_angle:angle:<script>&"quote"'
        oid = weird + "\n" + "x" * 300
        tid = ae.draft_test_id("b1", oid)
        assert len(tid) <= 80 and all(c.isalnum() or c == "_" for c in tid)

    def test_business_scoped_distinctness(self):
        assert ae.draft_test_id("b1", "a:1") != ae.draft_test_id("b2", "a:1")


class TestReport:
    def test_report_sections_and_summary(self):
        acknowledged = [
            item("a:1", "expansion"),
            item("h:1", "coverage_gap", dimension="hook_direction", target="urgency",
                 supporting=()),
            item("i:1", "investigation"),
            item("g:1", "alignment"),
            item("cc:1", "concentration", dimension="portfolio", target="A",
                 supporting=()),
        ]
        report = ae.build_action_report(
            acknowledged_items=acknowledged, concept_contexts=CONTEXTS,
            business_id="b1", source_plan_fingerprint="pf",
            scope_contexts={"z": {"creative_format": "carousel"}},
        )
        assert report["summary"]["drafts_created_spec"] == 2
        assert report["summary"]["excluded_total"] == 3
        skip_codes = {s["skip_reason"]["reason_code"] for s in report.get("skipped", [])}
        # hook coverage with scope fallback produces a draft; nothing else skips here
        assert skip_codes <= {"missing_required_taxonomy_field"}

    def test_empty_acknowledged(self):
        report = ae.build_action_report(acknowledged_items=[], concept_contexts={},
                                        business_id="b1", source_plan_fingerprint="pf")
        assert report["drafts"] == []
        empty = ae.empty_report()
        assert empty["summary"]["reason"] == "no_acknowledged_opportunities"

    def test_order_invariance(self):
        ack = [item(f"x:{i}", "expansion") for i in range(3)]
        one = ae.build_action_report(acknowledged_items=ack, concept_contexts={},
                                     business_id="b1", source_plan_fingerprint="pf")
        two = ae.build_action_report(acknowledged_items=list(reversed(ack)),
                                     concept_contexts={}, business_id="b1",
                                     source_plan_fingerprint="pf")
        assert [d["source_opportunity_id"] for d in one["drafts"]] == [
            d["source_opportunity_id"] for d in two["drafts"]
        ]


class TestBannedVocabulary:
    def test_no_winner_or_prediction_language(self):
        ack = [item("a:1", "expansion"), item("f:1", "fatigue")]
        report = ae.build_action_report(acknowledged_items=ack, concept_contexts=CONTEXTS,
                                        business_id="b1", source_plan_fingerprint="pf")
        text = str(report).lower()
        for banned in ("winning", "guaranteed", "probability of success",
                       "will improve", "expected winner"):
            assert banned not in text, banned


class TestExecutionStatus:
    def test_every_draft_carries_not_executed(self):
        ack = [item("a:1", "expansion"), item("f:1", "fatigue")]
        report = ae.build_action_report(acknowledged_items=ack, concept_contexts=CONTEXTS,
                                        business_id="b1", source_plan_fingerprint="pf")
        assert all(d["execution_status"] == "not_executed" for d in report["drafts"])
