"""User administration use cases; transactions are supplied by the caller."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.v2.shared.errors import DomainError


@dataclass(frozen=True)
class NewAccount:
    username: str
    display_name: str
    role: str
    password_hash: str


class UserAdministrationPort(Protocol):
    def people(self) -> dict[str, Any]: ...

    def users(self) -> dict[str, Any]: ...

    def audits(self, page_number: int) -> dict[str, Any]: ...

    def get_user(self, identifier: str) -> dict[str, Any] | None: ...

    def create_user(self, account: NewAccount) -> dict[str, Any]: ...

    def update_user(self, identifier: str, role: str, active: bool) -> dict[str, Any]: ...

    def revoke_user_sessions(self, identifier: str) -> None: ...

    def audit(self, actor_id: str, action: str, identifier: str, detail: dict[str, Any] | None) -> None: ...


class UserAdministrationService:
    def __init__(self, port: UserAdministrationPort):
        self.port = port

    def list_people(self) -> dict[str, Any]:
        return self.port.people()

    def list_users(self) -> dict[str, Any]:
        return self.port.users()

    def list_audits(self, page_number: int) -> dict[str, Any]:
        return self.port.audits(page_number)

    def create_user(self, actor_id: str, account: NewAccount) -> dict[str, Any]:
        result = self.port.create_user(account)
        self.port.audit(actor_id, "CREATE_USER", result["id"], {"role": account.role})
        return result

    def update_user(self, actor_id: str, identifier: str, role: str, active: bool) -> dict[str, Any]:
        if self.port.get_user(identifier) is None:
            raise DomainError("NOT_FOUND", "记录不存在")
        if actor_id == identifier and (not active or role != "管理员"):
            raise DomainError("VALIDATION_ERROR", "不能禁用或降级当前管理员")
        result = self.port.update_user(identifier, role, active)
        self.port.revoke_user_sessions(identifier)
        self.port.audit(actor_id, "UPDATE_USER", identifier, {"role": role, "active": active})
        return result


class AdminReadPort(Protocol):
    def standards(self) -> dict[str, Any]: ...

    def laws(self) -> dict[str, Any]: ...

    def notifications(self, user_id: str) -> dict[str, Any]: ...

    def sources(self, license_summary: dict[str, Any]) -> dict[str, Any]: ...

    def models(self) -> dict[str, Any]: ...

    def channels(self) -> dict[str, Any]: ...


class AdminReadService:
    def __init__(self, port: AdminReadPort):
        self.port = port

    def list_standards(self) -> dict[str, Any]:
        return self.port.standards()

    def list_laws(self) -> dict[str, Any]:
        return self.port.laws()

    def list_notifications(self, user_id: str) -> dict[str, Any]:
        return self.port.notifications(user_id)

    def list_sources(self, license_summary: dict[str, Any]) -> dict[str, Any]:
        return self.port.sources(license_summary)

    def list_models(self) -> dict[str, Any]:
        return self.port.models()

    def list_channels(self) -> dict[str, Any]:
        return self.port.channels()


class AdminWritePort(Protocol):
    def mark_notification_read(self, identifier: str, user_id: str) -> dict[str, Any] | None: ...

    def activate_model(self, identifier: str, actor_id: str) -> dict[str, Any]: ...

    def rollback_model(self, task: str, actor_id: str) -> dict[str, Any]: ...

    def add_law(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...

    def update_station(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...

    def add_alias(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...

    def add_channel(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...

    def toggle_channel(self, identifier: str, enabled: bool, actor_id: str) -> dict[str, Any]: ...

    def end_standard(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...

    def end_law(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...

    def add_standard(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...


class AdminWriteService:
    def __init__(self, port: AdminWritePort):
        self.port = port

    def mark_notification_read(self, identifier: str, user_id: str) -> dict[str, Any] | None:
        return self.port.mark_notification_read(identifier, user_id)

    def activate_model(self, identifier: str, actor_id: str) -> dict[str, Any]:
        return self.port.activate_model(identifier, actor_id)

    def rollback_model(self, task: str, actor_id: str) -> dict[str, Any]:
        return self.port.rollback_model(task, actor_id)

    def add_law(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return self.port.add_law(values, actor_id)

    def update_station(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return self.port.update_station(identifier, values, actor_id)

    def add_alias(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return self.port.add_alias(identifier, values, actor_id)

    def add_channel(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return self.port.add_channel(values, actor_id)

    def toggle_channel(self, identifier: str, enabled: bool, actor_id: str) -> dict[str, Any]:
        return self.port.toggle_channel(identifier, enabled, actor_id)

    def end_standard(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return self.port.end_standard(identifier, values, actor_id)

    def end_law(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return self.port.end_law(identifier, values, actor_id)

    def add_standard(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return self.port.add_standard(values, actor_id)
