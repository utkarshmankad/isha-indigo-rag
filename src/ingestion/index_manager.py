"""Keeps the dense (Qdrant) and lexical (BM25) indexes consistent for
document add/update/delete outside the bundled static ingest path (S9-T1).

Scope: within a single running process, a document add/update/delete either
lands in both indexes or in neither — never in only one. There is no
cross-process persistence here: a process restart still rebuilds BM25 only
from the static bundled corpus (see docs/LOCAL-RECONCILIATION.md), so
self-serve uploads made through this manager do not survive a restart until
a canonical document store re-feeds them at startup. That is separate,
larger, unauthorized-so-far scope.
"""
from threading import Lock

from src.embedding.vector_store import QdrantVectorStore
from src.observability.logging_config import get_logger
from src.retrieval.hybrid_search import BM25Index

logger = get_logger("ingestion.index_manager")


class IndexConsistencyError(RuntimeError):
    pass


class IndexManager:
    def __init__(self, bm25_index: BM25Index, vector_store: QdrantVectorStore) -> None:
        self._bm25 = bm25_index
        self._store = vector_store
        self._lock = Lock()

    def add_document(self, chunks: list[dict]) -> None:
        """Add a new document's embedded chunks to both indexes. If the BM25
        side fails after the dense write succeeds, the dense write is rolled
        back so the document is never vector-searchable without also being
        keyword-searchable."""
        if not chunks:
            return
        doc_id = chunks[0]["doc_id"]
        with self._lock:
            self._store.upsert(chunks)
            try:
                self._bm25.add_chunks(chunks)
            except Exception:
                logger.error("bm25 add failed, rolling back dense write", doc_id=doc_id)
                self._store.delete_by_doc_id(doc_id)
                raise IndexConsistencyError(
                    f"Failed to index '{doc_id}' for keyword search; upload rolled back."
                ) from None

    def update_document(self, doc_id: str, chunks: list[dict]) -> None:
        """Replace `doc_id`'s chunks in both indexes. Writes the new dense
        points before touching BM25 or removing the old dense points, so a
        failure at any step leaves either the old document fully intact
        (rollback) or the new document fully committed — never a mix."""
        if not chunks:
            return
        with self._lock:
            old_chunks = self._bm25.chunks_for_document(doc_id)
            old_chunk_ids = [c["chunk_id"] for c in old_chunks]

            self._store.upsert(chunks)
            try:
                self._bm25.replace_document(doc_id, chunks)
            except Exception:
                logger.error(
                    "bm25 replace failed, rolling back new dense write", doc_id=doc_id,
                )
                self._store.delete_by_chunk_ids([c["chunk_id"] for c in chunks])
                raise IndexConsistencyError(
                    f"Failed to update '{doc_id}' for keyword search; update rolled back."
                ) from None

            if old_chunk_ids:
                try:
                    self._store.delete_by_chunk_ids(old_chunk_ids)
                except Exception:
                    # BM25 and the new dense points are already committed and
                    # consistent with each other — the update itself
                    # succeeded. Stale superseded dense points may briefly
                    # duplicate in vector-only results until this is retried.
                    logger.error(
                        "post-update cleanup of superseded dense points failed",
                        doc_id=doc_id,
                    )

    def delete_document(self, doc_id: str) -> None:
        """Remove `doc_id` from both indexes. BM25 removal happens first
        because it is cheap and fully in-memory: if the dense delete then
        fails, the BM25 entries are restored so nothing is silently
        keyword-unsearchable while still present in Qdrant."""
        with self._lock:
            removed = self._bm25.remove_document(doc_id)
            try:
                self._store.delete_by_doc_id(doc_id)
            except Exception:
                logger.error(
                    "dense delete failed, restoring bm25 entries", doc_id=doc_id,
                )
                if removed:
                    self._bm25.add_chunks(removed)
                raise
