from datetime import date

from scripts.audit_bundled_corpus import audit

TODAY = date(2026, 9, 16)


def test_audit_flags_stale_and_missing_fields():
    docs = [
        {"id": "A-1", "title": "Old policy", "airline": "indigo", "last_updated": "2024-01-01"},
    ]
    report = audit(docs, today=TODAY)

    assert report["total_documents"] == 1
    assert report["missing_source_url"] == 1
    assert report["missing_effective_date"] == 1
    assert report["missing_verified_date"] == 1
    assert report["stale_by_last_updated"] == 1
    doc = report["documents"][0]
    assert doc["age_days"] > 365
    assert doc["stale"] is True


def test_audit_does_not_flag_recent_document_as_stale():
    docs = [
        {"id": "A-1", "title": "Fresh policy", "airline": "indigo", "last_updated": "2026-09-01"},
    ]
    report = audit(docs, today=TODAY)

    assert report["stale_by_last_updated"] == 0
    assert report["documents"][0]["stale"] is False


def test_audit_respects_custom_stale_threshold():
    docs = [
        {"id": "A-1", "title": "Policy", "airline": "indigo", "last_updated": "2026-08-01"},
    ]
    report = audit(docs, today=TODAY, stale_days=10)
    assert report["documents"][0]["stale"] is True


def test_audit_does_not_flag_missing_fields_when_present():
    docs = [
        {
            "id": "A-1", "title": "Policy", "airline": "indigo", "last_updated": "2026-09-01",
            "source_url": "https://example.com/policy", "effective_date": "2026-01-01",
            "verified_date": "2026-09-01",
        },
    ]
    report = audit(docs, today=TODAY)

    assert report["missing_source_url"] == 0
    assert report["missing_effective_date"] == 0
    assert report["missing_verified_date"] == 0


def test_audit_handles_unparseable_last_updated():
    docs = [
        {"id": "A-1", "title": "Policy", "airline": "indigo", "last_updated": "not-a-date"},
    ]
    report = audit(docs, today=TODAY)

    doc = report["documents"][0]
    assert doc["age_days"] is None
    assert doc["stale"] is False
    assert doc["unparseable_last_updated"] is True
    assert report["unparseable_last_updated"] == 1


def test_audit_handles_missing_last_updated():
    docs = [{"id": "A-1", "title": "Policy", "airline": "indigo"}]
    report = audit(docs, today=TODAY)

    doc = report["documents"][0]
    assert doc["age_days"] is None
    assert doc["stale"] is False
    assert doc["unparseable_last_updated"] is False


def test_audit_defaults_airline_to_indigo_when_absent():
    docs = [{"id": "A-1", "title": "Policy", "last_updated": "2026-09-01"}]
    report = audit(docs, today=TODAY)
    assert report["documents"][0]["airline"] == "indigo"


def test_audit_over_real_bundled_corpus_runs_without_error():
    """Smoke test against the actual data/*.py corpus — the audit script
    itself, not a snapshot of current staleness (which will drift over
    time and is not something a test should assert on)."""
    from scripts.audit_bundled_corpus import _load_all_documents

    docs = _load_all_documents()
    report = audit(docs, today=date.today())

    assert report["total_documents"] == len(docs) == 78
    assert all("doc_id" in d for d in report["documents"])
