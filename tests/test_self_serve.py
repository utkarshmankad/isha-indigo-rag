from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.self_serve import (
    OwnershipError,
    UploadValidationError,
    delete_document_for_tenant,
    ingest_document_for_tenant,
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
    (added_chunks,), _ = manager.add_document.call_args
    assert all(c["metadata"]["airline"] == "indigo" for c in added_chunks)


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_cannot_be_tagged_to_another_airline(mock_embed):
    """The tenant object, not any caller-supplied string, decides the airline tag."""
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    manager = MagicMock()
    spicejet_tenant = TenantConfig("spicejet", "spicejet", "SpiceJet (SG)", "sj-key")

    ingest_document_for_tenant(spicejet_tenant, "Test Policy", "x" * 100, "baggage", manager)

    (added_chunks,), _ = manager.add_document.call_args
    assert all(c["metadata"]["airline"] == "spicejet" for c in added_chunks)


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
    (called_doc_id, chunks), _ = manager.update_document.call_args
    assert called_doc_id == doc_id
    assert all(c["metadata"]["airline"] == "indigo" for c in chunks)


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
