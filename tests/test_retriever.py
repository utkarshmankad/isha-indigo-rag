import pytest
from unittest.mock import MagicMock

from src.retrieval.retriever import MAX_CONTEXT_CHARS, RetrievalEngine, _build_system_prompt

SAMPLE_CHUNKS = [
    {
        "chunk_id": "doc_0_chunk_000",
        "score": 0.85,
        "text": "IndiGo economy allows 15 kg checked baggage.",
        "metadata": {
            "title": "IndiGo Baggage Policy",
            "category": "baggage",
            "doc_type": "policy",
            "last_updated": "2025-01-01",
            "airline": "indigo",
        },
    },
    {
        "chunk_id": "doc_1_chunk_000",
        "score": 0.72,
        "text": "DGCA mandates compensation for delays over 3 hours.",
        "metadata": {
            "title": "DGCA Passenger Rights",
            "category": "flight_delays_and_cancellations",
            "doc_type": "regulation",
            "last_updated": "2024-06-01",
            "airline": "dgca",
        },
    },
]


def _make_engine() -> RetrievalEngine:
    store = MagicMock()
    store.query.return_value = []
    return RetrievalEngine(store)


def test_system_prompt_contains_airline_label():
    prompt = _build_system_prompt("ctx", airline="indigo")
    assert "IndiGo" in prompt


def test_system_prompt_air_india():
    prompt = _build_system_prompt("ctx", airline="air_india")
    assert "Air India" in prompt


def test_system_prompt_all_uses_generic_label():
    prompt = _build_system_prompt("ctx", airline="all")
    assert "the airline" in prompt


def test_system_prompt_contains_context():
    ctx = "Some policy text."
    prompt = _build_system_prompt(ctx, airline="indigo")
    assert ctx in prompt


def test_build_context_source_numbering():
    engine = _make_engine()
    ctx = engine.build_context(SAMPLE_CHUNKS)
    assert "[Source 1]" in ctx
    assert "[Source 2]" in ctx


def test_build_context_includes_titles():
    engine = _make_engine()
    ctx = engine.build_context(SAMPLE_CHUNKS)
    assert "IndiGo Baggage Policy" in ctx
    assert "DGCA Passenger Rights" in ctx


def test_build_context_truncation():
    engine = _make_engine()
    big_chunk = {
        "chunk_id": "big",
        "score": 0.9,
        "text": "X" * (MAX_CONTEXT_CHARS + 1000),
        "metadata": {
            "title": "Big Doc",
            "category": "baggage",
            "doc_type": "policy",
            "last_updated": "2025-01-01",
        },
    }
    ctx = engine.build_context([big_chunk])
    assert "[context truncated]" in ctx
    assert len(ctx) <= MAX_CONTEXT_CHARS + 100


def test_build_context_empty_chunks():
    engine = _make_engine()
    assert engine.build_context([]) == ""


def test_build_prompt_contains_query():
    engine = _make_engine()
    ctx = engine.build_context(SAMPLE_CHUNKS)
    prompt = engine.build_prompt("What is the baggage limit?", ctx, airline="indigo")
    assert "What is the baggage limit?" in prompt


def test_build_prompt_split_marker():
    engine = _make_engine()
    ctx = engine.build_context(SAMPLE_CHUNKS)
    prompt = engine.build_prompt("test query", ctx)
    assert "\n\nUSER QUESTION: " in prompt
