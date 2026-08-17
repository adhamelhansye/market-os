"""Deterministic simulation engine (Phase 5A).

The engine is the single source of simulation math. It answers one
question: *given a budget and a set of funnel assumptions, what outcomes
would a deterministic funnel model produce?* It never claims to predict
the future, never uses an LLM for numbers, never queries provider APIs,
never performs an autonomous action (no campaign edits, no budget
changes, no publishing).

Design rules:

- All money is `Decimal` (quantized to 0.01); ratios to 0.0001; counts
  (impressions / clicks / purchases) are fractional "expected" values,
  converted to float only at the transport boundary.
- Exactly one calculation model is selected per simulation (A / B / C),
  never a blend — see `select_model`.
- Unavailable != zero: every derived metric falls back to `None`
  instead of inventing a value (division by zero yields `None`).
- Break-even numbers come from the Phase 1 economics profile; this
  module never duplicates the unit-economics formulas.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.modules.simulator.constants import (
    DATA_QUALITY_INSUFFICIENT,
    DATA_QUALITY_MODERATE,
    DATA_QUALITY_STRONG,
    DATA_QUALITY_WEAK,
    MODEL_CPA_AOV,
    MODEL_CPC_CVR_AOV,
    MODEL_CPM_CTR_CVR_AOV,
    MODEL_PATHS,
    NEAR_BREAK_EVEN_THRESHOLD,
    PRECISION_MONEY,
    PRECISION_RATE,
    PROFITABILITY_NEAR_BREAK_EVEN,
    PROFITABILITY_PROFITABLE,
    PROFITABILITY_UNAVAILABLE,
    PROFITABILITY_UNPROFITABLE,
    SCENARIO_DOWNSIDE,
    SCENARIO_EXPECTED,
    SCENARIO_UPSIDE,
    SENSITIVITY_STEPS,
    SENSITIVITY_VARIABLES,
)
from src.modules.simulator.inputs import AssumptionSet
from src.modules.simulator.scenarios import LevelValues, ScenarioProfile
from src.modules.simulator.schemas import (
    BreakEvenRead,
    ProfitabilityRead,
    ScenarioMetricsRead,
    SensitivityRowRead,
    SensitivityTableRead,
    TargetComparisonRead,
)

ZERO = Decimal("0")
ONE = Decimal("1")
THOUSAND = Decimal("1000")
COUNT_PRECISION = Decimal("0.0001")


# ---------------------------------------------------------------------------
# Arithmetic helpers (all Decimal, all division-safe)
# ---------------------------------------------------------------------------


def _div(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == ZERO:
        return None
    return numerator / denominator


def _money(value: Decimal | None) -> Decimal | None:
    return value.quantize(PRECISION_MONEY) if value is not None else None


def _rate(value: Decimal | None) -> Decimal | None:
    return value.quantize(PRECISION_RATE) if value is not None else None


def _count(value: Decimal | None) -> Decimal | None:
    return value.quantize(COUNT_PRECISION) if value is not None else None


_MODEL_INPUTS: dict[str, tuple[str, ...]] = {
    MODEL_CPM_CTR_CVR_AOV: ("cpm", "ctr", "cvr", "aov"),
    MODEL_CPC_CVR_AOV: ("cpc", "cvr", "aov"),
    MODEL_CPA_AOV: ("cpa", "aov"),
}

_SENSITIVITY_ATTR: dict[str, str] = {
    "ctr": "ctr",
    "cpc": "cpc",
    "cpm": "cpm",
    "cvr": "cvr",
    "aov": "aov",
}

_CONFIDENCE_RANK: dict[str, int] = {
    DATA_QUALITY_STRONG: 3,
    DATA_QUALITY_MODERATE: 2,
    DATA_QUALITY_WEAK: 1,
    DATA_QUALITY_INSUFFICIENT: 0,
}
_RANK_CONFIDENCE: dict[int, str] = {
    3: DATA_QUALITY_STRONG,
    2: DATA_QUALITY_MODERATE,
    1: DATA_QUALITY_WEAK,
    0: DATA_QUALITY_INSUFFICIENT,
}


# ---------------------------------------------------------------------------
# Funnel output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineMetrics:
    """All metrics of one scenario run (Decimal; None = unavailable)."""

    budget: Decimal | None = None
    impressions: Decimal | None = None
    clicks: Decimal | None = None
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cpm: Decimal | None = None
    purchases: Decimal | None = None
    cvr: Decimal | None = None
    cpa: Decimal | None = None
    aov: Decimal | None = None
    revenue: Decimal | None = None
    roas: Decimal | None = None
    mer: Decimal | None = None
    gross_revenue: Decimal | None = None
    refund_amount: Decimal | None = None
    net_revenue: Decimal | None = None
    contribution_profit: Decimal | None = None
    contribution_margin: Decimal | None = None

    def to_read(self) -> ScenarioMetricsRead:
        return ScenarioMetricsRead(
            budget=self.budget,
            impressions=_to_float(self.impressions),
            clicks=_to_float(self.clicks),
            ctr=self.ctr,
            cpc=self.cpc,
            cpm=self.cpm,
            purchases=_to_float(self.purchases),
            cvr=self.cvr,
            cpa=self.cpa,
            aov=self.aov,
            revenue=self.revenue,
            roas=self.roas,
            mer=self.mer,
            gross_revenue=self.gross_revenue,
            refund_amount=self.refund_amount,
            net_revenue=self.net_revenue,
            contribution_profit=self.contribution_profit,
            contribution_margin=self.contribution_margin,
        )

    def to_dict(self) -> dict:
        return self.to_read().model_dump()


def _to_float(value: Decimal | None) -> float | None:
    return float(str(value)) if value is not None else None


# ---------------------------------------------------------------------------
# Funnel calculation
# ---------------------------------------------------------------------------


def compute_funnel(
    *,
    model: str,
    budget: Decimal,
    level: LevelValues,
    refund_rate: Decimal | None,
    profit_per_order: Decimal | None,
) -> EngineMetrics | None:
    """Run the deterministic funnel for one scenario level.

    Returns None when the model's required inputs are missing for this
    level (never fabricates). Model selection is the engine's other
    concern (`select_model`); this function only executes one model.
    """
    impressions: Decimal | None = None
    clicks: Decimal | None = None
    purchases: Decimal | None = None
    ctr: Decimal | None = level.ctr
    cpc: Decimal | None = level.cpc
    cpm: Decimal | None = level.cpm
    cvr: Decimal | None = level.cvr
    aov: Decimal | None = level.aov

    if model == MODEL_CPM_CTR_CVR_AOV:
        if level.cpm is None or level.ctr is None or level.cvr is None or level.aov is None:
            return None
        impressions = _div(budget, level.cpm) * THOUSAND
        clicks = impressions * level.ctr
        purchases = clicks * level.cvr
        cpc = _div(budget, clicks)
    elif model == MODEL_CPC_CVR_AOV:
        if level.cpc is None or level.cvr is None or level.aov is None:
            return None
        clicks = _div(budget, level.cpc)
        purchases = clicks * level.cvr
        impressions = _div(clicks, level.ctr) if level.ctr else None
        cpm = _div(budget, impressions) * THOUSAND if impressions else None
    elif model == MODEL_CPA_AOV:
        if level.cpa is None or level.aov is None:
            return None
        purchases = _div(budget, level.cpa)
        clicks = _div(purchases, level.cvr) if level.cvr else None
        impressions = _div(clicks, level.ctr) if (clicks is not None and level.ctr) else None
        cpc = _div(budget, clicks) if clicks else None
        cpm = _div(budget, impressions) * THOUSAND if impressions else None
    else:
        return None

    cpa = _div(budget, purchases)
    revenue = purchases * aov if purchases is not None and aov is not None else None
    roas = _div(revenue, budget)
    gross_revenue = revenue
    refund_amount = (
        revenue * refund_rate if revenue is not None and refund_rate is not None else None
    )
    net_revenue = (
        revenue - refund_amount if revenue is not None and refund_amount is not None else revenue
    )
    contribution_profit = (
        purchases * profit_per_order
        if purchases is not None and profit_per_order is not None
        else None
    )
    contribution_margin = _div(contribution_profit, net_revenue or revenue)

    return EngineMetrics(
        budget=_money(budget),
        impressions=_count(impressions),
        clicks=_count(clicks),
        ctr=_rate(ctr),
        cpc=_money(cpc),
        cpm=_money(cpm),
        purchases=_count(purchases),
        cvr=_rate(cvr),
        cpa=_money(cpa),
        aov=_money(aov),
        revenue=_money(revenue),
        roas=_rate(roas),
        mer=_rate(roas),
        gross_revenue=_money(gross_revenue),
        refund_amount=_money(refund_amount),
        net_revenue=_money(net_revenue),
        contribution_profit=_money(contribution_profit),
        contribution_margin=_rate(contribution_margin),
    )


def select_model(assumptions: AssumptionSet) -> str | None:
    """Pick exactly one runnable funnel model, deterministically.

    Priority: A (CPM->CTR->CVR->AOV) when impressions- and clicks-based
    evidence exists; B (CPC->CVR->AOV) otherwise; C (CPA->AOV) last.
    Returns None when no model can be grounded in evidence.
    """
    value = {
        "cpm": assumptions.cpm.value,
        "ctr": assumptions.ctr.value,
        "cpc": assumptions.cpc.value,
        "cvr": assumptions.cvr.value,
        "aov": assumptions.aov.value,
        "cpa": assumptions.cpa.value,
    }
    for model in (MODEL_CPM_CTR_CVR_AOV, MODEL_CPC_CVR_AOV, MODEL_CPA_AOV):
        if all(value[name] is not None for name in _MODEL_INPUTS[model]):
            return model
    return None


# ---------------------------------------------------------------------------
# Scenario availability
# ---------------------------------------------------------------------------


def scenario_reason(model: str, level: LevelValues) -> str | None:
    """Why a level cannot be computed (None when it can)."""
    if model not in _MODEL_INPUTS:
        return "unknown_model"
    if any(getattr(level, name) is None for name in _MODEL_INPUTS[model]):
        return "insufficient_assumptions"
    return None


def data_quality_for(assumptions: AssumptionSet, model: str) -> str:
    """Data quality = weakest confidence among the model's inputs."""
    if model not in _MODEL_INPUTS:
        return DATA_QUALITY_INSUFFICIENT
    ranks = [
        _CONFIDENCE_RANK.get(
            getattr(assumptions, name).confidence, _CONFIDENCE_RANK[DATA_QUALITY_INSUFFICIENT]
        )
        for name in _MODEL_INPUTS[model]
    ]
    return _RANK_CONFIDENCE[min(ranks)]


