from unittest.mock import MagicMock, patch

from src.agent.graph import build_graph, run_agent

SAMPLE_CHUNKS = [
    {
        "doc_id": "BAG-001",
        "chunk_id": "BAG-001_chunk_000",
        "text": "IndiGo Blue passengers get 15kg. 6E Prime passengers get 25kg.",
        "metadata": {
            "title": "Checked Baggage Allowances", "category": "baggage",
            "doc_type": "policy", "last_updated": "2024-11-01",
            "source_doc_id": "BAG-002", "airline": "indigo",
        },
    },
]


def _high_confidence_hybrid_result():
    return [{
        "chunk_id": "BAG-001_chunk_000", "score": 0.9, "vector_score": 0.9,
        "text": SAMPLE_CHUNKS[0]["text"], "metadata": SAMPLE_CHUNKS[0]["metadata"],
        "fusion_score": 0.9,
    }]


@patch("src.agent.graph.embed_batch", return_value=[[0.1] * 8])
@patch("src.agent.graph.hybrid_search", return_value=_high_confidence_hybrid_result())
def test_underspecified_baggage_query_gets_exception_guidance_in_prompt(mock_hybrid, mock_embed):
    store = MagicMock()
    graph = build_graph(SAMPLE_CHUNKS, store)

    with patch("src.agent.graph.generate_answer", return_value="ok") as mock_generate:
        run_agent("what is my baggage allowance?", graph, airline="indigo")

    prompt = mock_generate.call_args[0][0]
    assert "IMPORTANT: The passenger did not specify" in prompt
    assert "fare class" in prompt


@patch("src.agent.graph.embed_batch", return_value=[[0.1] * 8])
@patch("src.agent.graph.hybrid_search", return_value=_high_confidence_hybrid_result())
def test_fully_specified_baggage_query_gets_no_exception_guidance(mock_hybrid, mock_embed):
    store = MagicMock()
    graph = build_graph(SAMPLE_CHUNKS, store)

    with patch("src.agent.graph.generate_answer", return_value="ok") as mock_generate:
        run_agent("6E Prime baggage allowance for an international flight", graph, airline="indigo")

    prompt = mock_generate.call_args[0][0]
    assert "IMPORTANT: The passenger did not specify" not in prompt


@patch("src.agent.graph.embed_batch", return_value=[[0.1] * 8])
@patch("src.agent.graph.hybrid_search", return_value=_high_confidence_hybrid_result())
def test_exception_guidance_never_changes_retrieval_or_confidence(mock_hybrid, mock_embed):
    """The guidance only touches the generation prompt — retrieval,
    confidence, and billing/refusal behavior must be identical whether or
    not guidance was added."""
    store = MagicMock()
    graph = build_graph(SAMPLE_CHUNKS, store)

    with patch("src.agent.graph.generate_answer", return_value="ok"):
        state = run_agent("what is my baggage allowance?", graph, airline="indigo")

    assert state["refused"] is False
    assert state["confidence"] == 0.9
    assert len(state["retrieved_chunks"]) == 1
