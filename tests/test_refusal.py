from unittest.mock import MagicMock, patch

from src.agent.graph import REFUSAL_FLOOR, build_graph, run_agent

SAMPLE_CHUNKS = [
    {
        "doc_id": "BAG-001",
        "chunk_id": "BAG-001_chunk_000",
        "text": "IndiGo carry-on baggage is limited to 7 kg.",
        "metadata": {
            "title": "Carry-On Baggage Policy",
            "category": "baggage",
            "doc_type": "policy",
            "last_updated": "2024-11-01",
            "source_doc_id": "BAG-001",
            "airline": "indigo",
        },
    },
]


def _mock_vector_store():
    store = MagicMock()
    store.query.return_value = []  # forces confidence = 0.0
    return store


@patch("src.agent.graph.embed_batch", return_value=[[0.0] * 8])
@patch("src.agent.graph.hybrid_search", return_value=[])
def test_low_confidence_triggers_refusal_without_llm_call(mock_hybrid, mock_embed):
    store = _mock_vector_store()
    graph = build_graph(SAMPLE_CHUNKS, store)

    with patch("src.agent.graph.generate_answer") as mock_generate:
        state = run_agent("What is the capital of France?", graph, airline="all")

    mock_generate.assert_not_called()
    assert state["confidence"] < REFUSAL_FLOOR
    assert "could not find this in the policy documents" in state["answer"].lower()
