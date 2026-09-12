# Qdrant backup and recovery

The application uses Qdrant, not Postgres. Free clusters can suspend after one
week and be deleted after four weeks of inactivity unless reactivated. Check the
Cloud dashboard and reactivate a suspended cluster before recovery attempts.
See https://qdrant.tech/documentation/cloud/create-cluster/.

Stop uploads and ingestion while taking a backup. Export count checks detect some
concurrent changes but cannot detect same-count content edits. This procedure is
for ISHA's single-node, single dense-vector collection. Multi-node snapshots must
be taken per node; aliases are not included in collection snapshots.

```sh
uv run python scripts/qdrant_backup.py backup --directory /secure/backups/isha-YYYYMMDD
uv run python scripts/qdrant_backup.py verify --directory /secure/backups/isha-YYYYMMDD
uv run python scripts/qdrant_backup.py restore --directory /secure/backups/isha-YYYYMMDD --local-path /secure/drills/isha-YYYYMMDD --target recovered_kb
```

A backup includes all stored vectors and payload text (including self-serve
uploads), bundled source documents, vector configuration, payload index types,
checksums and a downloaded native snapshot. Original uploaded files were not
retained by the old application; exported chunk text cannot reconstruct original
formatting or material discarded during chunking. Retain originals separately.
Never commit these files or upload them as public CI artifacts. Keep another
copy on protected storage outside the application host. A backup is complete
only when the command succeeds and `verify` succeeds. Do not reuse an existing
backup directory. A failed native download may leave a valid portable export;
retry to a new directory and investigate the failed snapshot operation.

For cloud recovery, configure the destination QDRANT_URL/QDRANT_API_KEY (or use
`--env-file /secure/destination.env`) and restore into a **new** collection:

```sh
uv run python scripts/qdrant_backup.py restore --directory /secure/backups/isha-YYYYMMDD --target recovered_kb
```

Restore never replaces an existing collection. On failure, leave production
traffic unchanged and inspect the isolated target before retrying with a new
name. Validate exact count, a known point's payload and a retrieval query before
changing application configuration to the recovered collection. Current app
constructors default to `airline_kb`; change deployment collection configuration
explicitly when switching. Never run `ingest.py --reset` as an outage remedy:
it destroys uploaded content that is absent from bundled Python documents.

Native snapshot restoration requires a compatible Qdrant server and restores
server-specific collection state. Follow https://qdrant.tech/documentation/snapshots/
for upload/recovery; test on a separate server/collection first. Local-backend
restore drills exercise the portable export, not native snapshot recovery.
