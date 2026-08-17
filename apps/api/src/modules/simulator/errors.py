"""Simulator errors (Phase 5A).

The simulator is read-only and deterministic. Errors carry stable
machine-readable codes the frontend can branch on.
"""

from __future__ import annotations

from src.core.exceptions import ApiError


class SimulatorFilterError(ApiError):
    """422 — unsupported entity/model/window combination."""

    status_code = 422
    code = "invalid_simulation_request"


class SimulatorInputError(ApiError):
    """422 — semantically wrong input (negative budget, impossible rates)."""

    status_code = 422
    code = "invalid_simulation_input"


class SimulatorInsufficientDataError(ApiError):
    """422 — not enough historical data to build assumption defaults."""

    status_code = 422
    code = "insufficient_historical_data"


__all__ = [
    "SimulatorFilterError",
    "SimulatorInputError",
    "SimulatorInsufficientDataError",
]
