from app.auth import hash_password, session_digest, verify_password


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("secret")
    second = hash_password("secret")

    assert first != second
    assert verify_password("secret", first)
    assert not verify_password("wrong", first)
    assert session_digest("token") != "token"
