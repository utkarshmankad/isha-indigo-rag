from qdrant_client import QdrantClient

from src.documents.document_store import DocumentStore, build_record


def _store():
    client = QdrantClient(":memory:")
    return DocumentStore(client, collection_name="test_documents")


def test_put_and_get_round_trips_record():
    store = _store()
    record = build_record(
        doc_id="doc_1", title="Baggage Policy", category="baggage", airline="indigo",
        original_content="Full original policy text.", uploaded_by="tenant-1",
        source_url="https://example.com/policy", effective_date="2026-01-01",
    )

    store.put(record)
    fetched = store.get("doc_1")

    assert fetched["original_content"] == "Full original policy text."
    assert fetched["source_url"] == "https://example.com/policy"
    assert fetched["effective_date"] == "2026-01-01"
    assert fetched["version"] == 1


def test_get_missing_doc_returns_none():
    store = _store()
    assert store.get("does-not-exist") is None


def test_put_overwrites_existing_record():
    store = _store()
    store.put(build_record(
        doc_id="doc_1", title="Old", category="baggage", airline="indigo",
        original_content="old text", uploaded_by="tenant-1",
    ))
    previous = store.get("doc_1")
    store.put(build_record(
        doc_id="doc_1", title="New", category="baggage", airline="indigo",
        original_content="new text", uploaded_by="tenant-1", previous=previous,
    ))

    fetched = store.get("doc_1")
    assert fetched["title"] == "New"
    assert fetched["original_content"] == "new text"
    assert fetched["version"] == 2
    assert fetched["created_at"] == previous["created_at"]


def test_delete_removes_record():
    store = _store()
    store.put(build_record(
        doc_id="doc_1", title="T", category="baggage", airline="indigo",
        original_content="text", uploaded_by="tenant-1",
    ))
    store.delete("doc_1")
    assert store.get("doc_1") is None


def test_list_for_airline_filters_by_airline():
    store = _store()
    store.put(build_record(
        doc_id="doc_1", title="T1", category="baggage", airline="indigo",
        original_content="text", uploaded_by="tenant-1",
    ))
    store.put(build_record(
        doc_id="doc_2", title="T2", category="baggage", airline="spicejet",
        original_content="text", uploaded_by="tenant-2",
    ))

    indigo_docs = store.list_for_airline("indigo")
    assert [r["doc_id"] for r in indigo_docs] == ["doc_1"]


def test_build_record_first_version_has_no_previous():
    record = build_record(
        doc_id="doc_1", title="T", category="baggage", airline="indigo",
        original_content="text", uploaded_by="tenant-1",
    )
    assert record["version"] == 1
    assert record["created_at"] == record["updated_at"]


def test_build_record_defaults_to_pending_status():
    record = build_record(
        doc_id="doc_1", title="T", category="baggage", airline="indigo",
        original_content="text", uploaded_by="tenant-1",
    )
    assert record["status"] == "pending"
    assert record["superseded_by"] is None


def test_build_record_carries_supersedes():
    record = build_record(
        doc_id="doc_2", title="T", category="baggage", airline="indigo",
        original_content="text", uploaded_by="tenant-1", supersedes="doc_1",
    )
    assert record["supersedes"] == "doc_1"


def test_put_archives_previous_version_into_history():
    store = _store()
    store.put(build_record(
        doc_id="doc_1", title="Old", category="baggage", airline="indigo",
        original_content="old text", uploaded_by="tenant-1",
    ))
    previous = store.get("doc_1")
    store.put(build_record(
        doc_id="doc_1", title="New", category="baggage", airline="indigo",
        original_content="new text", uploaded_by="tenant-1", previous=previous,
    ))

    versions = store.list_versions("doc_1")
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["original_content"] == "old text"
    assert versions[1]["original_content"] == "new text"


def test_list_versions_single_version_returns_current_only():
    store = _store()
    store.put(build_record(
        doc_id="doc_1", title="T", category="baggage", airline="indigo",
        original_content="text", uploaded_by="tenant-1",
    ))
    versions = store.list_versions("doc_1")
    assert [v["version"] for v in versions] == [1]


def test_patch_updates_fields_without_bumping_version_or_history():
    store = _store()
    store.put(build_record(
        doc_id="doc_1", title="T", category="baggage", airline="indigo",
        original_content="text", uploaded_by="tenant-1",
    ))

    updated = store.patch("doc_1", status="approved")

    assert updated["status"] == "approved"
    fetched = store.get("doc_1")
    assert fetched["status"] == "approved"
    assert fetched["version"] == 1
    assert store.list_versions("doc_1") == [fetched]


def test_patch_missing_doc_returns_none():
    store = _store()
    assert store.patch("does-not-exist", status="approved") is None


def test_find_by_content_hash_matches_same_airline_and_hash():
    store = _store()
    record = build_record(
        doc_id="doc_1", title="Baggage Policy", category="baggage", airline="indigo",
        original_content="Full text.", uploaded_by="tenant-1",
    )
    store.put(record)

    found = store.find_by_content_hash("indigo", record["content_hash"])
    assert found["doc_id"] == "doc_1"


def test_find_by_content_hash_ignores_other_airline():
    store = _store()
    record = build_record(
        doc_id="doc_1", title="Baggage Policy", category="baggage", airline="indigo",
        original_content="Full text.", uploaded_by="tenant-1",
    )
    store.put(record)

    assert store.find_by_content_hash("spicejet", record["content_hash"]) is None


def test_find_by_content_hash_ignores_rejected_and_superseded():
    store = _store()
    record = build_record(
        doc_id="doc_1", title="Baggage Policy", category="baggage", airline="indigo",
        original_content="Full text.", uploaded_by="tenant-1",
    )
    store.put(record)
    store.patch("doc_1", status="rejected")

    assert store.find_by_content_hash("indigo", record["content_hash"]) is None


def test_list_for_airline_filters_by_status():
    store = _store()
    store.put(build_record(
        doc_id="doc_1", title="T1", category="baggage", airline="indigo",
        original_content="text", uploaded_by="tenant-1",
    ))
    store.patch("doc_1", status="approved")
    store.put(build_record(
        doc_id="doc_2", title="T2", category="baggage", airline="indigo",
        original_content="text2", uploaded_by="tenant-1",
    ))

    pending = store.list_for_airline("indigo", status="pending")
    assert [r["doc_id"] for r in pending] == ["doc_2"]
