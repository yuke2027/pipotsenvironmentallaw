"""SQLAlchemy adapter for authentication use cases."""

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.v2.common import audit
from app.v2.domains.auth.models import LoginSession, User


class SqlAlchemyAuthenticationPort:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_user(self, username: str, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.username == username)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def resolve_session(self, token_hash: str) -> tuple[LoginSession | None, User | None]:
        record = self.session.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash))
        user = self.session.get(User, record.user_id) if record is not None else None
        return record, user

    def create_session(self, user_id: str, token_hash: str, csrf_hash: str, expires_at: datetime) -> LoginSession:
        record = LoginSession(user_id=user_id, token_hash=token_hash,
                              csrf_hash=csrf_hash, expires_at=expires_at)
        self.session.add(record)
        self.session.flush()
        return record

    def revoke_session(self, session_id: str) -> None:
        record = self.session.get(LoginSession, session_id)
        if record is not None:
            record.revoked = True

    def revoke_user_sessions(self, user_id: str) -> None:
        self.session.execute(update(LoginSession).where(LoginSession.user_id == user_id).values(revoked=True))

    def update_password(self, user_id: str, password_hash: str) -> None:
        account = self.session.get(User, user_id)
        if account is not None:
            account.password_hash = password_hash
            account.must_change_password = False

    def audit(self, actor_id: str | None, action: str, detail: dict[str, Any] | None = None) -> None:
        kind = "route" if action == "ACCESS_DENIED" else "authentication"
        audit(self.session, actor_id, action, kind, detail=detail)
