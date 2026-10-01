"""Unit coverage for Argon2id passwords and HS256 tokens."""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.errors import AppError, error_payload
from app.core.logging import SensitiveDataFilter
from app.core.security import (
    credentials_error,
    decode_access_token,
    hash_password,
    issue_access_token,
    verify_password,
)

TEST_SECRET = "unit-test-jwt-secret-value"
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_valid_and_invalid_passwords_use_distinct_argon2id_hashes() -> None:
    first = hash_password("correct-horse")
    second = hash_password("correct-horse")
    assert first != second
    assert first.startswith("$argon2id$")
    assert verify_password("correct-horse", first)
    assert verify_password("correct-horse", second)
    assert verify_password("other-horse", first) is False
    assert verify_password("correct-horse", None) is False


def test_empty_password_is_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_expired_and_tampered_tokens_are_rejected() -> None:
    token, _claims = issue_access_token(
        user_id=7,
        role="研究者",
        password_change_required=False,
        now=_NOW,
        ttl_seconds=60,
        secret=TEST_SECRET,
    )
    decode_access_token(token, TEST_SECRET, _NOW + timedelta(seconds=59))
    with pytest.raises(AppError) as expired:
        decode_access_token(token, TEST_SECRET, _NOW + timedelta(seconds=60))
    assert expired.value.status_code == 401

    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(AppError) as broken:
        decode_access_token(tampered, TEST_SECRET, _NOW)
    assert broken.value.status_code == 401


def test_non_hs256_algorithms_are_rejected() -> None:
    other = jwt.encode(
        {"sub": "1", "role": "研究者", "iat": 1, "exp": 9999999999, "jti": "j", "password_change_required": False},
        TEST_SECRET,
        algorithm="HS384",
    )
    with pytest.raises(AppError) as caught:
        decode_access_token(other, TEST_SECRET, _NOW)
    assert caught.value.status_code == 401

    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = '{"sub":"1","role":"研究者","iat":1,"exp":9999999999,"jti":"j","password_change_required":false}'
    body = base64.urlsafe_b64encode(payload.encode("utf-8")).rstrip(b"=").decode()
    unsigned = f"{header}.{body}."
    with pytest.raises(AppError) as none_alg:
        decode_access_token(unsigned, TEST_SECRET, _NOW)
    assert none_alg.value.status_code == 401


def test_password_and_token_values_are_redacted_from_logs(caplog: pytest.LogCaptureFixture) -> None:
    secret_password = "plain-password-value"
    secret_token = "plain-token-value"
    logger = logging.getLogger("unit.auth.redaction")
    logger.addFilter(SensitiveDataFilter())
    logger.setLevel(logging.INFO)
    with caplog.at_level(logging.INFO, logger="unit.auth.redaction"):
        digest = hash_password(secret_password)
        assert verify_password(secret_password, digest)
        logger.info("password=%s authorization=%s", secret_password, secret_token)
    assert secret_password not in caplog.text
    assert secret_token not in caplog.text
    payload = error_payload(credentials_error())
    rendered = json.dumps(payload)
    assert secret_password not in rendered
    assert "INVALID_CREDENTIALS" in rendered
