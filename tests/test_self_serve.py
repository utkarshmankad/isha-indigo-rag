from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.self_serve import (
    UploadValidationError,
    ingest_document_for_tenant,
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
    store = MagicMock()

    result = ingest_document_for_tenant(
        TENANT, "Test Policy", "x" * 100, "baggage", store,
    )

    assert result["chunk_count"] >= 1
    store.upsert.assert_called_once()
    (upserted_chunks,), _ = store.upsert.call_args
    assert all(c["metadata"]["airline"] == "indigo" for c in upserted_chunks)


@patch("src.ingestion.self_serve.embed_chunks")
def test_ingest_document_cannot_be_tagged_to_another_airline(mock_embed):
    """The tenant object, not any caller-supplied string, decides the airline tag."""
    mock_embed.side_effect = lambda chunks: [{**c, "embedding": [0.0] * 8} for c in chunks]
    store = MagicMock()
    spicejet_tenant = TenantConfig("spicejet", "spicejet", "SpiceJet (SG)", "sj-key")

    ingest_document_for_tenant(spicejet_tenant, "Test Policy", "x" * 100, "baggage", store)

    (upserted_chunks,), _ = store.upsert.call_args
    assert all(c["metadata"]["airline"] == "spicejet" for c in upserted_chunks)
