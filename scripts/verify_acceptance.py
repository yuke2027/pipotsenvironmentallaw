"""Verify a generated online-acceptance report without changing platform state."""

import argparse
import json
from pathlib import Path


REQUIRED_GATES = (
    "seven_full_days_elapsed",
    "collection_coverage_passed",
    "license_gate_passed",
    "backup_gate_passed",
    "production_signoff_passed",
)


def evaluate_report(report: dict) -> dict:
    """Return a stable, machine-readable verification summary."""
    failed = [gate for gate in REQUIRED_GATES if report.get(gate) is not True]
    return {
        "passed": not failed,
        "failed_gates": failed,
        "generated_at": report.get("generated_at"),
        "earliest_review_at": report.get("earliest_review_at"),
        "license_evidence": report.get("license_evidence", {}),
        "backup_evidence": report.get("backup_evidence", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an online acceptance report")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(".artifacts/online-acceptance-current-window.json"),
    )
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    if not isinstance(report, dict):
        print(json.dumps({"passed": False, "error": "report must be a JSON object"}, ensure_ascii=False))
        return 2
    result = evaluate_report(report)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
