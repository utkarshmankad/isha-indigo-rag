import pytest
from src.retrieval.hybrid_search import BM25Index, reciprocal_rank_fusion

SAMPLE_CHUNKS = [
    {
        "chunk_id": f"doc_{i}",
        "text": text,
        "metadata": {"category": cat, "airline": airline},
    }
    for i, (text, cat, airline) in enumerate([
        ("IndiGo economy allows 15 kg checked baggage.", "baggage", "indigo"),
        ("Air India allows 23 kg checked baggage.", "baggage", "air_india"),
        ("BluChip loyalty points expire after 3 years.", "loyalty", "indigo"),
        ("DGCA requires compensation for flight delays.", "flight_delays_and_cancellations", "dgca"),
        ("SpiceJet SpiceFlex allows free cancellation.", "cancellations_and_refunds", "spicejet"),
    ])
]


def test_build_and_search_returns_results():
    idx = BM25Index()
    idx.build(SAMPLE_CHUNKS)
    results = idx.search("baggage allowance", top_k=2)
    assert len(results) == 2
    assert all("chunk_id" in r and "score" in r for r in results)


def test_search_without_build_raises():
    idx = BM25Index()
    with pytest.raises(RuntimeError):
        idx.search("test")


def test_search_relevant_chunk_ranks_high():
    idx = BM25Index()
    idx.build(SAMPLE_CHUNKS)
    results = idx.search("BluChip loyalty points", top_k=5)
    assert results[0]["chunk_id"] == "doc_2"


def test_corpus_size_property():
    idx = BM25Index()
    idx.build(SAMPLE_CHUNKS)
    assert idx.corpus_size == len(SAMPLE_CHUNKS)


def test_save_and_load(tmp_path):
    idx = BM25Index()
    idx.build(SAMPLE_CHUNKS)
    idx.save(str(tmp_path))

    idx2 = BM25Index()
    assert idx2.load(str(tmp_path))
    assert idx2.corpus_size == len(SAMPLE_CHUNKS)

    results = idx2.search("baggage", top_k=2)
    assert len(results) == 2


def test_load_missing_dir_returns_false(tmp_path):
    idx = BM25Index()
    assert not idx.load(str(tmp_path / "nonexistent"))


def test_build_or_load_creates_and_reuses_cache(tmp_path):
    idx1 = BM25Index.build_or_load(SAMPLE_CHUNKS, cache_root=str(tmp_path))
    assert idx1.corpus_size == len(SAMPLE_CHUNKS)

    idx2 = BM25Index.build_or_load(SAMPLE_CHUNKS, cache_root=str(tmp_path))
    assert idx2.corpus_size == len(SAMPLE_CHUNKS)
    results = idx2.search("flight delay", top_k=2)
    assert len(results) == 2


def test_build_or_load_different_corpus_gets_new_cache(tmp_path):
    extra = SAMPLE_CHUNKS + [
        {"chunk_id": "doc_5", "text": "Extra chunk.", "metadata": {"category": "baggage", "airline": "indigo"}}
    ]
    idx1 = BM25Index.build_or_load(SAMPLE_CHUNKS, cache_root=str(tmp_path))
    idx2 = BM25Index.build_or_load(extra, cache_root=str(tmp_path))
    assert idx2.corpus_size == len(extra)


def test_rrf_merges_and_deduplicates():
    bm25 = [
        {"chunk_id": "a", "score": 0.9, "text": "t", "metadata": {}},
        {"chunk_id": "b", "score": 0.5, "text": "t", "metadata": {}},
    ]
    vec = [
        {"chunk_id": "b", "score": 0.95, "text": "t", "metadata": {}},
        {"chunk_id": "c", "score": 0.8, "text": "t", "metadata": {}},
    ]
    fused = reciprocal_rank_fusion(bm25, vec, top_k=3)
    ids = [r["chunk_id"] for r in fused]
    assert len(ids) == len(set(ids))
    assert all("fusion_score" in r for r in fused)


def test_rrf_shared_chunk_ranks_higher():
    bm25 = [
        {"chunk_id": "shared", "score": 0.9, "text": "t", "metadata": {}},
        {"chunk_id": "only_bm25", "score": 0.8, "text": "t", "metadata": {}},
    ]
    vec = [
        {"chunk_id": "shared", "score": 0.9, "text": "t", "metadata": {}},
        {"chunk_id": "only_vec", "score": 0.8, "text": "t", "metadata": {}},
    ]
    fused = reciprocal_rank_fusion(bm25, vec, top_k=3)
    assert fused[0]["chunk_id"] == "shared"
