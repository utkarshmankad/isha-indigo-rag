import pytest
from src.ingestion.chunker import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    chunk_document,
    clean_text,
    ingest_all,
    split_into_chunks,
)

DOC_FIXTURE = {
    "id": "test_doc",
    "title": "Test Policy",
    "content": "This is test content about airline policies. " * 30,
    "category": "baggage",
    "department": "ops",
    "doc_type": "policy",
    "last_updated": "2025-01-01",
    "airline": "indigo",
}


def test_clean_text_collapses_blank_lines():
    result = clean_text("a\n\n\n\nb")
    assert "\n\n\n" not in result


def test_clean_text_collapses_inline_whitespace():
    result = clean_text("hello   world")
    assert "  " not in result


def test_split_short_text_single_chunk():
    # Text must be >= MIN_CHUNK_SIZE (100) to survive the filter.
    text = "Short text about airline policy. " * 4
    chunks = split_into_chunks(text, chunk_size=400, overlap=80)
    assert len(chunks) == 1


def test_split_long_text_multiple_chunks():
    text = "Word " * 200
    chunks = split_into_chunks(text, chunk_size=400, overlap=80)
    assert len(chunks) > 1


def test_split_chunks_bounded_by_size_plus_overlap():
    text = "Word " * 300
    chunks = split_into_chunks(text, chunk_size=400, overlap=80)
    for c in chunks:
        assert len(c) <= CHUNK_SIZE + CHUNK_OVERLAP


def test_min_chunk_size_enforced():
    doc = {**DOC_FIXTURE, "content": "A" * 50 + "\n\n" + "B" * 200}
    chunks = chunk_document(doc)
    for c in chunks:
        assert len(c["text"]) >= MIN_CHUNK_SIZE


def test_chunk_document_metadata():
    chunks = chunk_document(DOC_FIXTURE)
    assert len(chunks) >= 1
    for c in chunks:
        assert c["doc_id"] == "test_doc"
        assert c["metadata"]["category"] == "baggage"
        assert c["metadata"]["airline"] == "indigo"
        assert "chunk_id" in c
        assert "text" in c


def test_chunk_document_unique_ids():
    chunks = chunk_document(DOC_FIXTURE)
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunk_document_total_chunks_field():
    chunks = chunk_document(DOC_FIXTURE)
    for c in chunks:
        assert c["total_chunks"] == len(chunks)


def test_ingest_all_multiple_docs():
    docs = [
        {**DOC_FIXTURE, "id": f"doc_{i}", "title": f"Doc {i}"}
        for i in range(3)
    ]
    chunks = ingest_all(docs)
    assert len(chunks) >= 3
    assert {c["doc_id"] for c in chunks} == {"doc_0", "doc_1", "doc_2"}


def test_ingest_all_no_duplicate_chunk_ids():
    docs = [
        {**DOC_FIXTURE, "id": f"doc_{i}"}
        for i in range(5)
    ]
    chunks = ingest_all(docs)
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
