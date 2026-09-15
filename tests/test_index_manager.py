from unittest.mock import MagicMock

import pytest

from src.ingestion.index_manager import IndexConsistencyError, IndexManager
from src.retrieval.hybrid_search import BM25Index

BASE_CHUNKS = [
    {
        "chunk_id": "doc_a_chunk_000",
        "doc_id": "doc_a",
        "text": "IndiGo checked baggage allowance is 15 kg.",
        "metadata": {"source_doc_id": "doc_a", "airline": "indigo", "category": "baggage"},
    },
    {
        "chunk_id": "doc_b_chunk_000",
        "doc_id": "doc_b",
        "text": "SpiceJet loyalty points expire after 2 years.",
        "metadata": {"source_doc_id": "doc_b", "airline": "spicejet", "category": "loyalty"},
    },
]


def _bm25_with_base():
    idx = BM25Index()
    idx.build([dict(c) for c in BASE_CHUNKS])
    return idx


def test_add_document_upserts_and_indexes():
    bm25 = _bm25_with_base()
    store = MagicMock()
    manager = IndexManager(bm25, store)
    new_chunks = [
        {"chunk_id": "doc_c_chunk_000", "doc_id": "doc_c", "text": "Air India refund policy.",
         "metadata": {"source_doc_id": "doc_c", "airline": "air_india"}},
    ]

    manager.add_document(new_chunks)

    store.upsert.assert_called_once_with(new_chunks)
    assert bm25.corpus_size == 3
    assert bm25.chunks_for_document("doc_c")


def test_add_document_rolls_back_dense_on_bm25_failure():
    bm25 = _bm25_with_base()
    bm25.add_chunks = MagicMock(side_effect=RuntimeError("boom"))
    store = MagicMock()
    manager = IndexManager(bm25, store)
    new_chunks = [
        {"chunk_id": "doc_c_chunk_000", "doc_id": "doc_c", "text": "text",
         "metadata": {"source_doc_id": "doc_c"}},
    ]

    with pytest.raises(IndexConsistencyError):
        manager.add_document(new_chunks)

    store.upsert.assert_called_once_with(new_chunks)
    store.delete_by_doc_id.assert_called_once_with("doc_c")


def test_update_document_replaces_both_indexes():
    bm25 = _bm25_with_base()
    store = MagicMock()
    manager = IndexManager(bm25, store)
    new_chunks = [
        {"chunk_id": "doc_a_chunk_000_v2", "doc_id": "doc_a", "text": "IndiGo checked baggage allowance is 20 kg.",
         "metadata": {"source_doc_id": "doc_a", "airline": "indigo"}},
    ]

    manager.update_document("doc_a", new_chunks)

    store.upsert.assert_called_once_with(new_chunks)
    store.delete_by_chunk_ids.assert_called_once_with(["doc_a_chunk_000"])
    remaining = bm25.chunks_for_document("doc_a")
    assert len(remaining) == 1
    assert remaining[0]["chunk_id"] == "doc_a_chunk_000_v2"


def test_update_document_rolls_back_new_dense_write_on_bm25_failure():
    bm25 = _bm25_with_base()
    bm25.replace_document = MagicMock(side_effect=RuntimeError("boom"))
    store = MagicMock()
    manager = IndexManager(bm25, store)
    new_chunks = [
        {"chunk_id": "doc_a_chunk_000_v2", "doc_id": "doc_a", "text": "new text",
         "metadata": {"source_doc_id": "doc_a"}},
    ]

    with pytest.raises(IndexConsistencyError):
        manager.update_document("doc_a", new_chunks)

    store.delete_by_chunk_ids.assert_called_once_with(["doc_a_chunk_000_v2"])
    # Original bm25 entry for doc_a is untouched since replace_document raised
    # before mutating internal state (mocked out entirely).
    assert bm25.chunks_for_document("doc_a")


def test_delete_document_removes_from_both_indexes():
    bm25 = _bm25_with_base()
    store = MagicMock()
    manager = IndexManager(bm25, store)

    manager.delete_document("doc_a")

    store.delete_by_doc_id.assert_called_once_with("doc_a")
    assert bm25.chunks_for_document("doc_a") == []


def test_delete_document_restores_bm25_on_dense_failure():
    bm25 = _bm25_with_base()
    store = MagicMock()
    store.delete_by_doc_id.side_effect = RuntimeError("qdrant down")
    manager = IndexManager(bm25, store)

    with pytest.raises(RuntimeError):
        manager.delete_document("doc_a")

    assert bm25.chunks_for_document("doc_a")
