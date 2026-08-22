"""Property-based tests for emotional direction validation.

Tests that validate_emotional_direction correctly handles all 10 valid emotions
and rejects invalid ones.
"""


from src.modules.creative.service import validate_emotional_direction

# The 10 valid emotions from the controlled taxonomy
VALID_EMOTIONS = {
    "relief",
    "confidence",
    "aspiration",
    "curiosity",
    "trust",
    "urgency",
    "desire",
    "belonging",
    "authority",
    "security",
}


class TestEmotionalDirectionValidation:
    """Tests for emotional direction validation."""

    def test_valid_emotions_accepted(self):
        """All 10 valid emotions should be accepted as primary or secondary."""
        for emotion in VALID_EMOTIONS:
            is_valid, error = validate_emotional_direction(emotion, None)
            assert is_valid, f"Emotion '{emotion}' should be valid but got error: {error}"
            is_valid, error = validate_emotional_direction(None, emotion)
            msg = f"Emotion '{emotion}' should be valid as secondary but got error: {error}"
            assert is_valid, msg

    def test_none_is_valid(self):
        """None values (optional fields) should be valid."""
        is_valid, error = validate_emotional_direction(None, None)
        assert is_valid
        assert error is None

    def test_same_emotion_twice_accepted(self):
        """Same emotion for primary and secondary is allowed."""
        is_valid, error = validate_emotional_direction("relief", "relief")
        assert is_valid, f"Same emotion twice should be valid but got error: {error}"

    def test_different_emotions_accepted(self):
        """Different primary and secondary emotions should be accepted."""
        is_valid, error = validate_emotional_direction("relief", "confidence")
        assert is_valid, f"Different emotions should be valid but got error: {error}"

    def test_invalid_emotions_rejected(self):
        """Invalid emotions should be rejected."""
        invalid = ["", "invalid_emotion", "nonexistent", "random_emotion", "test"]
        for emotion in invalid:
            is_valid, error = validate_emotional_direction(emotion, None)
            assert not is_valid, f"Emotion '{emotion}' should be invalid as primary"
            assert error is not None
            is_valid, error = validate_emotional_direction(None, emotion)
            assert not is_valid, f"Emotion '{emotion}' should be invalid as secondary"
            assert error is not None

    def test_invalid_emotions_rejected_list(self):
        """Comprehensive list of invalid emotions."""
        test_cases = [
            "",
            "invalid_emotion",
            "nonexistent",
            "random_emotion",
            "test",
            "emotion",
            "feeling",
            "mood",
            "state",
            "attitude",
        ]
        for emotion in test_cases:
            is_valid, error = validate_emotional_direction(emotion, None)
            assert not is_valid, f"Emotion '{emotion}' should be invalid"
            is_valid, error = validate_emotional_direction(None, emotion)
            assert not is_valid, f"Emotion '{emotion}' should be invalid as secondary"
