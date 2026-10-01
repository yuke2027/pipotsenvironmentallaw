"""Property 29: missing accounts and wrong passwords are indistinguishable."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import AppError, error_payload
from app.core.security import hash_password, reset_verification_count, verification_count
from app.domain.records import UserDraft
from tests.support.auth_factory import memory_service

_KNOWN = "known-user"
_PASSWORD = "right-password"


@given(
    missing_name=st.text(min_size=1, max_size=24).filter(
        lambda value: value.strip().casefold() not in {"", _KNOWN} and "\x00" not in value
    ),
    wrong_password=st.text(min_size=1, max_size=24).filter(
        lambda value: value != _PASSWORD and "\x00" not in value
    ),
)
@pytest.mark.property
def test_property_29_credential_failures_are_indistinguishable(
    missing_name: str,
    wrong_password: str,
) -> None:
    """Both failure paths share one HTTP error and each performs one Argon2 check.

    **Feature: environmental-supervision-platform, Property 29: 凭据失败不可枚举账号**
    **Property 29：凭据失败不可枚举账号**
    **Validates: Requirements 13.5**
    """

    service, auth, _audit, clock = memory_service()
    auth.add_user(
        UserDraft(
            username=_KNOWN,
            password_hash=hash_password(_PASSWORD),
            role="研究者",
            is_active=True,
            must_change_password=False,
            created_at=clock.now(),
        )
    )
    missing = _capture(service, missing_name, wrong_password)
    wrong = _capture(service, _KNOWN, wrong_password)
    assert missing[0] == wrong[0] == 401
    assert missing[1] == wrong[1]
    assert missing[2] == 1
    assert wrong[2] == 1


def _capture(service: object, username: str, password: str) -> tuple[int, str, int]:
    from app.services.auth import AuthService

    if not isinstance(service, AuthService):
        raise TypeError("expected AuthService")
    reset_verification_count()
    with pytest.raises(AppError) as caught:
        service.login(username, password)
    error = caught.value
    payload = error_payload(error)
    structure = (
        f"{error.status_code}|{error.code.value}|{error.message}|"
        f"{payload['error']['details']}"
    )
    return error.status_code, structure, verification_count()
