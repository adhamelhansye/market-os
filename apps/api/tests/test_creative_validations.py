"""Parametrized unit tests for Phase 8A creative validation functions."""

import pytest

from src.modules.creative.service import validate_hook_direction, validate_emotional_direction


# ——— validate_hook_direction ———

@pytest.mark.parametrize(
    "hook_direction, expected_valid",
    [
        # All 8 controlled hook directions
        ("problem_agitation", True),
        ("benefit_focus", True),
        ("objection_preempt", True),
        ("curiosity_gap", True),
        ("authority_establish", True),
        ("social_proof", True),
        ("urgency", True),
        ("personal_story", True),
        # None/empty is optional
        (None, True),
        ("", True),
        # Invalid directions should fail
        ("invalid_hook_direction", False),
        ("opening_objective", False),  # not in controlled taxonomy
        ("pain_agitation", False),     # alias, not in controlled taxonomy
        ("fear_of_missing_out", False),  # not in the 8-item controlled taxonomy
    ],
)
def test_validate_hook_direction(hook_direction, expected_valid):
    """Validate that hook_direction is from the controlled 8-item taxonomy."""
    is_valid, error_reason = validate_hook_direction(hook_direction)
    assert is_valid == expected_valid, (
        f"Hook direction '{hook_direction}': expected_valid={expected_valid}, "
        f"got is_valid={is_valid}, error={error_reason}"
    )


# ——— validate_emotional_direction ———

@pytest.mark.parametrize(
    "primary_emotion, secondary_emotion, expected_valid",
    [
        # Valid combinations from the 10 controlled categories
        ("relief", "confidence", True),
        ("trust", "security", True),
        ("aspiration", "curiosity", True),
        ("desire", None, True),
        (None, "urgency", True),
        # Same emotion twice is allowed for emphasis
        ("authority", "authority", True),
        # Invalid emotions should fail
        ("joy", "anger", False),
        ("joy", None, False),
        (None, "invalid_emotion", False),
        (None, None, True),  # Both None is OK (optional fields)
    ],
)
def test_validate_emotional_direction(primary_emotion, secondary_emotion, expected_valid):
    """Validate that emotional directions are from the controlled 10-item taxonomy."""
    is_valid, error_reason = validate_emotional_direction(primary_emotion, secondary_emotion)
    assert is_valid == expected_valid, (
        f"Emotional direction primary={primary_emotion!r}, secondary={secondary_emotion!r}: "
        f"expected_valid={expected_valid}, got is_valid={is_valid}, error={error_reason}"
    )
