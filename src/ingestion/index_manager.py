"""Keeps the canonical record, dense (Qdrant) and lexical (BM25) indexes
consistent for document add/update/delete outside the bundled static ingest
path (S9-T1, extended for Weeks 3-4 item 1 with the canonical document
store).

Scope: within a single running process, a document add/update/delete either
lands in all three of {canonical record, dense index, lexical index}, or
none of them — never a subset. There is no cross-process persistence for
the dense/lexical indexes: a process restart still rebuilds BM25 only from
the static bundled corpus (see docs/LOCAL-RECONCILIATION.md), and the dense
index only from whatever is already in Qdrant. The canonical record store
(src/documents/document_store.py) IS itself durable/cross-process — it is
the source of truth for a document's original content and provenance — but
nothing yet re-derives dense/BM25 entries from it at startup. That
replay-on-startup step is separate, larger, not-yet-authorized scope.
"""
from threading import Lock

from src.documents.document_store import DocumentStore, VALID_STATUSES
from src.embedding.vector_store import QdrantVectorStore
from src.observability.logging_config import get_logger
from src.retrieval.hybrid_search import BM25Index

logger = get_logger("ingestion.index_manager")


class IndexConsistencyError(RuntimeError):
    pass


class IndexManager:
    def __init__(
        self,
        bm25_index: BM25Index,
        vector_store: QdrantVectorStore,
        document_store: DocumentStore | None = None,
    ) -> None:
        self._bm25 = bm25_index
        self._store = vector_store
        self._documents = document_store
        self._lock = Lock()

    def add_document(self, record: dict, chunks: list[dict]) -> None:
        """Add a new document: canonical record first (durable, cheap,
        idempotent), then dense chunks, then BM25. Any failure after the
        canonical record write rolls that record back out too, so a failed
        add never leaves an orphan canonical record with no searchable
        content."""
        if not chunks:
            return
        doc_id = chunks[0]["doc_id"]
        with self._lock:
            if self._documents:
                self._documents.put(record)
            self._store.upsert(chunks)
            try:
                self._bm25.add_chunks(chunks)
            except Exception:
                logger.error("bm25 add failed, rolling back dense write and record", doc_id=doc_id)
                self._store.delete_by_doc_id(doc_id)
                if self._documents:
                    self._documents.delete(doc_id)
                raise IndexConsistencyError(
                    f"Failed to index '{doc_id}' for keyword search; upload rolled back."
                ) from None

    def update_document(self, doc_id: str, record: dict, chunks: list[dict]) -> None:
        """Replace a document with compensation on failed publication.

        Dense snapshots preserve overwritten vectors and find stale chunks
        after restart. Cleanup must succeed before publishing the new BM25
        corpus. Crashes or failed compensation still require reconciliation.
        """
        if not chunks:
            return
        with self._lock:
            previous_record = self._documents.get(doc_id) if self._documents else None
            old_chunks = self._bm25.chunks_for_document(doc_id)
            dense_snapshot = list(self._store.chunks_for_document(doc_id))
            old_chunk_ids = list(dict.fromkeys(c["chunk_id"] for c in [*old_chunks, *dense_snapshot]))

            if self._documents:
                self._documents.put(record)
            retained_ids = {c["chunk_id"] for c in chunks}
            obsolete_ids = [cid for cid in old_chunk_ids if cid not in retained_ids]
            try:
                self._store.upsert(chunks)
                if obsolete_ids:
                    self._store.delete_by_chunk_ids(obsolete_ids)
                self._bm25.replace_document(doc_id, chunks)
            except Exception:
                logger.error("document publication failed, restoring prior dense version and record", doc_id=doc_id)
                new_only = [c["chunk_id"] for c in chunks if c["chunk_id"] not in
                            {old["chunk_id"] for old in dense_snapshot}]
                self._store.delete_by_chunk_ids(new_only)
                if dense_snapshot:
                    self._store.upsert(dense_snapshot)
                if self._documents and previous_record:
                    self._documents.put(previous_record)
                raise IndexConsistencyError(
                    f"Failed to update '{doc_id}' for keyword search; update rolled back."
                ) from None

    def delete_document(self, doc_id: str) -> None:
        """Remove `doc_id` from the lexical index, the dense index, and the
        canonical record, in that order — BM25 first because it is cheap and
        fully in-memory to restore, the canonical record last because it is
        the cheapest to leave in place if an earlier step fails."""
        with self._lock:
            removed = self._bm25.remove_document(doc_id)
            try:
                self._store.delete_by_doc_id(doc_id)
            except Exception:
                logger.error("dense delete failed, restoring bm25 entries", doc_id=doc_id)
                if removed:
                    self._bm25.add_chunks(removed)
                raise
            if self._documents:
                self._documents.delete(doc_id)

    def set_status(self, doc_id: str, status: str, *, superseded_by: str | None = None) -> None:
        """Approve/reject/supersede: a metadata-only transition, not a
        content change. Updates the canonical record, the dense chunks and
        the in-memory BM25 chunks for `doc_id` so retrieval's status filter
        (see docs/INDEX-CONSISTENCY.md) sees the change immediately. These
        three patches are independent and idempotent — safe to retry on
        partial failure, unlike add/update/delete there is no compensating
        rollback here."""
        if status not in VALID_STATUSES:
            raise ValueError("Invalid document approval status")
        with self._lock:
            for chunk in self._bm25.chunks_for_document(doc_id):
                chunk["metadata"]["status"] = status
                if superseded_by is not None:
                    chunk["metadata"]["superseded_by"] = superseded_by
            self._store.set_status_by_doc_id(doc_id, status, superseded_by=superseded_by)
            if self._documents:
                self._documents.patch(doc_id, status=status, superseded_by=superseded_by)
