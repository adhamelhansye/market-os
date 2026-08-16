"""Decision rules unit tests (Phase 4B).

Deterministic unit tests over pure rule evaluation: every decision type,
the precedence order, sample-size gates, forecast integration, economics
gates, evidence strength and review suggestions. No database, no providers,
no LLM — same inputs always produce the same outputs.
"""


from src.modules.recommendations.rules import (
    DecisionContext,
    compute_evidence_strength,
    resolve_decision,
    review_suggestions_for,
)
from src.modules.recommendations.severity import (
    DECISION_TYPES,
    EVIDENCE_STRONG,
    EVIDENCE_WEAK,
)
from src.modules.recommendations.thresholds import THRESHOLD_VERSION


def _finding(code: str, category: str, severity: str = "low",
             status: str = "detected", id: str | None = None) -> dict:
    return {
        "id": id or f"f_{code}",
        "code": code,
        "category": category,
        "severity": severity,
        "status": status,
        "evidence": {},
    }


def _healthy_ctx(**overrides) -> DecisionContext:
    """A business-grain context that is scale-eligible by default."""
    defaults = {
        "business_id": "b-1",
        "entity_type": "business",
        "entity_id": None,
        "entity_name": "Healthy Store",
        "metrics": {
            "spend": "1000.00",
            "impressions": "20000",
            "clicks": "200",
            "conversions": "10",
            "purchases": "6",
            "roas": {"value": "2.5", "status": "available"},
            "cpa": {"value": "40.00", "status": "available"},
        },
        "economics": {
            "break_even_roas": "1.8",
            "break_even_cpa_range": ["60.00", "100.00"],
            "average_contribution_profit": "50.00",
        },
        "rows": 30,
        "range_length_days": 30,
    }
    defaults.update(overrides)
    return DecisionContext(**defaults)


def _campaign_ctx(**overrides) -> DecisionContext:
    """Campaign-grain context: no purchase attribution (CPA unavailable)."""
    defaults = {
        "business_id": "b-1",
        "entity_type": "campaign",
        "entity_id": "c-1",
        "entity_name": "Campaign 1",
        "metrics": {
            "spend": "1000.00",
            "impressions": "20000",
            "clicks": "200",
            "conversions": "12",
            "purchases": None,
            "roas": {"value": "1.6", "status": "available"},
            "cpa": {
                "value": None,
                "status": "unavailable",
                "reason": "no purchase attribution at this grain",
            },
        },
        "economics": {
            "break_even_roas": "1.2",
            "break_even_cpa_range": ["60.00", "100.00"],
        },
        "rows": 30,
        "range_length_days": 30,
    }
    defaults.update(overrides)
    return DecisionContext(**defaults)


def _kill_ctx(**overrides) -> DecisionContext:
    """Persistently unprofitable business context (kill-eligible)."""
    defaults = {
        "business_id": "b-1",
        "entity_type": "business",
        "entity_id": None,
        "entity_name": "Losing Store",
        "metrics": {
            "spend": "1500.00",
            "impressions": "30000",
            "clicks": "300",
            "conversions": "15",
            "purchases": "15",
            "roas": {"value": "1.0", "status": "available"},
            "cpa": {"value": "250.00", "status": "available"},
        },
        "economics": {
            "break_even_roas": "1.8",
            "break_even_cpa_range": ["60.00", "100.00"],
            "average_contribution_profit": "50.00",
        },
        "rows": 30,
        "range_length_days": 30,
    }
    defaults.update(overrides)
    return DecisionContext(**defaults)


# ---------------------------------------------------------------------------
# Decision types are review labels, never actions
# ---------------------------------------------------------------------------


def test_resolved_decision_is_always_a_review_label() -> None:
    for ctx in (
        _healthy_ctx(),
        _kill_ctx(),
        _healthy_ctx(
            metrics={
                "spend": None,
                "impressions": None,
                "roas": {"value": None, "status": "unavailable"},
                "cpa": {"value": None, "status": "unavailable"},
            }
        ),
    ):
        decision = resolve_decision(ctx)
        assert decision.decision in DECISION_TYPES
        assert decision.decision != "kill"
        assert decision.rules_version == THRESHOLD_VERSION
        assert decision.primary_reason


