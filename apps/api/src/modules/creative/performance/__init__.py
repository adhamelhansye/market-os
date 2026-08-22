"""Creative performance intelligence (Phase 8C).

Deterministic Creative Performance Intelligence built on the canonical
metrics layer. No LLM, no predicted numbers, no autonomous actions:

- observations are aggregated from real ``metric_facts`` rows,
- signals reuse the shared KPI engine formulas (no competing math),
- fatigue / classification / readiness follow named, versioned rules,

and every conclusion carries evidence back to the metric source.
"""

from src.modules.creative.performance.thresholds import (
    CREATIVE_PERFORMANCE_RULES_VERSION,
    value,
)

__all__ = ["CREATIVE_PERFORMANCE_RULES_VERSION", "value"]
