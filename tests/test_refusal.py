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
def test_low_confidence_triggers_refusal_without_final_answer_llm_call(mock_hybrid, mock_embed):
    store = _mock_vector_store()
    graph = build_graph(SAMPLE_CHUNKS, store)

    with patch("src.agent.graph.generate_answer", return_value="a hypothetical passage") as mock_generate:
        state = run_agent("What is the capital of France?", graph, airline="all")

    # generate_answer is legitimately called once for HyDE expansion on the
    # retry pass (S7-T1) — but never for the final answer, since confidence
    # stays below REFUSAL_FLOOR and generate_node short-circuits before that.
    assert mock_generate.call_count == 1
    assert "USER QUESTION: What is the capital of France?" in mock_generate.call_args[0][0]
    assert "policy document answering this customer support question" in mock_generate.call_args[0][0]
    assert state["confidence"] < REFUSAL_FLOOR
    assert "could not find this in the policy documents" in state["answer"].lower()