# ---------------------------------------------------------------------------
# Break-even / profitability / targets (expected level)
# ---------------------------------------------------------------------------


def build_break_even(
    expected: EngineMetrics,
    *,
    break_even_cpa: Decimal | None,
    break_even_roas: Decimal | None,
) -> BreakEvenRead:
    """Break-even hints relative to the expected scenario.

    All formulas are economics-derived; each value is independently
    `None` when its inputs are missing.
    """
    budget = expected.budget
    clicks = expected.clicks
    purchases = expected.purchases
    cvr = expected.cvr
    aov = expected.aov

    minimum_cvr = None
    if break_even_cpa and budget is not None and clicks is not None:
        minimum_cvr = _rate(_div(budget, break_even_cpa * clicks))
    maximum_cpc = _money(break_even_cpa * cvr) if break_even_cpa and cvr is not None else None
    minimum_aov = None
    if break_even_roas and purchases is not None:
        minimum_aov = _money(_div(break_even_roas * (budget or ZERO), purchases))
    maximum_cpa = _rate(_div(aov, break_even_roas)) if aov is not None and break_even_roas else None

    return BreakEvenRead(
        break_even_cpa=_money(break_even_cpa),
        break_even_roas=_rate(break_even_roas),
        simulated_cpa=expected.cpa,
        simulated_roas=expected.roas,
        minimum_cvr=minimum_cvr,
        maximum_cpc=maximum_cpc,
        minimum_aov=minimum_aov,
        maximum_cpa=maximum_cpa,
        minimum_roas=_rate(break_even_roas),
    )


