# Qdrant readiness monitoring

The `Qdrant readiness monitor` GitHub Actions workflow runs daily at 03:17 UTC
(08:47 IST), outside the application host, and supports manual dispatch. Existing
repository secrets `QDRANT_URL` and `QDRANT_API_KEY` provide authentication. Set
repository variable `QDRANT_COLLECTION` only if using a non-default collection.
Use a read-only Qdrant key for monitoring where possible.

The probe reads the collection and one point without payloads or vectors. It
makes no OpenAI calls and returns nonzero for an unavailable, unhealthy or empty
collection. Each request has a 10-second timeout and the workflow has a five-minute
cap. Output excludes credentials, endpoint URLs and document contents.

```sh
uv run python scripts/check_qdrant.py --env-file /secure/isha.env
```

A failed run produces an Actions error and job summary. In GitHub account
notification settings, enable Actions failure notifications and verify that the
workflow owner receives them. The code does not silently create a new email or
third-party alert destination. Notification delivery remains subject to those
account settings; inspect a deliberately failing non-production run when setting
up delivery.

GitHub schedules run only from the default branch, can be delayed, and scheduled
workflows in public repositories may be disabled after prolonged repository
inactivity. Inspect Actions periodically. This monitor is not an uptime guarantee.

Qdrant documents suspension after one week and deletion after four weeks of
inactivity unless reactivated. An authenticated point read provides real database
activity, but verify its effect in the dashboard over a full inactivity period;
this change cannot establish that behavior immediately. Do not use costly LLM
queries or artificial writes as a keep-alive.

On failure: inspect the dashboard, reactivate if suspended, check secret and
collection configuration, then dispatch the monitor again. Never reset the
collection to fix connectivity. Follow the backup/recovery runbook if deleted.

References:
- https://qdrant.tech/documentation/cloud/create-cluster/
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
