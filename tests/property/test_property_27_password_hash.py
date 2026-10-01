"""Property 27: password hashes do not expose plaintext."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError, error_payload
from app.core.security import CREDENTIALS_MESSAGE, hash_password, verify_password
from app.db.models import User
from app.db.session import create_engine_from_url, session_factory, sqlite_file_url
from app.db.upgrade import upgrade_database
from app.services.auth import AuthService
from tests.support.auth_factory import auth_settings, frozen_clock
from tests.support.memory_auth import MemoryAuditRepository


def _passwords() -> st.SearchStrategy[str]:
    body = st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=1,
        max_size=24,
    )
    return body.map(lambda value: value + "密")


@pytest.fixture(scope="module")
def auth_factory(tmp_path_factory: pytest.TempPathFactory) -> sessionmaker[object]:
    root = tmp_path_factory.mktemp("property-27")
    url = sqlite_file_url(root / "auth.db")
    upgrade_database(url, backup_directory=root / "backups")
    engine = create_engine_from_url(url)
    return session_factory(engine)


@given(password=_passwords())
@pytest.mark.property
def test_property_27_password_hash_does_not_expose_plaintext(
    password: str,
    auth_factory: sessionmaker[object],
) -> None:
    """Hashes differ, both verify, and plaintext is absent from storage, logs, and errors.

    **Feature: environmental-supervision-platform, Property 27: 密码哈希不暴露明文**
    **Property 27：密码哈希不暴露明文**
    **Validates: Requirements 13.2, 13.17, 15.5**
    """

    first = hash_password(password)
    second = hash_password(password)
    assert first != second
    assert first.startswith("$argon2id$")
    assert second.startswith("$argon2id$")
    assert verify_password(password, first)
    assert verify_password(password, second)
    assert not _reversible(first, password)
    assert not _reversible(second, password)

    from uuid import uuid4

    from app.domain.records import UserDraft
    from app.repositories.sqlalchemy.store import SqlAlchemyAuthRepository

    username = f"user-{uuid4().hex}"
    logger = logging.getLogger("app")
    handler = _ListHandler()
    logger.addHandler(handler)
    try:
        with auth_factory() as session:  # type: ignore[operator]
            repo = SqlAlchemyAuthRepository(session)
            repo.add_user(
                UserDraft(
                    username=username,
                    password_hash=first,
                    role="研究者",
                    is_active=True,
                    must_change_password=True,
                    created_at=frozen_clock().now(),
                )
            )
            session.commit()
        with auth_factory() as session:  # type: ignore[operator]
            stored = session.scalar(select(User.password_hash).where(User.username == username))
            assert isinstance(stored, str)
            assert stored == first
            assert password not in stored
            assert not _reversible(stored, password)
            service = AuthService(
                SqlAlchemyAuthRepository(session),
                MemoryAuditRepository(),
                auth_settings(),
                frozen_clock(),
            )
            with pytest.raises(AppError) as caught:
                service.login(username, password + "x")
        payload = error_payload(caught.value)
        blob = json.dumps(payload, ensure_ascii=False).replace(CREDENTIALS_MESSAGE, "")
        blob = blob.replace(str(payload["request_id"]), "")
        assert password not in blob
        rendered_logs = "\n".join(record.getMessage() for record in handler.records)
        assert password not in rendered_logs
    finally:
        logger.removeHandler(handler)


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _reversible(stored: str, password: str) -> bool:
    if stored == password or stored == password.encode("utf-8").hex():
        return True
    try:
        decoded = base64.b64decode(stored, validate=True)
    except (binascii.Error, ValueError):
        return False
    return decoded == password.encode("utf-8")
