"""Administrator alert-channel configuration. Secrets stay behind credential references."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from app.core.clock import Clock, SystemClock
from app.core.errors import AppError, ErrorCode, ErrorDetail, get_request_id
from app.core.logging import is_sensitive_key
from app.domain.audit_actions import ACTION_AUTHORIZATION_DENIED
from app.domain.enums import ALERT_CHANNEL_TYPES, RISK_LEVELS
from app.domain.errors import DuplicateNameError
from app.domain.permissions import ADMIN, Operation, is_allowed
from app.domain.principal import Principal
from app.domain.records import AlertChannelDraft, AlertChannelRecord, AuditDraft
from app.domain.repositories import AlertRepository, AuditRepository


class AlertChannelService:
    def __init__(
        self,
        alerts: AlertRepository,
        audit: AuditRepository,
        clock: Clock | None = None,
    ) -> None:
        self._alerts = alerts
        self._audit = audit
        self._clock = clock if clock is not None else SystemClock()

    def create(
        self,
        actor: Principal,
        *,
        name: str,
        channel_type: str,
        enabled: bool,
        non_secret_config: Mapping[str, str],
        credential_ref: str | None,
        recipients: tuple[str, ...],
        threshold_level: str,
    ) -> AlertChannelRecord:
        self._require_admin(actor)
        self._validate(channel_type, non_secret_config, recipients, threshold_level)
        now = self._clock.now()
        try:
            channel_id = self._alerts.add_channel(
                self._draft(
                    name,
                    channel_type,
                    enabled,
                    non_secret_config,
                    credential_ref,
                    recipients,
                    threshold_level,
                    actor.user_id,
                    now,
                )
            )
        except DuplicateNameError:
            raise AppError(ErrorCode.CONFLICT, "通道名称已存在") from None
        self._audit.append(self._event(actor.user_id, "ALERT_CHANNEL_CREATED", str(channel_id), now, credential_ref))
        created = self._alerts.get_channel(channel_id)
        if created is None:
            raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "通道保存失败")
        return created

    def update(
        self,
        actor: Principal,
        channel_id: int,
        *,
        name: str,
        channel_type: str,
        enabled: bool,
        non_secret_config: Mapping[str, str],
        credential_ref: str | None,
        recipients: tuple[str, ...],
        threshold_level: str,
    ) -> AlertChannelRecord:
        self._require_admin(actor)
        self._validate(channel_type, non_secret_config, recipients, threshold_level)
        if self._alerts.get_channel(channel_id) is None:
            raise AppError(ErrorCode.NOT_FOUND, "通道不存在")
        now = self._clock.now()
        try:
            self._alerts.update_channel(
                channel_id,
                self._draft(
                    name,
                    channel_type,
                    enabled,
                    non_secret_config,
                    credential_ref,
                    recipients,
                    threshold_level,
                    actor.user_id,
                    now,
                ),
            )
        except DuplicateNameError:
            raise AppError(ErrorCode.CONFLICT, "通道名称已存在") from None
        self._audit.append(self._event(actor.user_id, "ALERT_CHANNEL_UPDATED", str(channel_id), now, credential_ref))
        updated = self._alerts.get_channel(channel_id)
        if updated is None:
            raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "通道保存失败")
        return updated

    def list_channels(self, actor: Principal) -> tuple[AlertChannelRecord, ...]:
        self._require_admin(actor)
        return self._alerts.list_channels()

    def public_view(self, record: AlertChannelRecord) -> dict[str, object]:
        """Return the API shape. The credential reference is a name, never a secret value."""

        return {
            "id": record.id,
            "name": record.name,
            "channel_type": record.channel_type,
            "enabled": record.enabled,
            "non_secret_config": dict(record.non_secret_config),
            "credential_ref": record.credential_ref,
            "recipients": list(record.recipients),
            "threshold_level": record.threshold_level,
        }

    def _require_admin(self, actor: Principal) -> None:
        if actor.role == ADMIN and is_allowed(actor.role, Operation.ALERT_CHANNELS_WRITE):
            return
        self._audit.append(
            self._event(
                actor.user_id,
                ACTION_AUTHORIZATION_DENIED,
                Operation.ALERT_CHANNELS_WRITE.value,
                self._clock.now(),
                None,
            )
        )
        raise AppError(ErrorCode.FORBIDDEN, "权限不足")

    def _validate(
        self,
        channel_type: str,
        non_secret_config: Mapping[str, str],
        recipients: tuple[str, ...],
        threshold_level: str,
    ) -> None:
        if channel_type not in ALERT_CHANNEL_TYPES:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "通道类型无效",
                details=(ErrorDetail(field="channel_type", reason="unsupported"),),
            )
        if threshold_level not in RISK_LEVELS:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "阈值等级无效",
                details=(ErrorDetail(field="threshold_level", reason="unsupported"),),
            )
        if channel_type == "email" and not recipients:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "收件人无效",
                details=(ErrorDetail(field="recipients", reason="required"),),
            )
        sensitive = [key for key in non_secret_config if is_sensitive_key(key)]
        if sensitive:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "配置包含秘密字段",
                details=tuple(ErrorDetail(field=key, reason="secret values are not accepted") for key in sensitive),
            )

    def _draft(
        self,
        name: str,
        channel_type: str,
        enabled: bool,
        non_secret_config: Mapping[str, str],
        credential_ref: str | None,
        recipients: tuple[str, ...],
        threshold_level: str,
        created_by: int,
        updated_at: datetime,
    ) -> AlertChannelDraft:
        return AlertChannelDraft(
            name=name,
            channel_type=channel_type,
            enabled=enabled,
            non_secret_config={str(key): str(value) for key, value in non_secret_config.items()},
            credential_ref=credential_ref,
            recipients=recipients,
            threshold_level=threshold_level,
            created_by=created_by,
            updated_at=updated_at,
        )

    def _event(
        self,
        user_id: int,
        action: str,
        object_id: str,
        created_at: datetime,
        credential_ref: str | None,
    ) -> AuditDraft:
        details = None if credential_ref is None else {"credential_ref": credential_ref}
        return AuditDraft(
            user_id=user_id,
            action=action,
            object_type="operation" if action == ACTION_AUTHORIZATION_DENIED else "alert_channel",
            object_id=object_id,
            request_id=get_request_id(),
            result="DENIED" if action == ACTION_AUTHORIZATION_DENIED else "SUCCESS",
            details=details,
            ip_hash=None,
            created_at=created_at,
        )