# ---------------------------------------------------------------------------
# insufficient_data and learning
# ---------------------------------------------------------------------------


def test_insufficient_when_no_facts_at_all() -> None:
    ctx = _healthy_ctx(
        metrics={
            "spend": None,
            "impressions": None,
            "clicks": None,
            "conversions": None,
            "roas": {"value": None, "status": "unavailable"},
            "cpa": {"value": None, "status": "unavailable"},
        }
    )
    decision = resolve_decision(ctx)
    assert decision.decision == "insufficient_data"


def test_insufficient_below_early_signal_floors() -> None:
    ctx = _healthy_ctx(
        metrics={
            "spend": "50.00",
            "impressions": "600",
            "clicks": "3",
            "conversions": "0",
            "roas": {"value": None, "status": "unavailable"},
            "cpa": {"value": None, "status": "unavailable"},
        }
    )
    assert resolve_decision(ctx).decision == "insufficient_data"


def test_learning_when_data_present_but_below_sample_gates() -> None:
    ctx = _healthy_ctx(
        metrics={
            "spend": "200.00",
            "impressions": "2000",
            "clicks": "20",
            "conversions": "1",
            "purchases": "0",
            "roas": {"value": None, "status": "unavailable"},
            "cpa": {"value": None, "status": "unavailable"},
        },
        rows=3,
        range_length_days=3,
    )
    assert resolve_decision(ctx).decision == "learning"


def test_learning_above_floors_but_below_conversion_gate() -> None:
    ctx = _healthy_ctx(
        metrics={
            "spend": "300.00",
            "impressions": "3000",
            "clicks": "30",
            "conversions": "0",
            "purchases": "0",
            "roas": {"value": None, "status": "unavailable"},
            "cpa": {"value": None, "status": "unavailable"},
        },
        rows=10,
        range_length_days=10,
    )
    assert resolve_decision(ctx).decision == "learning"


# ---------------------------------------------------------------------------
# Precedence: tracking / data quality gate everything
# ---------------------------------------------------------------------------


def test_tracking_issue_takes_precedence_over_scale() -> None:
    ctx = _healthy_ctx(
        diagnostics=[
            _finding("provider_conversion_mismatch", "tracking", "low")
        ]
    )
    decision = resolve_decision(ctx)
    assert decision.decision == "tracking_issue"
    assert decision.severity == "critical"


def test_tracking_issue_takes_precedence_over_kill() -> None:
    ctx = _kill_ctx(
        diagnostics=[_finding("purchase_revenue_mismatch", "tracking", "medium")]
    )
    assert resolve_decision(ctx).decision == "tracking_issue"


def test_data_quality_issue_from_stale_flag() -> None:
    ctx = _healthy_ctx(data_stale=True)
    assert resolve_decision(ctx).decision == "data_quality_issue"


def test_data_quality_issue_from_finding() -> None:
    ctx = _healthy_ctx(
        diagnostics=[_finding("stale_meta_data", "data_quality", "medium")]
    )
    assert resolve_decision(ctx).decision == "data_quality_issue"


# ---------------------------------------------------------------------------
# kill_review
# ---------------------------------------------------------------------------


def test_kill_review_for_persistent_unprofitability() -> None:
    decision = resolve_decision(_kill_ctx())
    assert decision.decision == "kill_review"
    assert decision.severity == "critical"
    assert decision.primary_reason == "persistent_unprofitability"
    assert "review_campaign_for_potential_shutdown" in decision.review_suggestions
    # Kill is a REVIEW: suggestions are advisory labels, never executions.
    assert all(isinstance(s, str) for s in decision.review_suggestions)


def test_kill_review_blocked_when_forecast_shows_recovery() -> None:
    ctx = _kill_ctx(forecast={"roas": {"value": "2.2", "status": "available"}})
    assert resolve_decision(ctx).decision != "kill_review"


def test_kill_review_blocked_by_short_history() -> None:
    ctx = _kill_ctx(rows=10, range_length_days=10)
    assert resolve_decision(ctx).decision != "kill_review"


def test_kill_review_blocked_by_low_spend() -> None:
    ctx = _kill_ctx(
        metrics={
            **_kill_ctx().metrics,
            "spend": "400.00",
        }
    )
    assert resolve_decision(ctx).decision != "kill_review"


