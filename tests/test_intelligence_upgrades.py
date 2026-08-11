from unittest.mock import MagicMock, patch

from src.agent.graph import build_graph, run_agent
from src.retrieval.retriever import RetrievalEngine, _build_system_prompt

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


# ── S7-T1: HyDE ─────────────────────────────────────────────────────────────

@patch("src.agent.graph.embed_batch", return_value=[[0.1] * 8])
@patch("src.agent.graph.hybrid_search", return_value=[])
def test_hyde_not_used_on_first_iteration(mock_hybrid, mock_embed):
    """First attempt should embed the raw query — no LLM call yet, no
    latency/cost paid unless the first pass actually needs a retry."""
    store = MagicMock()
    store.query.return_value = [{"score": 0.9, "metadata": {}, "text": "x", "chunk_id": "c1"}]
    graph = build_graph(SAMPLE_CHUNKS, store)

    with patch("src.agent.graph.generate_answer", return_value="ok") as mock_generate:
        run_agent("what is the baggage limit", graph, airline="indigo")

    # First embed_batch call should be the raw query, not a HyDE passage —
    # generate_answer's only call (if any) is the final-answer one.
    first_call_args = mock_embed.call_args_list[0][0][0]
    assert first_call_args == ["what is the baggage limit"]


@patch("src.agent.graph.hybrid_search", return_value=[])
def test_hyde_used_on_retry_pass(mock_hybrid):
    """On the retry pass (confidence stayed low), the embedded text should
    be the HyDE passage, not the raw query."""
    store = MagicMock()
    store.query.return_value = []  # forces confidence 0.0 -> retry
    graph = build_graph(SAMPLE_CHUNKS, store)

    with patch("src.agent.graph.embed_batch", return_value=[[0.1] * 8]) as mock_embed, \
         patch("src.agent.graph.generate_answer", return_value="a hypothetical policy passage") as mock_generate:
        run_agent("vague question", graph, airline="indigo")

    embed_texts = [call[0][0][0] for call in mock_embed.call_args_list]
    assert "vague question" in embed_texts  # first pass: raw query
    assert "a hypothetical policy passage" in embed_texts  # retry pass: HyDE output


@patch("src.agent.graph.embed_batch", return_value=[[0.1] * 8])
@patch("src.agent.graph.hybrid_search", return_value=[])
def test_hyde_failure_falls_back_to_raw_query(mock_hybrid, mock_embed):
    """If the HyDE LLM call itself fails, retrieval must still proceed with
    the raw query rather than crashing the whole request."""
    store = MagicMock()
    store.query.return_value = []
    graph = build_graph(SAMPLE_CHUNKS, store)

    def _raise_on_hyde(prompt):
        if "policy document answering" in prompt:
            raise RuntimeError("LLM unavailable")
        return "ok"

    with patch("src.agent.graph.generate_answer", side_effect=_raise_on_hyde):
        state = run_agent("vague question", graph, airline="indigo")

    assert state["stage_error"] == ""  # no crash, degraded gracefully


# ── S7-T2: conversation memory ──────────────────────────────────────────────

def test_build_prompt_includes_recent_history():
    engine = RetrievalEngine.__new__(RetrievalEngine)  # skip __init__ (no store needed)
    history = [
        {"role": "user", "content": "What is the baggage allowance?"},
        {"role": "assistant", "content": "7 kg for carry-on."},
    ]
    prompt = engine.build_prompt("what about international flights?", "CONTEXT HERE", "indigo", history=history)
    assert "PRIOR CONVERSATION" in prompt
    assert "What is the baggage allowance?" in prompt
    assert "7 kg for carry-on." in prompt


def test_build_prompt_omits_history_block_when_absent():
    engine = RetrievalEngine.__new__(RetrievalEngine)
    prompt = engine.build_prompt("what is the baggage allowance?", "CONTEXT HERE", "indigo")
    assert "PRIOR CONVERSATION" not in prompt


def test_build_prompt_caps_history_length():
    engine = RetrievalEngine.__new__(RetrievalEngine)
    history = [{"role": "user", "content": f"turn {i}"} for i in range(20)]
    prompt = engine.build_prompt("current question", "CTX", "indigo", history=history)
    assert "turn 19" in prompt  # most recent kept
    assert "turn 0" not in prompt  # oldest dropped


@patch("src.agent.graph.hybrid_search", return_value=[])
def test_follow_up_query_gets_topic_context_from_history_for_retrieval(mock_hybrid):
    """A short follow-up with no topic keywords of its own ('what about for
    international flights?') must still get the prior turn's topic folded
    into what's embedded for retrieval — otherwise conversation memory only
    helps generation, not finding the right documents in the first place."""
    store = MagicMock()
    store.query.return_value = [{"score": 0.9, "metadata": {}, "text": "x", "chunk_id": "c1"}]
    graph = build_graph(SAMPLE_CHUNKS, store)
    history = [
        {"role": "user", "content": "What is the baggage allowance on 6E Prime?"},
        {"role": "assistant", "content": "7kg carry-on plus checked baggage."},
    ]

    with patch("src.agent.graph.embed_batch", return_value=[[0.1] * 8]) as mock_embed, \
         patch("src.agent.graph.generate_answer", return_value="ok"):
        run_agent("what about for international flights?", graph, airline="indigo", history=history)

    first_embed_text = mock_embed.call_args_list[0][0][0][0]
    assert "baggage allowance on 6E Prime" in first_embed_text
    assert "what about for international flights?" in first_embed_text


# ── S7-T3: multilingual (Hindi) ──────────────────────────────────────────────

def test_system_prompt_instructs_language_matching():
    prompt = _build_system_prompt("some context", "indigo")
    assert "same language" in prompt.lower()
    assert "hindi" in prompt.lower()
