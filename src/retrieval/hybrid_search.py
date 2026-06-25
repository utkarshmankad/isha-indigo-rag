import hashlib
import json
import os
import pickle
import re

import bm25s

RRF_K = 60
_BM25_CACHE_ROOT = ".bm25_cache"


def _tokenize(text: str) -> list[str]:
    return re.split(r"[\s\W]+", text.lower())


class BM25Index:
    def __init__(self) -> None:
        self._index: bm25s.BM25 | None = None
        self._chunks: list[dict] = []

    @property
    def corpus_size(self) -> int:
        return len(self._chunks)

    def build(self, chunks: list[dict]) -> None:
        self._chunks = chunks
        corpus_tokens = [_tokenize(c["text"]) for c in chunks]
        self._index = bm25s.BM25()
        self._index.index(corpus_tokens)
        print(f"[BM25] Indexed {len(chunks)} chunks.")

    def save(self, cache_dir: str) -> None:
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, "bm25.pkl"), "wb") as f:
            pickle.dump(self._index, f)
        with open(os.path.join(cache_dir, "chunks.pkl"), "wb") as f:
            pickle.dump(self._chunks, f)
        print(f"[BM25] Saved index to {cache_dir}.")

    def load(self, cache_dir: str) -> bool:
        bm25_path = os.path.join(cache_dir, "bm25.pkl")
        chunks_path = os.path.join(cache_dir, "chunks.pkl")
        if not (os.path.exists(bm25_path) and os.path.exists(chunks_path)):
            return False
        try:
            with open(bm25_path, "rb") as f:
                self._index = pickle.load(f)
            with open(chunks_path, "rb") as f:
                self._chunks = pickle.load(f)
            print(f"[BM25] Loaded index from cache ({len(self._chunks)} chunks).")
            return True
        except Exception:
            return False

    @classmethod
    def build_or_load(cls, chunks: list[dict], cache_root: str = _BM25_CACHE_ROOT) -> "BM25Index":
        key = hashlib.sha256(
            json.dumps([c["chunk_id"] for c in chunks]).encode()
        ).hexdigest()[:16]
        cache_dir = os.path.join(cache_root, key)
        idx = cls()
        if idx.load(cache_dir):
            return idx
        idx.build(chunks)
        idx.save(cache_dir)
        return idx

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if self._index is None:
            raise RuntimeError("BM25Index not built — call build() first.")
        query_tokens = _tokenize(query)
        results, scores = self._index.retrieve(
            [query_tokens], corpus=self._chunks, k=min(top_k, len(self._chunks))
        )
        raw_scores = scores[0].tolist()
        hits = results[0].tolist()

        max_score = max(raw_scores) if raw_scores else 1.0
        min_score = min(raw_scores) if raw_scores else 0.0
        span = max_score - min_score or 1.0

        return [
            {
                "chunk_id": hit["chunk_id"],
                "score": (score - min_score) / span,
                "text": hit["text"],
                "metadata": hit["metadata"],
            }
            for hit, score in zip(hits, raw_scores)
        ]


def reciprocal_rank_fusion(
    bm25_results: list[dict],
    vector_results: list[dict],
    top_k: int,
    k: int = RRF_K,
) -> list[dict]:
    rrf: dict[str, float] = {}
    data: dict[str, dict] = {}

    for rank, r in enumerate(bm25_results):
        cid = r["chunk_id"]
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (k + rank + 1)
        data[cid] = r

    for rank, r in enumerate(vector_results):
        cid = r["chunk_id"]
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (k + rank + 1)
        data[cid] = r

    ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        {**data[cid], "fusion_score": score}
        for cid, score in ranked
    ]


def hybrid_search(
    query: str,
    query_vector: list[float],
    bm25_index: BM25Index,
    vector_store,
    top_k: int = 5,
    filters: dict | None = None,
    airline_filter: list[str] | None = None,
) -> list[dict]:
    fetch_k = top_k * 2
    # When post-filtering by category/airline, fetch the full corpus so that
    # low-volume categories aren't starved before RRF.
    bm25_fetch_k = bm25_index.corpus_size if (filters or airline_filter) else fetch_k

    bm25_results = bm25_index.search(query, top_k=bm25_fetch_k)
    if filters:
        bm25_results = [
            r for r in bm25_results
            if all(r["metadata"].get(k) == v for k, v in filters.items())
        ]
    if airline_filter:
        bm25_results = [
            r for r in bm25_results
            if r["metadata"].get("airline") in airline_filter
        ]

    vector_results = vector_store.query(
        query_vector, top_k=fetch_k, filters=filters, airline_filter=airline_filter
    )

    fused = reciprocal_rank_fusion(bm25_results, vector_results, top_k=top_k)

    print(
        f"[Hybrid] BM25: {len(bm25_results)} | "
        f"Vector: {len(vector_results)} | "
        f"Fused: {len(fused)}"
    )
    return fused


if __name__ == "__main__":
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

    from dotenv import load_dotenv

    load_dotenv()

    from data.indigo_documents import DOCUMENTS
    from src.embedding.embedder import embed_batch
    from src.embedding.vector_store import QdrantVectorStore
    from src.ingestion.chunker import ingest_all

    chunks = ingest_all(DOCUMENTS)

    bm25 = BM25Index()
    bm25.build(chunks)

    store = QdrantVectorStore()

    test_queries = [
        "6E Prime baggage allowance",
        "what happens if my flight is cancelled",
        "BluChip points expiry",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"QUERY: {query}")
        print("=" * 60)

        bm25_results = bm25.search(query, top_k=2)
        print("BM25-only top 2:")
        for r in bm25_results:
            print(f"  {r['score']:.3f}  [{r['chunk_id']}]  {r['metadata']['title']}")

        qvec = embed_batch([query])[0]
        vector_results = store.query(qvec, top_k=2)
        print("Vector-only top 2:")
        for r in vector_results:
            print(f"  {r['score']:.3f}  [{r['chunk_id']}]  {r['metadata']['title']}")

        hybrid_results = hybrid_search(query, qvec, bm25, store, top_k=2)
        print("Hybrid top 2:")
        for r in hybrid_results:
            print(f"  {r['fusion_score']:.4f}  [{r['chunk_id']}]  {r['metadata']['title']}")
