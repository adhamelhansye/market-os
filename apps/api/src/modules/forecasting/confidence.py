"""Confidence interval helpers for the deterministic forecast engine.

The engine reports symmetric intervals around the central forecast at the
configured confidence level (default 80%). The width comes from the
model's own residual / bucket stddev: we never invent a confidence that
the model cannot justify.

Interval invariants (tested):

- lower ≤ expected ≤ upper
- lower ≥ 0 for non-negative business metrics
- the half-width is `stddev * z`, where `z` is the two-sided normal z-score
  for the configured level
"""

from __future__ import annotations

from decimal import Decimal

from src.modules.forecasting.constants import DEFAULT_CONFIDENCE_LEVEL

ZERO = Decimal("0")


_Z_TABLE: dict[Decimal, Decimal] = {
    Decimal("0.50"): Decimal("0.6745"),
    Decimal("0.60"): Decimal("0.8416"),
    Decimal("0.70"): Decimal("1.0364"),
    Decimal("0.80"): Decimal("1.2816"),
    Decimal("0.90"): Decimal("1.6449"),
    Decimal("0.95"): Decimal("1.9600"),
}


def z_score(confidence_level: Decimal) -> Decimal:
    """Return the symmetric z-score for the requested confidence level.

    Levels outside the table snap to the nearest supported entry; this is
    deliberate because the engine only exposes a small set of meaningful
    confidences (the Phase 4A spec lists 80% as the default).
    """
    if confidence_level <= ZERO:
        return ZERO
    if confidence_level >= Decimal("1"):
        return _Z_TABLE[Decimal("0.95")]
    quantized = confidence_level.quantize(Decimal("0.01"))
    if quantized in _Z_TABLE:
        return _Z_TABLE[quantized]
    # Snap to the nearest entry.
    nearest = min(_Z_TABLE.keys(), key=lambda k: abs(k - confidence_level))
    return _Z_TABLE[nearest]


def interval(
    expected: Decimal,
    stddev: Decimal,
    *,
    confidence_level: Decimal = DEFAULT_CONFIDENCE_LEVEL,
    non_negative: bool = True,
) -> tuple[Decimal, Decimal]:
    """Return `(lower, upper)` for the requested confidence level.

    The interval is centered on `expected`. When `non_negative=True` the
    lower bound is clamped at zero — business metrics (revenue, spend,
    purchases) are never negative and a negative lower bound would be
    misleading in the UI.
    """
    z = z_score(confidence_level)
    half = (stddev * z).quantize(Decimal("0.0001"))
    upper = expected + half
    lower = expected - half
    if non_negative and lower < ZERO:
        lower = ZERO
    return lower, upper


__all__ = ["interval", "z_score", "DEFAULT_CONFIDENCE_LEVEL"]
