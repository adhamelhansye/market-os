"""Diagnostics API errors.

Diagnostics are deterministic and read-only. Only filter/entity validation
errors are surfaced, as 4xx responses with stable machine-readable codes.
"""

from __future__ import annotations

from src.core.exceptions import ApiError


class DiagnosticsFilterError(ApiError):
    status_code = 422
    code = "invalid_diagnostics_filter"


__all__ = ["DiagnosticsFilterError"]