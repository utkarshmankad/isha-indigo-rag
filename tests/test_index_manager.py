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


def test_set_status_updates_bm25_dense_and_record():
    bm25 = _bm25_with_base()
    store = MagicMock()
    documents = MagicMock()
    manager = IndexManager(bm25, store, documents)

    manager.set_status("doc_a", "approved")

    assert bm25.chunks_for_document("doc_a")[0]["metadata"]["status"] == "approved"
    store.set_status_by_doc_id.assert_called_once_with("doc_a", "approved", superseded_by=None)
    documents.patch.assert_called_once_with("doc_a", status="approved", superseded_by=None)


def test_set_status_with_superseded_by_propagates_to_all_three():
    bm25 = _bm25_with_base()
    store = MagicMock()
    documents = MagicMock()
    manager = IndexManager(bm25, store, documents)

    manager.set_status("doc_a", "superseded", superseded_by="doc_new")

    chunk = bm25.chunks_for_document("doc_a")[0]
    assert chunk["metadata"]["status"] == "superseded"
    assert chunk["metadata"]["superseded_by"] == "doc_new"
    store.set_status_by_doc_id.assert_called_once_with("doc_a", "superseded", superseded_by="doc_new")
    documents.patch.assert_called_once_with("doc_a", status="superseded", superseded_by="doc_new")


def test_set_status_works_without_document_store():
    bm25 = _bm25_with_base()
    store = MagicMock()
    manager = IndexManager(bm25, store)

    manager.set_status("doc_a", "rejected")

    store.set_status_by_doc_id.assert_called_once_with("doc_a", "rejected", superseded_by=None)


def test_update_preserves_reused_chunk_ids_and_removes_durable_stale_chunks():
    bm25 = _bm25_with_base()
    store = MagicMock()
    # Include a persisted chunk absent from this process's BM25 (after restart).
    store.chunks_for_document.return_value = [BASE_CHUNKS[0], {**BASE_CHUNKS[0], 'chunk_id': 'old_extra'}]
    manager = IndexManager(bm25, store)
    replacement = {**BASE_CHUNKS[0], 'text': 'Replacement pending policy'}
    manager.update_document('doc_a', _record('doc_a'), [replacement])
    store.delete_by_chunk_ids.assert_called_once_with(['old_extra'])
    assert bm25.chunks_for_document('doc_a')[0]['text'] == 'Replacement pending policy'


def test_update_restores_overwritten_dense_chunks_when_lexical_write_fails():
    bm25 = _bm25_with_base()
    bm25.replace_document = MagicMock(side_effect=RuntimeError('index failure'))
    store = MagicMock()
    snapshot = [{**BASE_CHUNKS[0], 'embedding': [1.0, 0.0]}]
    store.chunks_for_document.return_value = snapshot
    manager = IndexManager(bm25, store)
    with pytest.raises(IndexConsistencyError):
        manager.update_document('doc_a', _record('doc_a'), [{**snapshot[0], 'text': 'new content'}])
    store.delete_by_chunk_ids.assert_called_once_with([])
    assert store.upsert.call_args.args[0] == snapshot


def test_invalid_status_rejected_before_any_write():
    bm25 = _bm25_with_base()
    store = MagicMock()
    manager = IndexManager(bm25, store)
    with pytest.raises(ValueError):
        manager.set_status('doc_a', 'aproved')
    store.set_status_by_doc_id.assert_not_called()


def test_real_dense_update_and_failure_restore(monkeypatch):
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance
    from src.embedding.vector_store import QdrantVectorStore
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store.client = QdrantClient(':memory:')
    store.collection_name = 'updates'
    store.client.create_collection('updates', vectors_config=VectorParams(size=2, distance=Distance.COSINE))
    old = {**BASE_CHUNKS[0], 'embedding': [1., 0.]}
    store.upsert([old])
    bm25 = _bm25_with_base()
    manager = IndexManager(bm25, store)
    new = {**old, 'text': 'Replacement baggage rule', 'embedding': [0., 1.]}
    manager.update_document('doc_a', _record('doc_a'), [new])
    assert store.chunks_for_document('doc_a')[0]['text'] == new['text']
    monkeypatch.setattr(bm25, 'replace_document', MagicMock(side_effect=RuntimeError('build failed')))
    with pytest.raises(IndexConsistencyError):
        manager.update_document('doc_a', _record('doc_a'), [old])
    restored = store.chunks_for_document('doc_a')[0]
    assert restored['text'] == new['text']
    assert restored['embedding'] == new['embedding']
    store.client.close()


def test_obsolete_cleanup_failure_aborts_update_instead_of_leaving_stale_policy():
    bm25 = _bm25_with_base()
    store = MagicMock()
    snapshot = [{**BASE_CHUNKS[0], 'embedding': [1., 0.]}]
    store.chunks_for_document.return_value = snapshot
    store.delete_by_chunk_ids.side_effect = [RuntimeError('cleanup failed'), None]
    manager = IndexManager(bm25, store)
    replacement = {**snapshot[0], 'chunk_id': 'replacement', 'text': 'Changed baggage policy'}
    with pytest.raises(IndexConsistencyError):
        manager.update_document('doc_a', _record('doc_a'), [replacement])
    assert store.upsert.call_args.args[0] == snapshot
    assert bm25.chunks_for_document('doc_a')[0]['text'] == BASE_CHUNKS[0]['text']