def test_kill_review_blocked_by_few_purchases() -> None:
    ctx = _kill_ctx(
        metrics={
            **_kill_ctx().metrics,
            "purchases": "3",
            "cpa": {"value": None, "status": "unavailable"},
        }
    )
    assert resolve_decision(ctx).decision != "kill_review"


def test_kill_review_suppressed_by_tracking_issue() -> None:
    ctx = _kill_ctx(
        diagnostics=[_finding("revenue_purchase_mismatch", "tracking", "medium")]
    )
    assert resolve_decision(ctx).decision == "tracking_issue"


def test_kill_review_needs_roas_below_break_even() -> None:
    ctx = _kill_ctx(
        metrics={
            **_kill_ctx().metrics,
            "roas": {"value": "1.9", "status": "available"},
            "cpa": {"value": "50.00", "status": "available"},
        }
    )
    assert resolve_decision(ctx).decision != "kill_review"


def test_campaign_grain_kill_uses_meta_conversions() -> None:
    ctx = _campaign_ctx(
        metrics={
            "spend": "1500.00",
            "impressions": "50000",
            "clicks": "500",
            "conversions": "15",
            "purchases": None,
            "roas": {"value": "0.5", "status": "available"},
            "cpa": {
                "value": None,
                "status": "unavailable",
                "reason": "no purchase attribution at this grain",
            },
        },
        economics={"break_even_roas": "1.2"},
    )
    assert resolve_decision(ctx).decision == "kill_review"


# ---------------------------------------------------------------------------
# scale_review
# ---------------------------------------------------------------------------


def test_scale_review_when_all_gates_met() -> None:
    decision = resolve_decision(_healthy_ctx())
    assert decision.decision == "scale_review"
    assert decision.severity == "medium"
    assert "review_additional_budget_allocation" in decision.review_suggestions


def test_scale_review_blocked_by_forecast_deterioration() -> None:
    ctx = _healthy_ctx(forecast={"roas": {"value": "1.5", "status": "available"}})
    # (2.5 - 1.5) / 2.5 = 40% drop > 15% → no scale
    assert resolve_decision(ctx).decision != "scale_review"


def test_scale_review_blocked_by_major_diagnostic() -> None:
    ctx = _healthy_ctx(
        diagnostics=[_finding("below_break_even_roas", "economics", "high")]
    )
    decision = resolve_decision(ctx)
    assert decision.decision != "scale_review"
    assert decision.decision == "optimize"


def test_scale_review_blocked_when_below_goal_target() -> None:
    # Goal never overrides hard economics: ROAS 2.5 > break-even 1.8
    # but < goal target 3 → scale is blocked, never kill_review.
    ctx = _healthy_ctx(
        goal={"target_roas": "3", "maximum_cpa": "40.00"},
        diagnostics=[_finding("below_target_roas", "economics", "medium")],
    )
    decision = resolve_decision(ctx)
    assert decision.decision != "kill_review"
    assert decision.decision == "optimize"


def test_scale_review_blocked_when_cpa_above_viable() -> None:
    ctx = _healthy_ctx(
        metrics={
            **_healthy_ctx().metrics,
            "cpa": {"value": "90.00", "status": "available"},
        }
    )
    decision = resolve_decision(ctx)
    assert decision.decision != "scale_review"
    assert decision.decision == "optimize"


def test_scale_review_blocked_when_performance_state_unprofitable() -> None:
    ctx = _healthy_ctx(performance_state="unprofitable")
    assert resolve_decision(ctx).decision != "scale_review"


def test_campaign_grain_scale_review() -> None:
    decision = resolve_decision(_campaign_ctx())
    assert decision.decision == "scale_review"
    # Campaign grain: CPA unavailable → cpa gates skipped, never invented.
    assert decision.metrics_snapshot["cpa"] is None


def test_campaign_scale_review_blocked_by_forecast_drop() -> None:
    ctx = _campaign_ctx(forecast={"roas": {"value": "1.0", "status": "available"}})
    # (1.6 - 1.0) / 1.6 = 37.5% drop → no scale
    assert resolve_decision(ctx).decision != "scale_review"


# ---------------------------------------------------------------------------
# optimize / maintain
# ---------------------------------------------------------------------------


