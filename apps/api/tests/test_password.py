"""Password hashing tests (Argon2id)."""

from src.core.security import hash_password, verify_password


def test_hash_and_verify_roundtrip() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert verify_password(password_hash, "correct horse battery staple")


def test_wrong_password_rejected() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert not verify_password(password_hash, "wrong password")


def test_hashes_are_salted_and_unique() -> None:
    first = hash_password("same-password")
    second = hash_password("same-password")
    assert first != second


def test_hash_never_contains_plaintext() -> None:
    password = "super-secret-passphrase"
    password_hash = hash_password(password)
    assert password not in password_hash


def test_malformed_hash_returns_false() -> None:
    assert not verify_password("not-an-argon2-hash", "whatever")