"""Unit tests for `_safe()` and numeric safety helpers.

These tests assert that _safe() handles edge cases without throwing
exceptions, per P2 Decimal Precision & Safety Hardening requirements.
"""

from decimal import Decimal

from src.core.utils import (
    _safe,
    clamp_decimal,
    percent_of,
    safe_add,
    safe_divide,
    safe_multiply,
)


class TestSafe:
    """Tests for _safe() edge case handling."""

    def test_none_returns_default(self):
        assert _safe(None) == Decimal("0")

    def test_no_arg_uses_default(self):
        assert _safe() == Decimal("0")

    def test_decimal_passes_through(self):
        assert _safe(Decimal("1.5")) == Decimal("1.5")

    def test_string_decimal(self):
        assert _safe("0.25") == Decimal("0.25")

    def test_int_handled(self):
        assert _safe(10) == Decimal("10")

    def test_zero_returns_zero(self):
        assert _safe(0) == Decimal("0")

    def test_nan_returns_default(self):
        assert _safe(float("nan")) == Decimal("0")
        assert _safe(Decimal("NaN")) == Decimal("0")

    def test_inf_returns_default(self):
        # Infinity is not in the explicit task list but is handled gracefully
        assert _safe(float("inf")) == Decimal("0")


class TestSafeDivide:
    """Tests for safe_divide() zero/None handling."""

    def test_normal_division(self):
        assert safe_divide(10, 2) == Decimal("5")

    def test_divide_by_zero(self):
        assert safe_divide(10, 0) == Decimal("0")

    def test_none_numerator(self):
        assert safe_divide(None, 5) == Decimal("0")

    def test_none_denominator(self):
        assert safe_divide(10, None) == Decimal("0")


class TestSafeAdd:
    """Tests for safe_add() None propagation."""

    def test_normal_addition(self):
        assert safe_add(5, 3) == Decimal("8")

    def test_none_first(self):
        assert safe_add(None, 3) == Decimal("3")

    def test_none_second(self):
        assert safe_add(5, None) == Decimal("5")


class TestSafeMultiply:
    """Tests for safe_multiply() None/NaN propagation."""

    def test_normal_multiplication(self):
        assert safe_multiply(3, 4) == Decimal("12")

    def test_none_propagation(self):
        assert safe_multiply(None, 5) == Decimal("0")


class TestPercentOf:
    """Tests for percent_of() safe percentage calculation."""

    def test_normal_percentage(self):
        assert percent_of(25, 100) == Decimal("25")

    def test_zero_part(self):
        assert percent_of(0, 100) == Decimal("0")

    def test_zero_whole(self):
        assert percent_of(50, 0) == Decimal("0")


class TestClampDecimal:
    """Tests for clamp_decimal() range clamping."""

    def test_clamp_within_range(self):
        assert clamp_decimal(value=5, minimum=0, maximum=10) == Decimal("5")

    def test_clamp_above_max(self):
        assert clamp_decimal(value=15, minimum=0, maximum=10) == Decimal("10")

    def test_clamp_below_min(self):
        assert clamp_decimal(value=-5, minimum=0, maximum=10) == Decimal("0")