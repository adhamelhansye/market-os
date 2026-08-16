"""Recommendations API errors.

The decision engine is deterministic and read-only. Only filter and
entity-validation errors are surfaced, as 4xx responses with stable
machine-readable codes.
"""

from __future__ import annotations

from src.core.exceptions import ApiError


class RecommendationsFilterError(ApiError):
    status_code = 422
    code = "invalid_recommendations_filter"


__all__ = ["RecommendationsFilterError"]