"""Validation for the external source-use confirmation record.

The environment switch is an explicit deployment decision, while this file
provides the auditable evidence that decision is based on.  Keeping the
validator in shared code lets the CLI, scheduler, HTTP layer, collection
adapters and acceptance report enforce the same rule.

Each configured collection source declares a ``provider_name``; the
confirmation record must name that provider so a license for one source can
never silently authorize another.  ``trial_operation`` records require a
``valid_until`` timestamp: once it passes, collection is blocked in every
environment until a renewed or continuous record is installed.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.v2.shared.job_contracts import Sha256


# Adapter key -> provider name the confirmation record must carry.  Adding a
# new source requires adding its adapter and its expected provider here, so a
# Quotsoft confirmation can never authorize the official interface by
# accident.
EXPECTED_PROVIDERS: dict[str, str] = {
    "quotsoft": "Quotsoft",
    "official": "北京市生态环境监测中心官方接口",
}


class LicenseConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=200)
    record_id: str = Field(min_length=1, max_length=200)
    confirmed_by: str = Field(min_length=1, max_length=200)
    confirmed_at: datetime
    scope: Literal["trial_operation", "continuous_business_use"]
    evidence_sha256: Sha256
    reference: str = Field(min_length=1, max_length=500)
    valid_until: datetime | None = None


def read_license_confirmation(path: Path | None) -> dict[str, Any]:
    """Return a non-sensitive summary of a confirmation record."""
    summary: dict[str, Any] = {"configured": path is not None, "available": False, "valid": False}
    if path is None:
        summary["reason"] = "confirmation_file_not_configured"
        return summary
    summary["path"] = str(path)
    if not path.exists():
        summary["reason"] = "confirmation_file_missing"
        return summary
    if not path.is_file():
        summary["reason"] = "confirmation_file_invalid"
        return summary
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = LicenseConfirmation.model_validate(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError):
        summary["reason"] = "confirmation_file_invalid"
        return summary
    summary.update({
        "available": True,
        "provider": record.provider,
        "record_id": record.record_id,
        "confirmed_by": record.confirmed_by,
        "confirmed_at": record.confirmed_at.isoformat(),
        "scope": record.scope,
        "reference": record.reference,
        "valid_until": record.valid_until.isoformat() if record.valid_until else None,
    })
    if record.confirmed_at.tzinfo is None:
        summary["reason"] = "confirmed_at_requires_timezone"
        return summary
    if record.confirmed_at > datetime.now(timezone.utc):
        summary["reason"] = "confirmed_at_is_in_the_future"
        return summary
    if record.scope == "trial_operation" and record.valid_until is None:
        summary["reason"] = "trial_scope_requires_valid_until"
        return summary
    if record.valid_until is not None:
        if record.valid_until.tzinfo is None:
            summary["reason"] = "valid_until_requires_timezone"
            return summary
        if record.valid_until <= datetime.now(timezone.utc):
            summary["reason"] = "valid_until_expired"
            return summary
    summary["valid"] = True
    return summary


def license_state(settings: Any) -> dict[str, Any]:
    """Structured gate result for collection enforcement.

    Returns ``state`` of ``ok``, ``unconfigured`` or ``blocked``.  A missing
    confirmation file is "unconfigured" (allowed outside production, as
    before); any present-but-invalid record — including an expired
    ``valid_until`` — is "blocked" in every environment so a lapsed trial
    authorization can never keep collecting.
    """
    summary = read_license_confirmation(getattr(settings, "source_license_confirmation_file", None))
    expected = EXPECTED_PROVIDERS.get(getattr(settings, "source_provider", ""))
    summary["source_provider"] = getattr(settings, "source_provider", None)
    summary["expected_provider"] = expected
    summary["switch"] = bool(getattr(settings, "source_license_confirmed", False))
    summary["provider_match"] = summary.get("provider") == expected if expected else False
    reason = summary.get("reason")
    if summary["valid"] and summary["provider_match"] and summary["switch"]:
        summary["state"] = "ok"
    elif not summary["switch"] or reason in {"confirmation_file_missing", "confirmation_file_not_configured"}:
        summary["state"] = "unconfigured"
    else:
        summary["state"] = "blocked"
    summary["ready"] = summary["state"] == "ok"
    return summary
