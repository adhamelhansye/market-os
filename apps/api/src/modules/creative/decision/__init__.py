"""Creative decision plan and human review (Phase 8F).

Deterministic, review-only decision plans assembled verbatim from the
latest Phase 8E optimization snapshot, plus the repository's only
mutable human-review state. Nothing here executes anything.
"""

from src.modules.creative.decision.engine import DECISION_PLAN_RULES_VERSION

__all__ = ["DECISION_PLAN_RULES_VERSION"]
