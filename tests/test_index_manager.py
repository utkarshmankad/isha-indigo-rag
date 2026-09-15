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


def _record(doc_id, **overrides):
    record = {"doc_id": doc_id, "title": "t", "airline": "indigo", "original_content": "x",
              "version": 1, "created_at": "now", "updated_at": "now"}
    record.update(overrides)
    return record


def test_add_document_upserts_indexes_and_writes_record():
    bm25 = _bm25_with_base()
    store = MagicMock()
    documents = MagicMock()
    manager = IndexManager(bm25, store, documents)
    new_chunks = [
        {"chunk_id": "doc_c_chunk_000", "doc_id": "doc_c", "text": "Air India refund policy.",
         "metadata": {"source_doc_id": "doc_c", "airline": "air_india"}},
    ]
    record = _record("doc_c")

    manager.add_document(record, new_chunks)

    documents.put.assert_called_once_with(record)
    store.upsert.assert_called_once_with(new_chunks)
    assert bm25.corpus_size == 3
    assert bm25.chunks_for_document("doc_c")


def test_add_document_works_without_document_store():
    bm25 = _bm25_with_base()
    store = MagicMock()
    manager = IndexManager(bm25, store)  # document_store omitted
    new_chunks = [
        {"chunk_id": "doc_c_chunk_000", "doc_id": "doc_c", "text": "text",
         "metadata": {"source_doc_id": "doc_c"}},
    ]

    manager.add_document(_record("doc_c"), new_chunks)

    store.upsert.assert_called_once_with(new_chunks)


def test_add_document_rolls_back_dense_and_record_on_bm25_failure():
    bm25 = _bm25_with_base()
    bm25.add_chunks = MagicMock(side_effect=RuntimeError("boom"))
    store = MagicMock()
    documents = MagicMock()
    manager = IndexManager(bm25, store, documents)
    new_chunks = [
        {"chunk_id": "doc_c_chunk_000", "doc_id": "doc_c", "text": "text",
         "metadata": {"source_doc_id": "doc_c"}},
    ]

    with pytest.raises(IndexConsistencyError):
        manager.add_document(_record("doc_c"), new_chunks)

    store.upsert.assert_called_once_with(new_chunks)
    store.delete_by_doc_id.assert_called_once_with("doc_c")
    documents.delete.assert_called_once_with("doc_c")


def test_update_document_replaces_indexes_and_record():
    bm25 = _bm25_with_base()
    store = MagicMock()
    documents = MagicMock()
    documents.get.return_value = _record("doc_a", version=1)
    manager = IndexManager(bm25, store, documents)
    new_chunks = [
        {"chunk_id": "doc_a_chunk_000_v2", "doc_id": "doc_a", "text": "IndiGo checked baggage allowance is 20 kg.",
         "metadata": {"source_doc_id": "doc_a", "airline": "indigo"}},
    ]
    new_record = _record("doc_a", version=2)

    manager.update_document("doc_a", new_record, new_chunks)

    documents.put.assert_called_once_with(new_record)
    store.upsert.assert_called_once_with(new_chunks)
    store.delete_by_chunk_ids.assert_called_once_with(["doc_a_chunk_000"])
    remaining = bm25.chunks_for_document("doc_a")
    assert len(remaining) == 1
    assert remaining[0]["chunk_id"] == "doc_a_chunk_000_v2"


def test_update_document_rolls_back_new_dense_write_and_record_on_bm25_failure():
    bm25 = _bm25_with_base()
    bm25.replace_document = MagicMock(side_effect=RuntimeError("boom"))
    store = MagicMock()
    documents = MagicMock()
    old_record = _record("doc_a", version=1)
    documents.get.return_value = old_record
    manager = IndexManager(bm25, store, documents)
    new_chunks = [
        {"chunk_id": "doc_a_chunk_000_v2", "doc_id": "doc_a", "text": "new text",
         "metadata": {"source_doc_id": "doc_a"}},
    ]

    with pytest.raises(IndexConsistencyError):
        manager.update_document("doc_a", _record("doc_a", version=2), new_chunks)

    store.delete_by_chunk_ids.assert_called_once_with(["doc_a_chunk_000_v2"])
    # First put() call wrote the new record; rollback put() call restores the old one.
    assert documents.put.call_args_list[-1].args[0] == old_record
    assert bm25.chunks_for_document("doc_a")


def test_delete_document_removes_from_both_indexes_and_record():
    bm25 = _bm25_with_base()
    store = MagicMock()
    documents = MagicMock()
    manager = IndexManager(bm25, store, documents)

    manager.delete_document("doc_a")

    store.delete_by_doc_id.assert_called_once_with("doc_a")
    documents.delete.assert_called_once_with("doc_a")
    assert bm25.chunks_for_document("doc_a") == []


def test_delete_document_restores_bm25_and_keeps_record_on_dense_failure():
    bm25 = _bm25_with_base()
    store = MagicMock()
    store.delete_by_doc_id.side_effect = RuntimeError("qdrant down")
    documents = MagicMock()
    manager = IndexManager(bm25, store, documents)

    with pytest.raises(RuntimeError):
        manager.delete_document("doc_a")

    assert bm25.chunks_for_document("doc_a")
    documents.delete.assert_not_called()