def test_optimize_with_multiple_bottleneck_findings() -> None:
    ctx = _healthy_ctx(
        metrics={
            **_healthy_ctx().metrics,
            "cpa": {"value": "90.00", "status": "available"},
        },
        diagnostics=[
            _finding("low_ctr", "traffic", "low"),
            _finding("high_cpc", "traffic", "low"),
        ],
    )
    decision = resolve_decision(ctx)
    assert decision.decision == "optimize"
    suggestions = set(decision.review_suggestions)
    assert "review_creative_hooks" in suggestions
    assert "review_audience_targeting" in suggestions
    # Both findings are referenced as evidence.
    codes = {f["code"] for f in decision.diagnostics}
    assert codes == {"low_ctr", "high_cpc"}


def test_optimize_suggestion_for_funnel_bottleneck() -> None:
    ctx = _healthy_ctx(
        metrics={
            **_healthy_ctx().metrics,
            "cpa": {"value": "90.00", "status": "available"},
        },
        diagnostics=[
            {
                "id": "f_funnel",
                "code": "funnel_bottleneck",
                "category": "funnel",
                "severity": "medium",
                "status": "detected",
                "affected_stage": "purchase",
                "evidence": {
                    "funnel": {
                        "from_stage": "clicks",
                        "to_stage": "purchases",
                        "conversion_rate": "0.01",
                        "previous_rate": None,
                    }
                },
            }
        ],
    )
    decision = resolve_decision(ctx)
    assert decision.decision == "optimize"
    assert "review_landing_page_offer" in decision.review_suggestions
    funnel_items = [
        item
        for item in decision.evidence.evidence_items
        if item.funnel is not None
    ]
    assert funnel_items
    assert funnel_items[0].funnel.from_stage == "clicks"
    assert funnel_items[0].funnel.to_stage == "purchases"


def test_maintain_when_clean_and_sufficient() -> None:
    ctx = _healthy_ctx(
        metrics={
            **_healthy_ctx().metrics,
            "roas": {"value": "1.9", "status": "available"},
        }
    )
    decision = resolve_decision(ctx)
    assert decision.decision == "maintain"
    assert decision.severity == "info"


def test_maintain_ignores_informational_findings() -> None:
    ctx = _healthy_ctx(
        metrics={
            **_healthy_ctx().metrics,
            "roas": {"value": "1.9", "status": "available"},
        },
        diagnostics=[_finding("unobserved_funnel_stages", "data_quality", "info")],
    )
    # data_quality info findings signal missing stages, not stale data.
    decision = resolve_decision(ctx)
    assert decision.decision == "maintain"


# ---------------------------------------------------------------------------
# Evidence strength and snapshots
# ---------------------------------------------------------------------------


def test_evidence_strength_strong_with_full_inputs() -> None:
    ctx = _healthy_ctx(forecast={"roas": {"value": "2.3", "status": "available"}})
    assert compute_evidence_strength(ctx, "scale_review") == EVIDENCE_STRONG


def test_evidence_strength_weak_with_sparse_inputs() -> None:
    ctx = _healthy_ctx(
        metrics={
            "spend": "1000.00",
            "impressions": "20000",
            "conversions": "10",
            "purchases": "6",
            "roas": {"value": "2.5", "status": "available"},
            "cpa": {"value": "40.00", "status": "available"},
        },
        economics={},
    )
    assert compute_evidence_strength(ctx, "scale_review") == EVIDENCE_WEAK


def test_decision_carries_metrics_snapshot_and_version() -> None:
    decision = resolve_decision(_healthy_ctx())
    assert decision.metrics_snapshot["spend"] == "1000.00"
    assert decision.metrics_snapshot["roas"] == "2.5"
    assert decision.rules_version == THRESHOLD_VERSION
    assert decision.entity_type == "business"


def test_review_suggestions_never_contain_action_verbs() -> None:
    from src.modules.recommendations.thresholds import THRESHOLD_VERSION

    assert THRESHOLD_VERSION == "1.0"
    ctx = _kill_ctx()
    for decision_type in DECISION_TYPES:
        suggestions = review_suggestions_for(decision_type, ctx)
        assert isinstance(suggestions, list)
        for suggestion in suggestions:
            # All suggestion keys start with "review_" or "test_" (advisory).
            assert suggestion.startswith(("review_", "test_"))