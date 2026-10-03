# Online acceptance runbook

This runbook records the evidence required for the production sign-off of the
seven-day online collection window. The report is read-only: it never changes
observations, source files, jobs, or model artifacts.

## Start a window

Record one UTC start time and use the same value for every report. The current
window is:

```text
2026-10-01T14:00:00+00:00
```

Generate the report from the platform image and write it into the host
artifacts directory:

```powershell
docker compose -f compose.platform.yml run --rm --no-deps --user 0:0 `
  -v "${PWD}/.artifacts:/workspace/.artifacts" api `
  python -m scripts.online_acceptance_report `
  --since 2026-10-01T14:00:00+00:00 `
  --output /workspace/.artifacts/online-acceptance-current-window.json
```

Verify the report without changing platform state. The command exits with
status 0 only when every production gate is true:

```powershell
docker compose -f compose.platform.yml run --rm --no-deps `
  -v "${PWD}/.artifacts:/workspace/.artifacts" api `
  python -m scripts.verify_acceptance `
  --report /workspace/.artifacts/online-acceptance-current-window.json
```

The API image includes the report and verification modules. The `--user 0:0` option is only for
writing the host bind mount on Docker Desktop; it does not grant the running
API, worker, or scheduler extra privileges.

## Daily review

After the scheduled collection run, regenerate the report and inspect every
day in `days`:

- at least one collection job is `succeeded` or `partial`;
- job progress is 100 for completed jobs and retry counts are explainable;
- `source_attempt_counts` records successes and failures;
- `source_file_counts` records both origin and `is_current` revision state;
- missing files, source revisions, notifications, and backup evidence have a
  corresponding operational record.

The report also records the newest restore verification under
`backup_evidence`. A valid backup record must have `available=true` and
`checksums_verified=true`.

`earliest_review_at` is written into the report from the recorded `since`
timestamp. Do not approve the window before that instant, even if individual
collection jobs have succeeded.

## Final sign-off

Sign-off requires all of the following fields in the report to be true:

```json
{
  "seven_full_days_elapsed": true,
  "collection_coverage_passed": true,
  "license_gate_passed": true,
  "backup_gate_passed": true,
  "production_signoff_passed": true
}
```

The source-use license must be confirmed by the deployment owner before
setting `ESP_SOURCE_LICENSE_CONFIRMED=true`; retain a JSON confirmation record
at `var/platform/source-license-confirmation.json` (or configure
`ESP_SOURCE_LICENSE_CONFIRMATION_FILE`). The configured confirmation file is
included in the file backup manifest. The record must identify Quotsoft,
the confirming person, a timestamp with timezone, the continuous-business-use
scope, an audit record id, a reference, and the signed evidence SHA-256. The
scheduler, the `collect` CLI, and the API intentionally refuse online
collection in production until both the flag and record are valid.

Do not replace elapsed time with a synthetic job history or a one-time startup
check. For the current window the earliest valid seven-day review is
`2026-10-08T14:00:00+00:00`.
