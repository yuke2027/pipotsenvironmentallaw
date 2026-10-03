"""Validation for the external source-use confirmation record.

The environment switch is an explicit deployment decision, while this file
provides the auditable evidence that decision is based on.  Keeping the
validator in shared code lets the CLI, scheduler, HTTP layer and acceptance
report enforce the same rule.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.v2.shared.job_contracts import Sha256


class LicenseConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["Quotsoft"]
    record_id: str = Field(min_length=1, max_length=200)
    confirmed_by: str = Field(min_length=1, max_length=200)
    confirmed_at: datetime
    scope: Literal["continuous_business_use"]
    evidence_sha256: Sha256
    reference: str = Field(min_length=1, max_length=500)


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
    })
    if record.confirmed_at.tzinfo is None:
        summary["reason"] = "confirmed_at_requires_timezone"
        return summary
    if record.confirmed_at > datetime.now(timezone.utc):
        summary["reason"] = "confirmed_at_is_in_the_future"
        return summary
    summary["valid"] = True
    return summary
