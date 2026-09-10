from app.security import hash_password, verify_password


def test_hash_password_uses_argon2_and_not_plaintext() -> None:
    hashed_password = hash_password("secure-password")

    assert hashed_password != "secure-password"
    assert hashed_password.startswith("$argon2id$")


def test_verify_password_accepts_the_matching_password() -> None:
    hashed_password = hash_password("secure-password")

    assert verify_password("secure-password", hashed_password) is True
    assert verify_password("wrong-password", hashed_password) is False


def test_hash_password_uses_a_unique_salt() -> None:
    first_hash = hash_password("secure-password")
    second_hash = hash_password("secure-password")

    assert first_hash != second_hash
