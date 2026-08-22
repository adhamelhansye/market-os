"""Utility functions for numeric safety and decimal precision.

Used by creative intelligence service to handle edge cases in
KPI calculations, percent computations, and monetary operations.
All functions guarantee Decimal output — never float, never None.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _safe(value: Any = None, default: Decimal = Decimal("0")) -> Decimal:
    """Convert a value to Decimal safely, handling edge cases.

    Handles:
    - None  -> default
    - NaN   -> default (checked via d != d)
    - Infinity -> default (non-finite values are never valid metrics)
    - negative  -> default (negative money/KPIs are invalid)
    - zero  -> Decimal("0")
    - str   -> Decimal (e.g. "0.25")
    - Decimal -> as-is (with NaN guard)
    - float -> Decimal(str) then NaN guard, to avoid floating-point artifacts
    - Other -> try Decimal(str(value)), else default

    Returns a Decimal always (never float, never None).
    """
    if value is None:
        return default

    # Handle negative values - negative money/KPIs are invalid
    try:
        s = str(value)
    except Exception:
        return default

    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return default

    # Non-finite guard: NaN and Infinity are never valid metric values.
    if not d.is_finite():
        return default

    # Negative value guard - negative money/KPIs are invalid
    if d < 0:
        return default

    return d


def safe_divide(numerator: Any, denominator: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Safe division that handles zero/None denominators and NaN."""
    num = _safe(numerator)
    den = _safe(denominator)
    if den == 0 or den is None:
        return default
    return num / den


def safe_multiply(a: Any, b: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Safe multiplication that propagates None/NaN to default."""
    return _safe(_safe(a) * _safe(b), default)


def safe_add(a: Any, b: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Safe addition that propagates None/NaN to default."""
    return _safe(_safe(a) + _safe(b), default)


def safe_subtract(a: Any, b: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Safe subtraction that propagates None/NaN to default."""
    return _safe(_safe(a) - _safe(b), default)


def percent_of(part: Any, whole: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Calculate (part / whole) * 100 safely.

    Returns default if whole is zero or None.
    """
    whole_decimal = _safe(whole)
    if whole_decimal == 0:
        return default
    return (_safe(part) / whole_decimal) * Decimal("100")


def clamp_decimal(
    value: Any,
    minimum: Any = None,
    maximum: Any = None,
    default: Decimal = Decimal("0"),
) -> Decimal:
    """Clamp a Decimal value within [minimum, maximum] range."""
    val = _safe(value, default)
    min_val = _safe(minimum) if minimum is not None else None
    max_val = _safe(maximum) if maximum is not None else None
    if min_val is not None and val < min_val:
        return min_val
    if max_val is not None and val > max_val:
        return max_val
    return val