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


def test_add_chunks_extends_corpus_and_is_searchable():
    from copy import deepcopy
    idx = BM25Index()
    idx.build(deepcopy(SAMPLE_CHUNKS))
    idx.add_chunks([
        {"chunk_id": "doc_new", "doc_id": "doc_new", "text": "Vistara checked baggage is 20 kg.",
         "metadata": {"category": "baggage", "airline": "vistara", "source_doc_id": "doc_new"}},
    ])
    assert idx.corpus_size == len(SAMPLE_CHUNKS) + 1
    hit = next(r for r in idx.search("Vistara baggage", top_k=5) if r["chunk_id"] == "doc_new")
    assert hit["metadata"]["airline"] == "vistara"


def test_chunks_for_document_matches_source_doc_id():
    from copy import deepcopy
    idx = BM25Index()
    chunks = deepcopy(SAMPLE_CHUNKS)
    chunks[0]["metadata"]["source_doc_id"] = "doc_x"
    idx.build(chunks)
    assert [c["chunk_id"] for c in idx.chunks_for_document("doc_x")] == [chunks[0]["chunk_id"]]


def test_remove_document_shrinks_corpus_and_returns_removed():
    from copy import deepcopy
    idx = BM25Index()
    chunks = deepcopy(SAMPLE_CHUNKS)
    chunks[0]["metadata"]["source_doc_id"] = "doc_x"
    idx.build(chunks)

    removed = idx.remove_document("doc_x")

    assert len(removed) == 1
    assert idx.corpus_size == len(SAMPLE_CHUNKS) - 1
    assert idx.chunks_for_document("doc_x") == []


def test_remove_document_missing_id_is_noop():
    from copy import deepcopy
    idx = BM25Index()
    idx.build(deepcopy(SAMPLE_CHUNKS))
    assert idx.remove_document("does-not-exist") == []
    assert idx.corpus_size == len(SAMPLE_CHUNKS)


def test_remove_last_document_leaves_index_empty_but_safe():
    idx = BM25Index()
    idx.build([{"chunk_id": "only", "doc_id": "only_doc", "text": "solo chunk",
                "metadata": {"source_doc_id": "only_doc"}}])
    idx.remove_document("only_doc")
    assert idx.corpus_size == 0
    with pytest.raises(RuntimeError):
        idx.search("anything")


def test_replace_document_swaps_content_in_one_rebuild():
    from copy import deepcopy
    idx = BM25Index()
    chunks = deepcopy(SAMPLE_CHUNKS)
    chunks[0]["doc_id"] = "doc_x"
    chunks[0]["metadata"]["source_doc_id"] = "doc_x"
    idx.build(chunks)

    idx.replace_document("doc_x", [
        {"chunk_id": "doc_x_v2", "doc_id": "doc_x", "text": "IndiGo revised baggage allowance is 20 kg.",
         "metadata": {"source_doc_id": "doc_x", "airline": "indigo"}},
    ])

    remaining = idx.chunks_for_document("doc_x")
    assert len(remaining) == 1
    assert remaining[0]["chunk_id"] == "doc_x_v2"
    assert idx.corpus_size == len(SAMPLE_CHUNKS)


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


def test_same_id_policy_edit_rebuilds_cached_text(tmp_path):
    from copy import deepcopy
    original = deepcopy(SAMPLE_CHUNKS)
    BM25Index.build_or_load(original, cache_root=str(tmp_path))
    revised = deepcopy(original)
    revised[0]['text'] = 'IndiGo revised checked baggage allowance is twenty kilograms.'
    updated = BM25Index.build_or_load(revised, cache_root=str(tmp_path))
    assert updated.search('revised twenty kilograms', top_k=1)[0]['text'] == revised[0]['text']
    assert len(list(tmp_path.iterdir())) == 2


def test_visibility_and_airline_edits_invalidate_metadata(tmp_path):
    from copy import deepcopy
    original = deepcopy(SAMPLE_CHUNKS)
    original[0]['metadata']['visibility'] = 'public'
    BM25Index.build_or_load(original, cache_root=str(tmp_path))
    revised = deepcopy(original)
    revised[0]['metadata'].update(visibility='private', airline='spicejet')
    updated = BM25Index.build_or_load(revised, cache_root=str(tmp_path))
    hit = next(r for r in updated.search('baggage', top_k=5) if r['chunk_id'] == revised[0]['chunk_id'])
    assert hit['metadata']['visibility'] == 'private'
    assert hit['metadata']['airline'] == 'spicejet'


def test_metadata_dict_order_does_not_create_duplicate_cache(tmp_path):
    from copy import deepcopy
    original = deepcopy(SAMPLE_CHUNKS)
    BM25Index.build_or_load(original, cache_root=str(tmp_path))
    revised = deepcopy(original)
    for c in revised:
        c['metadata'] = dict(reversed(list(c['metadata'].items())))
    BM25Index.build_or_load(revised, cache_root=str(tmp_path))
    assert len(list(tmp_path.iterdir())) == 1
