"""Role matrix for protected operations.

The matrix is the authorization source of truth. Menus may hide links, but
callers must still consult ``is_allowed`` before any business write.
"""

from __future__ import annotations

from enum import Enum

from app.domain.enums import USER_ROLES

ADMIN = "管理员"
SUPERVISOR = "监管人员"
RESEARCHER = "研究者"

_ALL = frozenset(USER_ROLES)
_ADMIN = frozenset({ADMIN})
_ADMIN_AND_SUPERVISOR = frozenset({ADMIN, SUPERVISOR})


class Operation(str, Enum):
    """Protected operations addressed by the API and the authorization gate."""

    ME = "auth.me"
    LOGOUT = "auth.logout"
    CHANGE_PASSWORD = "auth.change_password"
    MONITORING_READ = "monitoring.read"
    COMPLIANCE_READ = "compliance.read"
    RISK_READ = "risk.read"
    FORECAST_READ = "forecast.read"
    STANDARDS_READ = "standards.read"
    STANDARDS_WRITE = "standards.write"
    EXPORT_CREATE = "exports.create"
    ALERTS_READ = "alerts.read"
    ALERT_CHANNELS_WRITE = "alert_channels.write"
    REPORTS_CREATE = "reports.create"
    JOBS_READ = "jobs.read"
    COLLECTION_TRIGGER = "jobs.collection"
    CSV_IMPORT = "imports.csv"
    MODELS_READ = "models.read"
    MODELS_RETRAIN = "models.retrain"
    MODELS_ACTIVATE = "models.activate"
    USERS_READ = "users.read"
    USERS_WRITE = "users.write"


PERMISSIONS: dict[Operation, frozenset[str]] = {
    Operation.ME: _ALL,
    Operation.LOGOUT: _ALL,
    Operation.CHANGE_PASSWORD: _ALL,
    Operation.MONITORING_READ: _ALL,
    Operation.COMPLIANCE_READ: _ALL,
    Operation.RISK_READ: _ALL,
    Operation.FORECAST_READ: _ALL,
    Operation.STANDARDS_READ: _ALL,
    Operation.EXPORT_CREATE: _ALL,
    Operation.ALERTS_READ: _ADMIN_AND_SUPERVISOR,
    Operation.REPORTS_CREATE: _ADMIN_AND_SUPERVISOR,
    Operation.JOBS_READ: _ADMIN_AND_SUPERVISOR,
    Operation.COLLECTION_TRIGGER: _ADMIN,
    Operation.CSV_IMPORT: _ADMIN,
    Operation.STANDARDS_WRITE: _ADMIN,
    Operation.ALERT_CHANNELS_WRITE: _ADMIN,
    Operation.MODELS_READ: _ADMIN,
    Operation.MODELS_RETRAIN: _ADMIN,
    Operation.MODELS_ACTIVATE: _ADMIN,
    Operation.USERS_READ: _ADMIN,
    Operation.USERS_WRITE: _ADMIN,
}

FIRST_LOGIN_OPERATIONS: frozenset[Operation] = frozenset(
    {Operation.ME, Operation.LOGOUT, Operation.CHANGE_PASSWORD}
)

ALL_PROTECTED_OPERATIONS: tuple[Operation, ...] = tuple(Operation)


def is_allowed(role: str, operation: Operation) -> bool:
    """Return whether ``role`` may perform ``operation``."""

    allowed = PERMISSIONS.get(operation)
    return allowed is not None and role in allowed