def build_profitability(
    expected: EngineMetrics,
    *,
    break_even_roas: Decimal | None,
) -> ProfitabilityRead:
    profit = expected.contribution_profit
    if profit is None:
        return ProfitabilityRead(
            status=PROFITABILITY_UNAVAILABLE,
            roas=expected.roas,
            break_even_roas=_rate(break_even_roas),
            contribution_profit=None,
            reason="no_contribution_profit",
        )
    denominator = expected.net_revenue or expected.revenue or None
    margin = _div(profit, denominator)
    if profit > ZERO and (margin is None or margin > NEAR_BREAK_EVEN_THRESHOLD):
        status = PROFITABILITY_PROFITABLE
    elif profit < ZERO:
        status = PROFITABILITY_UNPROFITABLE
    else:
        status = PROFITABILITY_NEAR_BREAK_EVEN
    return ProfitabilityRead(
        status=status,
        roas=expected.roas,
        break_even_roas=_rate(break_even_roas),
        contribution_profit=profit,
        reason=None,
    )


def build_targets(
    expected: EngineMetrics,
    *,
    target_cpa: Decimal | None,
    target_roas: Decimal | None,
    target_revenue: Decimal | None,
    target_profit: Decimal | None,
) -> list[TargetComparisonRead]:
    """Compare the expected scenario against user-supplied targets.

    Targets are optional user input, never fabricated goals.
    """
    out: list[TargetComparisonRead] = []

    def add(metric_code: str, target, simulated, *, lower_is_better: bool) -> None:
        if target is None and simulated is None:
            return
        if target is None or simulated is None:
            out.append(
                TargetComparisonRead(
                    metric_code=metric_code,
                    target_value=target,
                    simulated_value=simulated,
                    status="unavailable",
                    reason="missing_target_or_simulation",
                )
            )
            return
        met = simulated <= target if lower_is_better else simulated >= target
        out.append(
            TargetComparisonRead(
                metric_code=metric_code,
                target_value=target,
                simulated_value=simulated,
                status="met" if met else "not_met",
                reason=None,
            )
        )

    add("cpa", target_cpa, expected.cpa, lower_is_better=True)
    add("roas", target_roas, expected.roas, lower_is_better=False)
    add("revenue", target_revenue, expected.revenue, lower_is_better=False)
    add("profit", target_profit, expected.contribution_profit, lower_is_better=False)
    return out


