"""Research module constants and validation vocabularies (Phase 6A).

Every vocabulary here is a closed set validated deterministically
server-side. The classification & confidence model follows the Research
Intelligence Foundation spec: evidence and findings are always one of
observed / inferred / hypothesis, with an additional `supported` level
for evidence whose confidence is backed by corroboration.
"""

from __future__ import annotations

from collections.abc import Mapping

RESEARCH_TYPES: frozenset[str] = frozenset({"market", "customer", "competitor", "mixed"})

PROJECT_STATUSES: frozenset[str] = frozenset(
    {"draft", "collecting", "processing", "completed", "failed", "archived"}
)

# Successor states reachable from each project status. Draft is the
# initial state; `failed` and `archived` are terminal (failed may only be
# retried by creating a new project).
PROJECT_STATUS_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "draft": frozenset({"collecting", "processing", "completed", "archived", "failed"}),
    "collecting": frozenset({"processing", "completed", "archived", "failed"}),
    "processing": frozenset({"completed", "archived", "failed"}),
    "completed": frozenset({"archived"}),
    "failed": frozenset(),
    "archived": frozenset(),
}

SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "website",
        "product_page",
        "landing_page",
        "advertisement",
        "social_profile",
        "social_post",
        "review",
        "article",
        "search_result",
        "uploaded_document",
        "manual",
        "other",
    }
)

EVIDENCE_TYPES: frozenset[str] = frozenset(
    {
        "pricing",
        "offer",
        "product",
        "positioning",
        "feature",
        "benefit",
        "pain_point",
        "desire",
        "objection",
        "buying_trigger",
        "review",
        "complaint",
        "trust_signal",
        "messaging",
        "creative_pattern",
        "audience_signal",
        "market_signal",
        "competitor_gap",
        "funnel_signal",
        "other",
    }
)

FINDING_CATEGORIES: frozenset[str] = frozenset(
    {
        "market",
        "customer",
        "competitor",
        "offer",
        "pricing",
        "positioning",
        "messaging",
        "creative",
        "funnel",
        "product",
        "retention",
    }
)

# Deterministic classification & confidence ladder (spec-defined).
CLASSIFICATION_VALUES: frozenset[str] = frozenset({"observed", "inferred", "hypothesis"})
CONFIDENCE_VALUES: frozenset[str] = frozenset({"observed", "supported", "inferred", "hypothesis"})

PROVENANCE_VALUES: frozenset[str] = frozenset(
    {"collected", "cited", "paraphrased", "analyzed", "synthesized"}
)

IMPORTANCE_VALUES: frozenset[str] = frozenset({"low", "medium", "high"})

CONFIDENCE_STRENGTH_RANKING: dict[str, int] = {
    "observed": 3,
    "supported": 2,
    "inferred": 1,
    "hypothesis": 0,
}

# Minimum evidence support for finding strength labels.
_STRONG_MIN_TOTAL = 5
_STRONG_MIN_CORROBORATED = 3
_MODERATE_MIN_TOTAL = 3


def evidence_strength_ladder(total: int, corroborated: int) -> str:
    """Deterministic evidence strength label for a finding.

    strong    — >=5 evidence, >=3 with confidence observed/supported
    moderate  — >=3 evidence
    weak      — >=1 evidence
    insufficient — no evidence attached
    """
    if total >= _STRONG_MIN_TOTAL and corroborated >= _STRONG_MIN_CORROBORATED:
        return "strong"
    if total >= _MODERATE_MIN_TOTAL:
        return "moderate"
    if total >= 1:
        return "weak"
    return "insufficient"
