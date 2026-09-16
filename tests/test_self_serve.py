from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.self_serve import (
    DuplicateDocumentError,
    OwnershipError,
    UploadValidationError,
    approve_document_for_tenant,
    delete_document_for_tenant,
    get_version_history_for_tenant,
    ingest_document_for_tenant,
    reject_document_for_tenant,
    update_document_for_tenant,
    validate_upload,
)
from src.tenancy.registry import TenantConfig

TENANT = TenantConfig("indigo", "indigo", "IndiGo (6E)", "test-key")


def test_validate_upload_rejects_missing_title():
    with pytest.raises(UploadValidationError):
        validate_upload("", "some content that is long enough to pass the minimum length check")


def test_validate_upload_rejects_too_short_content():
    with pytest.raises(UploadValidationError):
        validate_upload("Title", "too short")


def test_validate_upload_accepts_valid_input():
    validate_upload("Title", "x" * 100)  # should not raise


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_tags_tenant_airline(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()

    result = ingest_document_for_tenant(
        TENANT, "Test Policy", "x" * 100, "baggage", manager,
    )

    assert result["chunk_count"] >= 1
    manager.add_document.assert_called_once()
    (record, added_chunks), _ = manager.add_document.call_args
    assert all(c["metadata"]["airline"] == "indigo" for c in added_chunks)
    assert all(c["metadata"]["status"] == "pending" for c in added_chunks)
    assert record["airline"] == "indigo"
    assert record["status"] == "pending"
    assert record["original_content"] == "x" * 100


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_cannot_be_tagged_to_another_airline(mock_embed):
    """The tenant object, not any caller-supplied string, decides the airline tag."""
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()
    spicejet_tenant = TenantConfig("spicejet", "spicejet", "SpiceJet (SG)", "sj-key")

    ingest_document_for_tenant(spicejet_tenant, "Test Policy", "x" * 100, "baggage", manager)

    (record, added_chunks), _ = manager.add_document.call_args
    assert all(c["metadata"]["airline"] == "spicejet" for c in added_chunks)
    assert record["airline"] == "spicejet"


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_doc_id_is_airline_prefixed(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()

    result = ingest_document_for_tenant(TENANT, "Test Policy", "x" * 100, "baggage", manager)

    assert result["doc_id"].startswith("SELFSERVE-INDIGO-")


@patch("src.ingestion.self_serve.embed_chunks")
def test_update_document_requires_ownership(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()

    with pytest.raises(OwnershipError):
        update_document_for_tenant(
            TENANT, "SELFSERVE-SPICEJET-other-doc-123", "Title", "x" * 100, "baggage", manager,
        )
    manager.update_document.assert_not_called()


@patch("src.ingestion.self_serve.embed_chunks")
def test_update_document_rejects_non_self_serve_doc_id(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()

    with pytest.raises(OwnershipError):
        update_document_for_tenant(TENANT, "BAGGAGE-POLICY-001", "Title", "x" * 100, "baggage", manager)
    manager.update_document.assert_not_called()


@patch("src.ingestion.self_serve.embed_chunks")
def test_update_document_calls_index_manager_for_owned_doc(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()
    doc_id = "SELFSERVE-INDIGO-old-title-123"

    result = update_document_for_tenant(TENANT, doc_id, "New Title", "y" * 100, "baggage", manager)

    assert result["doc_id"] == doc_id
    manager.update_document.assert_called_once()
    (called_doc_id, record, chunks), _ = manager.update_document.call_args
    assert called_doc_id == doc_id
    assert all(c["metadata"]["airline"] == "indigo" for c in chunks)
    assert record["original_content"] == "y" * 100
    assert record["version"] == 1  # no document_store passed, so no previous record to bump from


@patch("src.ingestion.self_serve.embed_chunks")
def test_update_document_bumps_version_from_document_store(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()
    doc_store = MagicMock()
    doc_store.get.return_value = {"version": 3, "created_at": "2026-01-01T00:00:00+00:00"}
    doc_id = "SELFSERVE-INDIGO-old-title-123"

    update_document_for_tenant(
        TENANT, doc_id, "New Title", "y" * 100, "baggage", manager, doc_store,
    )

    doc_store.get.assert_called_once_with(doc_id)
    (_, record, _), _ = manager.update_document.call_args
    assert record["version"] == 4
    assert record["created_at"] == "2026-01-01T00:00:00+00:00"


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_blocks_duplicate_content_by_default(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()
    doc_store = MagicMock()
    doc_store.find_by_content_hash.return_value = {"doc_id": "SELFSERVE-INDIGO-existing-1"}

    with pytest.raises(DuplicateDocumentError):
        ingest_document_for_tenant(TENANT, "Test Policy", "x" * 100, "baggage", manager, doc_store)

    manager.add_document.assert_not_called()


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_force_bypasses_dedup_check(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()
    doc_store = MagicMock()
    doc_store.find_by_content_hash.return_value = {"doc_id": "SELFSERVE-INDIGO-existing-1"}

    ingest_document_for_tenant(
        TENANT, "Test Policy", "x" * 100, "baggage", manager, doc_store, force=True,
    )

    manager.add_document.assert_called_once()


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_no_dedup_check_without_document_store(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()

    ingest_document_for_tenant(TENANT, "Test Policy", "x" * 100, "baggage", manager)

    manager.add_document.assert_called_once()


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_supersedes_requires_ownership(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()

    with pytest.raises(OwnershipError):
        ingest_document_for_tenant(
            TENANT, "Test Policy", "x" * 100, "baggage", manager,
            supersedes="SELFSERVE-SPICEJET-other-doc-1",
        )
    manager.add_document.assert_not_called()


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_supersedes_marks_old_doc(mock_embed):
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()
    old_doc_id = "SELFSERVE-INDIGO-old-doc-1"

    result = ingest_document_for_tenant(
        TENANT, "Test Policy", "x" * 100, "baggage", manager, supersedes=old_doc_id,
    )

    manager.set_status.assert_called_once_with(old_doc_id, "superseded", superseded_by=result["doc_id"])


def test_approve_document_requires_ownership():
    manager = MagicMock()
    with pytest.raises(OwnershipError):
        approve_document_for_tenant(TENANT, "SELFSERVE-SPICEJET-other-doc-123", manager)
    manager.set_status.assert_not_called()


def test_approve_document_sets_status_approved():
    manager = MagicMock()
    doc_id = "SELFSERVE-INDIGO-old-title-123"

    approve_document_for_tenant(TENANT, doc_id, manager)

    manager.set_status.assert_called_once_with(doc_id, "approved")


def test_reject_document_requires_ownership():
    manager = MagicMock()
    with pytest.raises(OwnershipError):
        reject_document_for_tenant(TENANT, "SELFSERVE-SPICEJET-other-doc-123", manager)
    manager.set_status.assert_not_called()


def test_reject_document_sets_status_rejected():
    manager = MagicMock()
    doc_id = "SELFSERVE-INDIGO-old-title-123"

    reject_document_for_tenant(TENANT, doc_id, manager)

    manager.set_status.assert_called_once_with(doc_id, "rejected")


def test_get_version_history_requires_ownership():
    """Regression: version history includes the document's full original
    text — must never be readable across tenants, not just unwritable."""
    doc_store = MagicMock()
    with pytest.raises(OwnershipError):
        get_version_history_for_tenant(TENANT, "SELFSERVE-SPICEJET-other-doc-123", doc_store)
    doc_store.list_versions.assert_not_called()


def test_get_version_history_returns_versions_for_owned_doc():
    doc_store = MagicMock()
    doc_store.list_versions.return_value = [{"version": 1}]
    doc_id = "SELFSERVE-INDIGO-old-title-123"

    result = get_version_history_for_tenant(TENANT, doc_id, doc_store)

    assert result == [{"version": 1}]
    doc_store.list_versions.assert_called_once_with(doc_id)


def test_delete_document_requires_ownership():
    manager = MagicMock()
    with pytest.raises(OwnershipError):
        delete_document_for_tenant(TENANT, "SELFSERVE-SPICEJET-other-doc-123", manager)
    manager.delete_document.assert_not_called()


def test_delete_document_calls_index_manager_for_owned_doc():
    manager = MagicMock()
    doc_id = "SELFSERVE-INDIGO-old-title-123"

    delete_document_for_tenant(TENANT, doc_id, manager)

    manager.delete_document.assert_called_once_with(doc_id)
