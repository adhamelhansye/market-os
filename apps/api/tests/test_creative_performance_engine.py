"""Deterministic rules for the creative performance engine (Phase 8C).

Every rule branch is tested against explicit Decimal inputs: normal
values, missing data, zero denominators, insufficient volume, trend
changes, fatigue windows, classification precedence, readiness gates,
comparison ordering, Decimal precision and snapshot reproducibility.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.modules.creative.performance import engine as eng


def sigmap(**overrides):
    totals = {
        "impressions": Decimal("10000"),
        "reach": Decimal("5000"),
        "clicks": Decimal("100"),
        "spend": Decimal("250"),
        "conversions": Decimal(5),
        "conversion_value": Decimal("500"),
    }
    totals.update(overrides)
    return eng.signals_by_code(eng.extract_signals(totals))


# ---------------------------------------------------------------------------
# Signal extraction (8C.3)
# ---------------------------------------------------------------------------


class TestSignalExtraction:
    def test_normal_values_available(self):
        signals = sigmap()
        assert signals["ctr"]["value"] == Decimal("0.0100")
        assert signals["cpc"]["value"] == Decimal("2.50")  # HALF_EVEN of 2.505
        assert signals["cpm"]["status"] == "available"
        assert signals["cvr_meta"]["source"] == "meta_reported"
        assert signals["cpa_meta"]["value"] == Decimal("50.00")
        assert signals["roas_meta"]["value"] == Decimal("2.0000")
        assert signals["frequency"]["value"] == Decimal("2.0000")

    def test_missing_denominators_unavailable_never_zero(self):
        signals = eng.signals_by_code(eng.extract_signals({}))
        for code in ("ctr", "cpc", "cpm", "cvr_meta", "cpa_meta", "roas_meta", "frequency"):
            assert signals[code]["status"] == "unavailable"
            assert signals[code]["value"] is None

    def test_real_zero_is_available(self):
        signals = eng.signals_by_code(
            eng.extract_signals({"impressions": Decimal(1000), "clicks": Decimal(0)})
        )
        assert signals["ctr"]["status"] == "available"
        assert signals["ctr"]["value"] == Decimal("0.0000")

    def test_zero_denominator_unavailable(self):
        signals = eng.signals_by_code(
            eng.extract_signals({"clicks": Decimal(0), "spend": Decimal("5.00")})
        )
        assert signals["cpc"]["status"] == "unavailable"
        assert signals["cvr_meta"]["status"] == "unavailable"

    def test_raw_facts_labelled_meta_reported(self):
        signals = eng.signals_by_code(eng.extract_signals({"spend": Decimal("1.00")}))
        assert signals["spend"]["source"] == "meta_reported"
        assert signals["impressions"]["reason"] == "no observed facts"

    def test_decimal_precision_money_and_rate(self):
        signals = eng.signals_by_code(
            eng.extract_signals(
                {
                    "impressions": Decimal("3"),
                    "clicks": Decimal("1"),
                    "spend": Decimal("1"),
                    "conversions": Decimal("3"),
                }
            )
        )
        assert str(signals["ctr"]["value"]) == "0.3333"
        assert str(signals["cvr_meta"]["value"]) == "3.0000"
        assert str(signals["cpa_meta"]["value"]) == "0.33"


# ---------------------------------------------------------------------------
# Trend (half-split)
# ---------------------------------------------------------------------------


def _daily(n, *, impressions=1000, clicks_fn=lambda i: 10, spend_fn=lambda i: 10):
    start = date(2026, 8, 1)
    return [
        {
            "date": start + timedelta(days=i),
            "impressions": impressions,
            "clicks": clicks_fn(i),
            "spend": spend_fn(i),
        }
        for i in range(n)
    ]


class TestTrend:
    def test_rising(self):
        trend = eng.trend_from_daily(_daily(10, clicks_fn=lambda i: 5 + i))
        assert trend["metrics"]["ctr"]["direction"] == "rising"

    def test_falling(self):
        trend = eng.trend_from_daily(_daily(8, clicks_fn=lambda i: max(1, 20 - i * 2)))
        assert trend["metrics"]["ctr"]["direction"] == "falling"

    def test_stable_within_deadband(self):
        trend = eng.trend_from_daily(_daily(8))
        assert trend["metrics"]["ctr"]["direction"] == "stable"

    def test_insufficient_days(self):
        trend = eng.trend_from_daily(_daily(4))
        assert trend["status"] == "insufficient_data"
        assert trend["metrics"] == {}

    def test_spend_trend_present(self):
        trend = eng.trend_from_daily(_daily(6, spend_fn=lambda i: 10 * (i + 1)))
        assert trend["metrics"]["spend"]["direction"] == "rising"


# ---------------------------------------------------------------------------
# Fatigue (8C.5)
# ---------------------------------------------------------------------------

BASE = date(2026, 8, 14)


def _fatigue_rows(*, prior_clicks=70, recent_clicks=70, prior_reach=5000,
                  recent_reach=5000, impressions=10000, days=14):
    rows = []
    for i in range(days):
        recent = i >= 7
        rows.append(
            {
                "date": BASE - timedelta(days=(days - 1 - i)),
                "impressions": impressions,
                "reach": recent_reach if recent else prior_reach,
                "clicks": recent_clicks if recent else prior_clicks,
                "spend": 100,
                "conversions": 10,
            }
        )
    return rows


class TestFatigue:
    def test_healthy_flat_performance(self):
        result = eng.detect_fatigue(BASE, _fatigue_rows())
        assert result["status"] == "healthy"
        assert result["score"] == 0

    def test_ctr_decline_plus_frequency_is_fatigue_signal(self):
        rows = _fatigue_rows(recent_clicks=25, recent_reach=2500)  # ctr -64%, freq rises above high
        result = eng.detect_fatigue(BASE, rows)
        assert result["status"] == "fatigue_signal"
        triggered = {signal["code"] for signal in result["signals"] if signal["triggered"]}
        assert "ctr_decline" in triggered
        assert "frequency_pressure" in triggered

    def test_single_signal_is_watch(self):
        # CTR declines but frequency stays low.
        rows = _fatigue_rows(recent_clicks=30)
        result = eng.detect_fatigue(BASE, rows)
        assert result["status"] == "watch"
        assert result["score"] == 1

    def test_cost_escalation_counts_toward_signal(self):
        rows = []
        for i in range(14):
            recent = i >= 7
            rows.append(
                {
                    "date": BASE - timedelta(days=(13 - i)),
                    "impressions": 10000,
                    "reach": 5000,
                    "clicks": 70,
                    "conversions": 2 if recent else 10,
                    "spend": 100,
                }
            )
        result = eng.detect_fatigue(BASE, rows)
        triggered = {signal["code"] for signal in result["signals"] if signal["triggered"]}
        assert "cost_escalation" in triggered
        assert result["status"] == "watch"  # single signal alone

    def test_insufficient_window_data(self):
        result = eng.detect_fatigue(BASE, _fatigue_rows(days=9))
        assert result["status"] == "insufficient_data"
        # Only the PRIOR window is short here; either window being short
        # must yield insufficient_data.
        windows = result["windows"]
        short_windows = [
            window
            for window in ("recent", "prior")
            if windows[window]["observed_days"] < windows["min_observed"]
        ]
        assert short_windows == ["prior"]
        assert result["score"] is None

    def test_rules_version_stamped(self):
        result = eng.detect_fatigue(BASE, _fatigue_rows())
        assert result["rules_version"] == eng.FATIGUE_RULES_VERSION


# ---------------------------------------------------------------------------
# Classification (8C.6)
# ---------------------------------------------------------------------------


def _classify(signals_map=None, **kwargs):
    defaults = dict(
        days_covered=10,
        break_even_roas=None,
        fatigue_status="healthy",
        ctr_trend_direction="stable",
    )
    defaults.update(kwargs)
    return eng.classify(signals_map if signals_map is not None else sigmap(), **defaults)


class TestClassification:
    def test_r1_insufficient_volume(self):
        result = _classify(sigmap(impressions=Decimal("400")))
        assert result["status"] == "insufficient_data"
        assert result["rule"] == "R1_volume_gate"

    def test_r1_insufficient_days(self):
        result = _classify(days_covered=2)
        assert result["status"] == "insufficient_data"

    def test_r2_fatigue_overrides_everything(self):
        result = _classify(fatigue_status="fatigue_signal")
        assert result["status"] == "fatigue_signal"
        assert result["rule"] == "R2_fatigue"

    def test_r3_economics_negative_beats_developing(self):
        result = _classify(break_even_roas=Decimal("20"))
        assert result["status"] == "underperforming"
        assert result["rule"] == "R3_underperformance"

    def test_r3_critical_ctr(self):
        result = _classify(sigmap(clicks=Decimal("25")))  # ctr 0.0025 < 0.003
        assert result["status"] == "underperforming"

    def test_r4_strong(self):
        result = _classify(
            sigmap(),
            break_even_roas=Decimal("1.5"),
            fatigue_status="healthy",
            ctr_trend_direction="rising",
        )
        assert result["status"] == "strong"
        assert result["rule"] == "R4_strong"

    def test_r4_strong_blocked_by_falling_trend(self):
        result = _classify(
            sigmap(),
            break_even_roas=Decimal("1.5"),
            ctr_trend_direction="falling",
        )
        assert result["status"] != "strong"

    def test_r5_developing_short_runway(self):
        # Mid CTR between critical and low floors; short runway.
        result = _classify(sigmap(clicks=Decimal("50")), days_covered=4)
        assert result["status"] == "developing"
        assert result["rule"] == "R5_short_runway"

    def test_r6_stable_baseline(self):
        result = _classify(
            sigmap(clicks=Decimal("50"), conversions=Decimal(1))
        )
        assert result["status"] == "stable"
        assert result["rule"] == "R6_baseline"

    def test_result_carries_rules_version_and_evidence(self):
        result = _classify()
        assert result["rules_version"] == eng.CLASSIFICATION_RULES_VERSION
        assert isinstance(result["evidence"], list)


# ---------------------------------------------------------------------------
# Scaling readiness (8C.7)
# ---------------------------------------------------------------------------


class TestScalingReadiness:
    def test_g1_insufficient_gates(self):
        result = eng.scaling_readiness(
            sigmap(spend=Decimal("10")),
            days_covered=10,
            fatigue_status="healthy",
            classification_status="strong",
            break_even_roas=None,
        )
        assert result["status"] == "insufficient_data"
        assert result["ready_for_review"] is False
        unmet = [gate["code"] for gate in result["gates"] if not gate["met"]]
        assert unmet == ["sample_min_spend"]

    def test_g2_fatigue_risk_from_watch(self):
        result = eng.scaling_readiness(
            sigmap(), days_covered=10, fatigue_status="watch",
            classification_status="stable", break_even_roas=None,
        )
        assert result["status"] == "fatigue_risk"

    def test_g3_not_ready_negative_economics(self):
        result = eng.scaling_readiness(
            sigmap(), days_covered=10, fatigue_status="healthy",
            classification_status="stable", break_even_roas=Decimal("2.5"),
        )
        assert result["status"] == "not_ready"

    def test_g4_strong_candidate(self):
        result = eng.scaling_readiness(
            sigmap(), days_covered=10, fatigue_status="healthy",
            classification_status="strong", break_even_roas=Decimal("1.5"),
        )
        assert result["status"] == "strong_candidate_for_review"
        assert result["ready_for_review"] is True

    def test_g5_ready_for_review(self):
        result = eng.scaling_readiness(
            sigmap(conversions=Decimal(3)), days_covered=10,
            fatigue_status="healthy", classification_status="stable",
            break_even_roas=None,
        )
        assert result["status"] == "ready_for_review"

    def test_readiness_never_executes(self):
        """The payload contains no action fields — informational only."""
        result = eng.scaling_readiness(
            sigmap(), days_covered=10, fatigue_status="healthy",
            classification_status="strong", break_even_roas=None,
        )
        assert set(result.keys()) <= {"status", "ready_for_review", "gates", "rules_version"}


# ---------------------------------------------------------------------------
# Comparison (8C.4)
# ---------------------------------------------------------------------------


class TestComparison:
    def _entries(self):
        return [
            {
                "entity": {"id": "b", "type": "creative_concept"},
                "signals": sigmap(clicks=Decimal("80")),
            },
            {
                "entity": {"id": "a", "type": "creative_concept"},
                "signals": sigmap(clicks=Decimal("120")),
            },
            {
                "entity": {"id": "c", "type": "creative_concept"},
                "signals": sigmap(impressions=Decimal("100")),
            },
        ]

    def test_ranking_deterministic_with_exclusions(self):
        result = eng.compare_entities(self._entries())
        ranks = [(item["rank"], item["entity"]["id"]) for item in result["ranked"]]
        assert ranks == [(1, "a"), (2, "b")]
        assert result["excluded"][0]["entity"]["id"] == "c"
        reasons = result["excluded"][0]["reasons"]
        assert any("sample_min_impressions" in reason for reason in reasons)

    def test_spread_between_best_and_worst(self):
        result = eng.compare_entities(self._entries())
        assert result["spread"]["absolute_change"] == Decimal("0.0040")

    def test_lower_is_better_for_cpa(self):
        entries = [
            {"entity": {"id": "x"}, "signals": sigmap()},
            {"entity": {"id": "y"}, "signals": sigmap(conversions=Decimal(10))},  # cpa 25 < 50
        ]
        result = eng.compare_entities(entries, primary_metric="cpa_meta")
        assert result["lower_is_better"] is True
        assert result["ranked"][0]["entity"]["id"] == "y"

    def test_unsupported_metric_rejected(self):
        with pytest.raises(ValueError):
            eng.compare_entities([], primary_metric="magic")

    def test_same_input_same_order(self):
        first = eng.compare_entities(self._entries())
        second = eng.compare_entities(list(reversed(self._entries())))
        assert [item["entity"]["id"] for item in first["ranked"]] == [
            item["entity"]["id"] for item in second["ranked"]
        ]

    def test_metric_unavailable_entities_excluded(self):
        entries = [{"entity": {"id": "z"}, "signals": {}}]
        result = eng.compare_entities(entries)
        assert result["ranked"] == []
        assert "ctr unavailable" in result["excluded"][0]["reasons"]


# ---------------------------------------------------------------------------
# Snapshots / serialization
# ---------------------------------------------------------------------------


class TestSnapshotHelpers:
    def test_fingerprint_order_insensitive(self):
        a = eng.fingerprint({"x": Decimal("1.5"), "y": ["a", "b"]})
        b = eng.fingerprint({"y": ["a", "b"], "x": "1.5"})
        assert a == b

    def test_fingerprint_changes_with_payload(self):
        assert eng.fingerprint({"x": 1}) != eng.fingerprint({"x": 2})

    def test_to_jsonable_converts_decimals_dates_uuids(self):
        import uuid as uuid_mod

        value = eng.to_jsonable(
            {
                "money": Decimal("12.3400"),
                "when": date(2026, 8, 22),
                "id": uuid_mod.UUID("00000000-0000-0000-0000-000000000001"),
                "nested": [Decimal("0.0100")],
            }
        )
        assert value == {
            "money": "12.3400",
            "when": "2026-08-22",
            "id": "00000000-0000-0000-0000-000000000001",
            "nested": ["0.0100"],
        }
