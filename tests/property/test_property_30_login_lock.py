"""Property 30: login lockout follows the configured failure and timeout rules."""

from __future__ import annotations

from datetime import timedelta

import pytest
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from app.core.errors import AppError
from app.core.security import hash_password
from app.domain.records import UserDraft
from tests.support.auth_factory import auth_settings, frozen_clock, memory_service

_USERNAME = "lock-user"
_CORRECT = "correct-password"
_WRONG = "wrong-password"
_LIMIT = 5
_LOCK_SECONDS = 15 * 60


@hypothesis_settings(max_examples=100, deadline=None, stateful_step_count=12)
class LoginLockMachine(RuleBasedStateMachine):
    """Failure, success, and time movement against the lockout state machine.

    **Feature: environmental-supervision-platform, Property 30: 登录锁定状态机**
    **Property 30：登录锁定状态机**
    **Validates: Requirements 13.6**
    """

    def __init__(self) -> None:
        super().__init__()
        self.service, self.auth, _audit, self.clock = memory_service(
            settings=auth_settings(login_max_failures=_LIMIT, login_lock_seconds=_LOCK_SECONDS),
            clock=frozen_clock(),
        )
        self.auth.add_user(
            UserDraft(
                username=_USERNAME,
                password_hash=hash_password(_CORRECT),
                role="监管人员",
                is_active=True,
                must_change_password=False,
                created_at=self.clock.now(),
            )
        )
        self.failures = 0
        self.locked_until = None

    @rule()
    def wrong_password(self) -> None:
        now = self.clock.now()
        locked = self.locked_until is not None and now < self.locked_until
        with pytest.raises(AppError) as caught:
            self.service.login(_USERNAME, _WRONG)
        assert caught.value.status_code == 401
        if locked:
            return
        self.failures += 1
        if self.failures >= _LIMIT:
            self.locked_until = now + timedelta(seconds=_LOCK_SECONDS)

    @rule()
    def correct_password(self) -> None:
        now = self.clock.now()
        locked = self.locked_until is not None and now < self.locked_until
        if locked:
            with pytest.raises(AppError) as caught:
                self.service.login(_USERNAME, _CORRECT)
            assert caught.value.status_code == 401
            return
        result = self.service.login(_USERNAME, _CORRECT)
        assert result.user_id > 0
        self.failures = 0
        self.locked_until = None

    @rule(seconds=st.integers(min_value=0, max_value=4000))
    def advance_time(self, seconds: int) -> None:
        self.clock.advance(seconds)

    @invariant()
    def counters_match_the_repository(self) -> None:
        user = self.auth.get_by_username(_USERNAME)
        assert user is not None
        assert user.failed_login_count == self.failures
        assert user.locked_until == self.locked_until


TestProperty30LoginLock = LoginLockMachine.TestCase
TestProperty30LoginLock.pytestmark = pytest.mark.property
