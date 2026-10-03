"""Application services for enforcement read use cases."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ListFilter:
    query: str = ""
    status: str | None = None
    page_number: int = 1
    page_size: int = 20


class EnforcementReadPort(Protocol):
    def enterprises(self, filters: ListFilter) -> dict[str, Any]: ...

    def leads(self, filters: ListFilter) -> dict[str, Any]: ...

    def inspections(self, filters: ListFilter) -> dict[str, Any]: ...


class EnforcementReadService:
    def __init__(self, read_port: EnforcementReadPort) -> None:
        self.read_port = read_port

    def list_enterprises(self, filters: ListFilter) -> dict[str, Any]:
        return self.read_port.enterprises(filters)

    def list_leads(self, filters: ListFilter) -> dict[str, Any]:
        return self.read_port.leads(filters)

    def list_inspections(self, filters: ListFilter) -> dict[str, Any]:
        return self.read_port.inspections(filters)


class EnforcementWritePort(Protocol):
    def create_enterprise(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...
    def enterprise_detail(self, identifier: str, user: Any) -> dict[str, Any]: ...
    def update_enterprise(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...
    def add_enterprise_record(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...
    def create_lead(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...
    def assign_lead(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...
    def claim_lead(self, identifier: str, actor_id: str) -> dict[str, Any]: ...
    def reject_lead(self, identifier: str, reason: str, actor_id: str) -> dict[str, Any]: ...
    def inspection_detail(self, identifier: str, user: Any) -> dict[str, Any]: ...
    def save_inspection(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...
    def transition(self, identifier: str, values: dict[str, Any], actor_id: str, manager: bool) -> dict[str, Any]: ...
    def add_rectification(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...
    def update_rectification(self, identifier: str, rectification_id: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: ...
    def upload_attachment(self, content: bytes, filename: str, inspection_id: str | None,
                          enterprise_id: str | None, replaces_id: str | None,
                          actor_id: str) -> dict[str, Any]: ...
    def prepare_attachment_download(self, identifier: str, user: Any) -> dict[str, Any]: ...


class EnforcementWriteService:
    def __init__(self, write_port: EnforcementWritePort) -> None:
        self.write_port = write_port

    def create_enterprise(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]: return self.write_port.create_enterprise(values, actor_id)
    def enterprise_detail(self, identifier: str, user: Any) -> dict[str, Any]: return self.write_port.enterprise_detail(identifier, user)
    def update_enterprise(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: return self.write_port.update_enterprise(identifier, values, actor_id)
    def add_enterprise_record(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: return self.write_port.add_enterprise_record(identifier, values, actor_id)
    def create_lead(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]: return self.write_port.create_lead(values, actor_id)
    def assign_lead(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: return self.write_port.assign_lead(identifier, values, actor_id)
    def claim_lead(self, identifier: str, actor_id: str) -> dict[str, Any]: return self.write_port.claim_lead(identifier, actor_id)
    def reject_lead(self, identifier: str, reason: str, actor_id: str) -> dict[str, Any]: return self.write_port.reject_lead(identifier, reason, actor_id)
    def inspection_detail(self, identifier: str, user: Any) -> dict[str, Any]: return self.write_port.inspection_detail(identifier, user)
    def save_inspection(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: return self.write_port.save_inspection(identifier, values, actor_id)
    def transition(self, identifier: str, values: dict[str, Any], actor_id: str, manager: bool) -> dict[str, Any]: return self.write_port.transition(identifier, values, actor_id, manager)
    def add_rectification(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]: return self.write_port.add_rectification(identifier, values, actor_id)
    def update_rectification(self, identifier: str, rectification_id: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return self.write_port.update_rectification(identifier, rectification_id, values, actor_id)
    def upload_attachment(self, content: bytes, filename: str, inspection_id: str | None, enterprise_id: str | None, replaces_id: str | None, actor_id: str) -> dict[str, Any]:
        return self.write_port.upload_attachment(content, filename, inspection_id, enterprise_id, replaces_id, actor_id)
    def prepare_attachment_download(self, identifier: str, user: Any) -> dict[str, Any]:
        return self.write_port.prepare_attachment_download(identifier, user)
