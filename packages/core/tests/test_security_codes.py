from __future__ import annotations

from novaxis_core.security import check_code, hash_code, new_login_code


def test_login_codes_hash_and_verify_case_insensitively() -> None:
    code = new_login_code()
    assert len(code) == 10 and "O" not in code and "0" not in code
    stored = hash_code(code)
    assert code not in stored
    assert check_code(code, stored) and check_code(code.lower(), stored)
    assert not check_code("WRONGCODE1", stored)
    assert not check_code(code, None) and not check_code(code, "plain")
    assert hash_code(code) != stored, "salted"