# ---------------------------------------------------------------------------
# Sensitivity
# ---------------------------------------------------------------------------


def build_sensitivity(
    model: str,
    *,
    budget: Decimal,
    level: LevelValues,
    refund_rate: Decimal | None,
    profit_per_order: Decimal | None,
) -> list[SensitivityTableRead]:
    """Sensitivity tables over the EXPECTED level (model stays fixed).

    Each variable in `SENSITIVITY_VARIABLES` that the model actually
    consumes gets one table; rows step the variable by -20% .. +20%
    and report the resulting revenue / profit / CPA / ROAS. Money and
    ratios stay Decimal throughout.
    """
    tables: list[SensitivityTableRead] = []
    baseline = compute_funnel(
        model=model,
        budget=budget,
        level=level,
        refund_rate=refund_rate,
        profit_per_order=profit_per_order,
    )
    baseline_profit = baseline.contribution_profit if baseline else None

    for variable in SENSITIVITY_VARIABLES:
        if variable == "budget":
            base_value = budget
        else:
            attr = _SENSITIVITY_ATTR.get(variable)
            if attr is None:
                continue
            base_value = getattr(level, attr)
            # Only include variables the model actually consumes.
            if attr not in _MODEL_INPUTS[model]:
                continue
        if base_value is None:
            continue

        rows: list[SensitivityRowRead] = []
        for step in SENSITIVITY_STEPS:
            new_value = base_value * (ONE + step)
            adjusted = None if variable == "budget" else _replace(level, variable, new_value)
            metrics = compute_funnel(
                model=model,
                budget=new_value if variable == "budget" else budget,
                level=adjusted if variable != "budget" else level,
                refund_rate=refund_rate,
                profit_per_order=profit_per_order,
            )
            rows.append(
                SensitivityRowRead(
                    variable=variable,
                    change_percent=step,
                    new_value=(
                        _money(new_value)
                        if variable in ("budget", "cpc", "cpm", "aov")
                        else _rate(new_value)
                    ),
                    revenue=metrics.revenue if metrics else None,
                    profit=metrics.contribution_profit if metrics else None,
                    cpa=metrics.cpa if metrics else None,
                    roas=metrics.roas if metrics else None,
                )
            )
        tables.append(
            SensitivityTableRead(
                variable=variable,
                rows=rows,
                baseline_profit=baseline_profit,
            )
        )
    return tables


