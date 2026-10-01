"""Closed string sets stored with database CHECK constraints.

Numeric legal limits and risk upper bounds do not live here. They are seed
data, read back from the database when a decision is made.
"""

from __future__ import annotations

MONITORING_SOURCES: tuple[str, ...] = ("ONLINE", "CSV", "IMPUTED")
USER_ROLES: tuple[str, ...] = ("管理员", "监管人员", "研究者")
COMPLIANCE_STATUSES: tuple[str, ...] = ("COMPLIANT", "NON_COMPLIANT", "INSUFFICIENT")
RISK_LEVELS: tuple[str, ...] = ("低", "中", "高", "严重")
CRITICAL_RISK_LEVEL = "严重"
FORECAST_STATUSES: tuple[str, ...] = ("SUCCESS", "SKIPPED", "FAILED")
MODEL_STATUSES: tuple[str, ...] = ("available", "retired")
ALERT_CHANNEL_TYPES: tuple[str, ...] = ("email", "webhook")
ALERT_STATUSES: tuple[str, ...] = ("PENDING", "SENT", "FAILED")
DELIVERY_OUTCOMES: tuple[str, ...] = ("SUCCESS", "FAILED")
JOB_STATUSES: tuple[str, ...] = ("RUNNING", "SUCCESS", "FAILED")
