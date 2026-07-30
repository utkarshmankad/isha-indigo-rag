import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import uuid

from src.observability.logging_config import get_logger
from src.security.rate_limiter import RateLimiter
from src.security.validator import QueryValidator

logger = get_logger("app")

st.set_page_config(
    page_title="ISHA — Indian Airlines Smart Helpdesk Assistant",
    page_icon="✈️",
    layout="wide",
)

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] h1 {
        color: #003580 !important;
    }
    [data-testid="stChatMessage"][data-message-author-role="assistant"] {
        border-left: 4px solid #003580;
        padding-left: 0.5rem;
        border-radius: 0 0.5rem 0.5rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

CATEGORY_EMOJI: dict[str, str] = {
    "baggage": "🧳",
    "check_in": "🎫",
    "fares_and_ticketing": "💰",
    "cancellations_and_refunds": "↩️",
    "flight_delays_and_cancellations": "⏰",
    "loyalty": "⭐",
    "special_assistance": "♿",
    "ancillary_services": "➕",
    "international_travel": "🌍",
    "safety_and_security": "🔒",
}

AIRLINE_OPTIONS = {
    "All Airlines": "all",
    "IndiGo (6E)": "indigo",
    "Air India (AI)": "air_india",
    "SpiceJet (SG)": "spicejet",
}

SAMPLE_QUESTIONS: dict[str, list[str]] = {
    "all": [
        "What are my rights if my flight is cancelled under DGCA rules?",
        "Can I carry a lithium power bank over 20000mAh on any Indian airline?",
        "What special assistance is available for wheelchair users?",
        "Compare baggage allowances across IndiGo, Air India, and SpiceJet.",
        "What compensation am I owed for denied boarding?",
    ],
    "indigo": [
        "IndiGo cancelled my flight 3 days before departure — what am I entitled to under DGCA?",
        "What is the baggage allowance on 6E Prime?",
        "How do I redeem BluChip points?",
        "What happens if my IndiGo flight is delayed more than 4 hours?",
        "Can I get a refund on a cancelled 6E Prime ticket?",
    ],
    "air_india": [
        "Air India cancelled my flight — what refund am I entitled to?",
        "What is the Flying Returns Silver tier benefit for baggage?",
        "How do I bid for a Business class upgrade on Air India?",
        "What is the carry-on baggage limit on Air India economy?",
        "How early can I check in online for an Air India flight?",
    ],
    "spicejet": [
        "What is SpiceJet SpiceFlex and how does it differ from SpiceSaver?",
        "Can I get a full refund on a SpiceFlex ticket?",
        "What is the SpiceClub Gold tier baggage benefit?",
        "How early do SpiceJet check-in counters open?",
        "SpiceJet delayed my flight 5 hours — what am I entitled to?",
    ],
}


@st.cache_resource(show_spinner="Connecting to Qdrant and building search index…")
def init_pipeline() -> dict:
    for key in ["OPENAI_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"]:
        if not os.getenv(key):
            try:
                val = st.secrets.get(key)
                if val:
                    os.environ[key] = val
            except Exception:
                pass

    from data.indigo_documents import DOCUMENTS as INDIGO_DOCS
    from data.air_india_documents import DOCUMENTS as AI_DOCS
    from data.spicejet_documents import DOCUMENTS as SJ_DOCS
    from data.dgca_documents import DOCUMENTS as DGCA_DOCS
    from src.agent.graph import build_graph, run_agent
    from src.embedding.vector_store import QdrantVectorStore
    from src.ingestion.chunker import ingest_all

    store = QdrantVectorStore()
    n = store.stats()["total_vectors"]
    if n == 0:
        raise RuntimeError(
            "Qdrant collection is empty. Run: uv run python scripts/ingest.py --reset"
        )

    all_docs = INDIGO_DOCS + AI_DOCS + SJ_DOCS + DGCA_DOCS
    chunks = ingest_all(all_docs)
    graph = build_graph(chunks, store)
    return {"graph": graph, "run_agent": run_agent, "n_chunks": n}


try:
    pipeline = init_pipeline()
except RuntimeError as e:
    st.error(f"❌ {e}")
    st.stop()
except Exception as e:
    st.error(
        "❌ Failed to initialise ISHA. Check credentials and Qdrant connection.\n\n"
        f"`{e}`"
    )
    st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("✈️ ISHA")
    st.caption("Indian Airlines Smart Helpdesk Assistant")
    st.success(f"✅ Connected to Qdrant — {pipeline['n_chunks']} policy chunks loaded")
    st.markdown("🟢 **System Ready**")
    st.divider()

    st.markdown("**Select Airline:**")
    airline_label = st.radio(
        label="Airline",
        options=list(AIRLINE_OPTIONS.keys()),
        index=0,
        label_visibility="collapsed",
    )
    selected_airline = AIRLINE_OPTIONS[airline_label]

    st.divider()

    st.markdown("**Passengers often ask:**")
    questions = SAMPLE_QUESTIONS.get(selected_airline, SAMPLE_QUESTIONS["all"])
    for q in questions:
        if st.button(q, key=f"sq_{selected_airline}_{hash(q)}", use_container_width=True):
            st.session_state["pending_query"] = q

    st.divider()

    st.markdown("**📊 Query Insights**")
    sq_count = st.session_state.get("session_query_count", 0)
    sq_confs = st.session_state.get("session_confidences", [])
    st.metric("Queries this session", sq_count)
    if sq_confs:
        avg_conf = sum(sq_confs) / len(sq_confs)
        st.metric("Avg confidence", f"{avg_conf:.2f}")
    else:
        st.caption("No queries yet.")

    rl_info = RateLimiter.get_rate_limit_info()
    st.caption(
        f"Rate limit: {rl_info['session_remaining']}/{rl_info['config_session_qpm']} "
        "queries left this minute"
    )

    st.divider()
    st.caption(
        "⚠️ ISHA is a demo assistant, not affiliated with IndiGo Airlines.  \n"
        "Official support: **0124-6173838** | [www.goindigo.in](https://www.goindigo.in)"
    )


# ── Main area ─────────────────────────────────────────────────────────────────
st.title("✈️ ISHA — Indian Airlines Smart Helpdesk Assistant")
st.subheader("Ask me anything about IndiGo, Air India, or SpiceJet policies")

if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "session_query_count" not in st.session_state:
    st.session_state["session_query_count"] = 0
if "session_confidences" not in st.session_state:
    st.session_state["session_confidences"] = []


def render_sources(chunks: list[dict]) -> None:
    with st.expander("📄 Sources consulted"):
        for chunk in chunks:
            cat = chunk["metadata"].get("category", "")
            emoji = CATEGORY_EMOJI.get(cat, "📋")
            title = chunk["metadata"].get("title", "Unknown")
            score = chunk.get("score", 0.0)
            st.markdown(f"{emoji} **{title}** — relevance: `{score:.3f}`")


# Render chat history
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("chunks"):
            render_sources(msg["chunks"])


# ── Query input ───────────────────────────────────────────────────────────────
user_input = st.chat_input("Ask about IndiGo policies, baggage, refunds, DGCA rights…")

query: str | None = None
airline = selected_airline

if "pending_query" in st.session_state:
    query = st.session_state["pending_query"]
    del st.session_state["pending_query"]
elif user_input:
    query = user_input

if query:
    with st.chat_message("user"):
        st.markdown(query)
    st.session_state["messages"].append({"role": "user", "content": query})

    # Rate limit check — reject before spending any retrieval/LLM cost.
    rate_result = RateLimiter.check_rate_limit()
    if not rate_result.is_allowed:
        logger.warning(
            "query blocked by rate limit",
            reason=rate_result.reason, retry_after_seconds=rate_result.retry_after_seconds,
        )
        with st.chat_message("assistant"):
            st.warning(f"⏳ {rate_result.reason}")
        st.session_state["messages"].append({
            "role": "assistant",
            "content": rate_result.reason,
        })
        is_valid = False
    else:
        # Validate query for security
        is_valid, reason, issues = QueryValidator.validate_input(query, airline)

        # Security warning if issues detected
        if issues:
            with st.warning("⚠️ Security Notice"):
                for category, message in issues:
                    if category.name == "safe":
                        st.markdown(f"ℹ️ {message}")
                    else:
                        st.error(f"🔒 {message}")
            if not is_valid:
                with st.chat_message("assistant"):
                    st.markdown(
                        "I cannot process this query due to security concerns. "
                        "Please rephrase without unusual patterns, and avoid mentioning personal information."
                    )
                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": "I cannot process this query due to security concerns.",
                })

    if is_valid:
        correlation_id = str(uuid.uuid4())

        with st.chat_message("assistant"):
            with st.spinner("Searching airline policy documents…"):
                try:
                    state = pipeline["run_agent"](
                        query, pipeline["graph"], airline=airline, correlation_id=correlation_id,
                    )
                    answer: str = state["answer"]
                    chunks: list[dict] = state["retrieved_chunks"]
                    conf: float = state.get("confidence", 0.0)
                except Exception:
                    logger.error("query failed in app layer", correlation_id=correlation_id, exc_info=True)
                    answer = (
                        "I encountered an error while processing your query. "
                        "Please try again or contact IndiGo at **0124-6173838**."
                    )
                    chunks = []
                    conf = 0.0

            st.markdown(answer)
            if chunks:
                render_sources(chunks)

        st.session_state["session_query_count"] += 1
        st.session_state["session_confidences"].append(conf)

        st.session_state["messages"].append({
            "role": "assistant",
            "content": answer,
            "chunks": chunks,
        })
