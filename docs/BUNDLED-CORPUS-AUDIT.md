# Bundled corpus audit (Weeks 3-4, item 4)

`scripts/audit_bundled_corpus.py` reports, without modifying anything,
which bundled documents (`data/*.py`) are missing an authoritative source
URL, an effective date, or a verified-as-current date, and which are stale
by `last_updated`. It does not fabricate any of that data — filling in real
URLs and dates is a content/product decision that requires someone to go
check the airlines' actual current policies, not something a script should
guess at.

`src/ingestion/chunker.py` now also passes `source_url`, `effective_date`,
and `verified_date` through to chunk metadata for bundled documents (as
`None` when absent), matching the schema self-serve documents already carry
via `src/documents/document_store.py` — so the fields are ready to be
populated per-document going forward without another schema change.

## Snapshot as of 2026-09-16

Run: `.venv/bin/python scripts/audit_bundled_corpus.py`

```
Total documents:            78
Missing source_url:         78
Missing effective_date:     78
Missing verified_date:      78
Stale (by last_updated):    78
Unparseable last_updated:   0
```

Every bundled document — all 78, across IndiGo, Air India, SpiceJet, and
DGCA — is missing all three provenance fields (the schema simply never had
them until this item), and every `last_updated` value is more than 670
days old (all dated between 2024-06-15 and 2024-11-15). This confirms the
gap called out in the Weeks 3-4 roadmap: nothing has verified whether this
content still matches the airlines' actual current policies.

## What this item delivers vs. what it doesn't

**Delivered**: the tooling to detect and report this gap on demand
(`scripts/audit_bundled_corpus.py`, tested in
`tests/test_audit_bundled_corpus.py`), and the schema to record the fix
once someone does it (chunk metadata now carries `source_url`,
`effective_date`, `verified_date` for bundled docs).

**Not delivered, and out of scope for this PR**: actually reviewing each of
the 78 bundled documents against the airlines' current published policies,
sourcing real URLs, and setting real effective/verified dates. That is
substantial manual content work — around 78 documents across 3 airlines —
not a coding task, and this audit deliberately does not invent placeholder
values that would look authoritative without being checked.

## Re-running the audit

```sh
.venv/bin/python scripts/audit_bundled_corpus.py               # human-readable table
.venv/bin/python scripts/audit_bundled_corpus.py --json         # machine-readable
.venv/bin/python scripts/audit_bundled_corpus.py --stale-days 180  # different threshold
```
