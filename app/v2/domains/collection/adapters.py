"""Per-source collection adapters and the source registry.

``resolve_adapter`` is the single entry point for picking a data source.  The
active source is chosen explicitly via ``ESP_SOURCE_PROVIDER``; an unknown key
fails closed instead of silently falling back.  Each adapter declares the
provider name its license confirmation must carry, and ``collect`` enforces
the license gate before any network traffic: a missing record is only allowed
outside production, while an expired or invalid record blocks collection
everywhere.
"""

from datetime import date
from typing import Any, Protocol

from app.v2.domains.collection.repository import collect_range, import_file
from app.v2.shared.license import license_state


class SourceLicenseError(ValueError):
    """Raised when collection is requested without a usable authorization."""


class SourceAdapter(Protocol):
    key: str
    provider_name: str
    attribution: str

    def collect(self, start: date, end: date, job_id: str, progress: Any) -> dict[str, Any]: ...

    def import_file(self, content: bytes, kind: str) -> dict[str, Any]: ...


def _enforce_license(configuration: Any, provider_name: str) -> None:
    state = license_state(configuration)
    if state["state"] == "ok":
        return
    if state["state"] == "unconfigured" and getattr(configuration, "environment", "") != "production":
        return
    detail = state.get("reason") or "provider_mismatch_or_unconfirmed"
    raise SourceLicenseError(
        f"数据源 {provider_name} 的采集许可不可用（{detail}）。"
        "请检查 ESP_SOURCE_LICENSE_CONFIRMED 与授权确认文件后重试")


class QuotsoftAdapter:
    """Quotsoft daily wide-table files; behaviour identical to the legacy path."""

    key = "quotsoft"
    provider_name = "Quotsoft"
    attribution = "Quotsoft / 北京市生态环境监测中心"

    def __init__(self, db: Any, store: Any, configuration: Any) -> None:
        self.db, self.store, self.configuration = db, store, configuration

    def collect(self, start: date, end: date, job_id: str, progress: Any) -> dict[str, Any]:
        _enforce_license(self.configuration, self.provider_name)
        return collect_range(self.db, self.store, self.configuration, start, end, job_id, progress)

    def import_file(self, content: bytes, kind: str) -> dict[str, Any]:
        # Manual uploads use files the operator already holds; the remote-use
        # license only gates scheduled/remote collection.
        return import_file(self.db, self.store, content, kind)


class OfficialSourceAdapter:
    """Boundary for the government monitoring interface.

    Registered so ``ESP_SOURCE_PROVIDER=official`` fails loudly and explicitly
    until the interface specification and endpoint are delivered; there is no
    silent fallback to Quotsoft.
    """

    key = "official"
    provider_name = "北京市生态环境监测中心官方接口"
    attribution = "北京市生态环境监测中心官方接口"

    def __init__(self, db: Any, store: Any, configuration: Any) -> None:
        self.db, self.store, self.configuration = db, store, configuration

    def collect(self, start: date, end: date, job_id: str, progress: Any) -> dict[str, Any]:
        _enforce_license(self.configuration, self.provider_name)
        raise NotImplementedError("官方数据源接口尚未接入：需取得接口规范、接入凭证与授权后实现")

    def import_file(self, content: bytes, kind: str) -> dict[str, Any]:
        raise NotImplementedError("官方数据源接口尚未接入：需取得接口规范、接入凭证与授权后实现")


ADAPTERS: dict[str, type[QuotsoftAdapter] | type[OfficialSourceAdapter]] = {
    QuotsoftAdapter.key: QuotsoftAdapter,
    OfficialSourceAdapter.key: OfficialSourceAdapter,
}


def adapter_keys() -> list[str]:
    return sorted(ADAPTERS)


def resolve_adapter(key: str, db: Any, store: Any, configuration: Any) -> SourceAdapter:
    cls = ADAPTERS.get(key)
    if cls is None:
        raise ValueError(
            f"未知数据源 '{key}'（可用：{', '.join(adapter_keys())}）；"
            "禁止自动回退，请显式设置 ESP_SOURCE_PROVIDER")
    return cls(db, store, configuration)


# Backwards-compatible name kept for callers migrated earlier in the v2
# refactor.
LegacyCollectionAdapter = QuotsoftAdapter
