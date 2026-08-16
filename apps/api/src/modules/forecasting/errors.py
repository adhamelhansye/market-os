"""Forecasting API errors.

Forecasting is deterministic and read-only. Errors carry stable
machine-readable codes the frontend can branch on (mirror of the Phase 3B
diagnostics error contract).
"""

from __future__ import annotations

from src.core.exceptions import ApiError


class ForecastingFilterError(ApiError):
    """422 — unsupported horizon/metric/entity_type combination."""

    status_code = 422
    code = "invalid_forecast_request"


class ForecastingInputError(ApiError):
    """422 — semantically wrong input (negative horizon, end before start)."""

    status_code = 422
    code = "invalid_forecast_input"


class ForecastingEconomicsMissingError(ApiError):
    """422 — profit forecast requested without unit economics."""

    status_code = 422
    code = "missing_economics"


class ForecastingModelFailureError(ApiError):
    """500 — the statistical model produced no usable signal."""

    status_code = 500
    code = "model_failure"


__all__ = [
    "ForecastingEconomicsMissingError",
    "ForecastingFilterError",
    "ForecastingInputError",
    "ForecastingModelFailureError",
]
