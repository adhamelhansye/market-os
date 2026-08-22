"""Property-based tests for hook direction validation.

Tests that validate_hook_direction correctly handles all 8 valid hook directions
and rejects invalid ones.
"""


from src.modules.creative.service import validate_hook_direction

# The 8 valid hook directions from the controlled taxonomy
VALID_HOOK_DIRECTIONS = {
    "problem_agitation",
    "benefit_focus",
    "objection_preempt",
    "curiosity_gap",
    "authority_establish",
    "social_proof",
    "urgency",
    "personal_story",
}


class TestHookDirectionValidation:
    """Tests for hook direction validation."""

    def test_valid_hook_directions_accepted(self):
        """All 8 valid hook directions should be accepted."""
        for direction in VALID_HOOK_DIRECTIONS:
            is_valid, error = validate_hook_direction(direction)
            assert is_valid, f"Hook direction '{direction}' should be valid but got error: {error}"

    def test_none_is_valid(self):
        """None (optional field) should be valid."""
        is_valid, error = validate_hook_direction(None)
        assert is_valid
        assert error is None

    def test_empty_string_is_valid(self):
        """Empty string should be valid (treated as optional)."""
        is_valid, error = validate_hook_direction("")
        assert is_valid
        assert error is None

    def test_invalid_hook_directions_rejected(self):
        """Invalid hook directions should be rejected."""
        invalid = ["invalid_direction", "nonexistent", "random_hook", "test"]
        for direction in invalid:
            is_valid, error = validate_hook_direction(direction)
            assert not is_valid, f"Hook direction '{direction}' should be invalid"
            assert error is not None

    def test_invalid_hook_directions_rejected_list(self):
        """Comprehensive list of invalid directions."""
        test_cases = [
            "invalid_direction",
            "nonexistent",
            "random_hook",
            "test",
            "hook_direction",
            "opening",
            "start",
            "begin",
            "intro",
        ]
        for direction in test_cases:
            is_valid, error = validate_hook_direction(direction)
            assert not is_valid, f"Hook direction '{direction}' should be invalid"