def _replace(level: LevelValues, variable: str, value: Decimal) -> LevelValues:
    kwargs = {
        "ctr": level.ctr,
        "cpc": level.cpc,
        "cpm": level.cpm,
        "cvr": level.cvr,
        "aov": level.aov,
        "cpa": level.cpa,
    }
    kwargs[variable] = value
    return LevelValues(**kwargs)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineRun:
    """Complete deterministic simulation output (pre-persistence)."""

    model_used: str
    calculation_path: str
    scenarios: dict[str, EngineMetrics]
    reasons: dict[str, str | None]
    break_even: BreakEvenRead
    profitability: ProfitabilityRead
    sensitivity: list[SensitivityTableRead]
    targets: list[TargetComparisonRead]
    data_quality: str
    evidence_strength: str

    def scenarios_dict(self) -> dict:
        return {level: metrics.to_dict() for level, metrics in self.scenarios.items()}


def run_simulation(
    *,
    assumptions: AssumptionSet,
    profile: ScenarioProfile,
    evidence_strength: str,
    target_cpa: Decimal | None = None,
    target_roas: Decimal | None = None,
    target_revenue: Decimal | None = None,
    target_profit: Decimal | None = None,
) -> EngineRun:
    """Execute all three scenario levels over the selected model.

    Levels with missing inputs produce unavailable scenarios with an
    explicit reason — never a fabricated number.
    """
    budget = assumptions.budget.value
    refund_rate = assumptions.refund_rate.value
    profit_per_order = assumptions.contribution_profit_per_order.value
    model = select_model(assumptions)

    if model is None or budget is None or profile is None:
        return EngineRun(
            model_used="unavailable",
            calculation_path="unavailable",
            scenarios={},
            reasons={
                SCENARIO_DOWNSIDE: "insufficient_assumptions",
                SCENARIO_EXPECTED: "insufficient_assumptions",
                SCENARIO_UPSIDE: "insufficient_assumptions",
            },
            break_even=BreakEvenRead(),
            profitability=ProfitabilityRead(
                status=PROFITABILITY_UNAVAILABLE,
                reason="no_calculation_model",
            ),
            sensitivity=[],
            targets=[],
            data_quality=DATA_QUALITY_INSUFFICIENT,
            evidence_strength=evidence_strength,
        )

    scenarios: dict[str, EngineMetrics] = {}
    reasons: dict[str, str | None] = {}
    for level_name in (SCENARIO_DOWNSIDE, SCENARIO_EXPECTED, SCENARIO_UPSIDE):
        level = profile.level(level_name)
        reason = scenario_reason(model, level)
        reasons[level_name] = reason
        if reason is None:
            metrics = compute_funnel(
                model=model,
                budget=budget,
                level=level,
                refund_rate=refund_rate,
                profit_per_order=profit_per_order,
            )
            scenarios[level_name] = metrics  # type: ignore[assignment]
            reasons[level_name] = None

    expected = scenarios.get(SCENARIO_EXPECTED)
    break_even = (
        build_break_even(
            expected,
            break_even_cpa=assumptions.break_even_cpa.value,
            break_even_roas=assumptions.break_even_roas.value,
        )
        if expected is not None
        else BreakEvenRead()
    )
    profitability = (
        build_profitability(
            expected,
            break_even_roas=assumptions.break_even_roas.value,
        )
        if expected is not None
        else ProfitabilityRead(
            status=PROFITABILITY_UNAVAILABLE,
            reason="no_expected_scenario",
        )
    )
    targets = (
        build_targets(
            expected,
            target_cpa=target_cpa,
            target_roas=target_roas,
            target_revenue=target_revenue,
            target_profit=target_profit,
        )
        if expected is not None
        else []
    )
    sensitivity = (
        build_sensitivity(
            model,
            budget=budget,
            level=profile.level(SCENARIO_EXPECTED),
            refund_rate=refund_rate,
            profit_per_order=profit_per_order,
        )
        if expected is not None
        else []
    )

    return EngineRun(
        model_used=model,
        calculation_path=MODEL_PATHS[model],
        scenarios=scenarios,
        reasons=reasons,
        break_even=break_even,
        profitability=profitability,
        sensitivity=sensitivity,
        targets=targets,
        data_quality=data_quality_for(assumptions, model),
        evidence_strength=evidence_strength,
    )


__all__ = [
    "EngineMetrics",
    "EngineRun",
    "build_break_even",
    "build_profitability",
    "build_sensitivity",
    "build_targets",
    "compute_funnel",
    "data_quality_for",
    "run_simulation",
    "scenario_reason",
    "select_model",
]
