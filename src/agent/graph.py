import os
import time
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from src.embedding.embedder import embed_batch
from src.embedding.vector_store import QdrantVectorStore
from src.observability.logging_config import get_logger
from src.retrieval.hybrid_search import BM25Index, hybrid_search
from src.retrieval.retriever import RetrievalEngine
from src.retrieval.tool_selector import route_query

load_dotenv()

logger = get_logger("agent.graph")

CONFIDENCE_THRESHOLD = 0.65
MAX_ITERATIONS = 2
DGCA_KEYWORDS = [
    "compensation", "rights", "dgca", "entitled", "cancelled flight",
    "refund rights", "complaint",
]
DGCA_TOOLS = ["flight_delays_and_cancellations", "cancellations_and_refunds"]
DGCA_INSTRUCTION = (
    "\n\nIMPORTANT: This query involves passenger rights under DGCA regulations. "
    "Cite specific DGCA circular numbers or guidelines if present in the context. "
    "Clearly state what the passenger is entitled to under Indian aviation law."
)


class AgentState(TypedDict):
    query: str
    airline: str
    selected_tools: list[str]
    retrieved_chunks: list[dict]
    context: str
    answer: str
    confidence: float
    iterations: int
    search_all: bool
    dgca_query: bool


def generate_answer(prompt: str) -> str:
    """Generate answer using OpenAI gpt-4o-mini."""
    def split_prompt(p: str) -> tuple[str, str]:
        if "\n\nUSER QUESTION: " in p:
            sys, usr = p.split("\n\nUSER QUESTION: ", 1)
            return sys, usr
        return p, ""

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        return "Error: OPENAI_API_KEY not configured."

    from openai import OpenAI
    client = OpenAI(api_key=openai_key)
    system_part, user_part = split_prompt(prompt)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_part},
            {"role": "user", "content": user_part},
        ],
        max_tokens=1024,
    )
    return response.choices[0].message.content or ""


def build_graph(chunks: list[dict], vector_store: QdrantVectorStore):
    bm25_index = BM25Index.build_or_load(chunks)
    engine = RetrievalEngine(vector_store)

    def select_tools_node(state: AgentState) -> dict:
        query = state["query"]
        route = route_query(query)

        selected = list(route["selected_tools"])
        search_all = route["search_all"]

        q_lower = query.lower()
        dgca_query = any(kw.lower() in q_lower for kw in DGCA_KEYWORDS)

        if dgca_query:
            for tool in DGCA_TOOLS:
                if tool not in selected:
                    selected.append(tool)
            logger.info("DGCA detected, force-added tools", dgca_tools=DGCA_TOOLS)

        logger.info(
            "tools selected",
            selected_tools=selected, search_all=search_all, dgca_query=dgca_query,
            reasoning=route["reasoning"],
        )

        return {
            "selected_tools": selected,
            "search_all": search_all,
            "dgca_query": dgca_query,
            "iterations": 0,
            "retrieved_chunks": [],
            "context": "",
            "answer": "",
            "confidence": 0.0,
            "airline": state.get("airline", "all"),
        }

    def retrieve_node(state: AgentState) -> dict:
        query = state["query"]
        iterations = state["iterations"] + 1
        search_all = state["search_all"]
        selected_tools = state["selected_tools"]
        airline = state.get("airline", "all")

        # When a specific airline is selected, always include DGCA docs for regulatory context
        airline_filter = None if airline == "all" else [airline, "dgca"]

        logger.info(
            "retrieve start", iteration=iterations, search_all=search_all, airline=airline,
        )

        qvec = embed_batch([query])[0]

        # Confidence from cosine similarity, scoped to airline if selected
        conf_results = vector_store.query(qvec, top_k=3, airline_filter=airline_filter)
        confidence = max((r["score"] for r in conf_results), default=0.0)
        logger.info("confidence computed", confidence=round(confidence, 4))

        # Hybrid search: per-tool filtered or global
        all_chunks: dict[str, dict] = {}
        if search_all:
            results = hybrid_search(
                query, qvec, bm25_index, vector_store, top_k=10,
                airline_filter=airline_filter,
            )
            for r in results:
                all_chunks[r["chunk_id"]] = r
        else:
            for tool in selected_tools:
                results = hybrid_search(
                    query, qvec, bm25_index, vector_store,
                    top_k=5, filters={"category": tool},
                    airline_filter=airline_filter,
                )
                for r in results:
                    all_chunks[r["chunk_id"]] = r

        # Dedupe, keep top 5 by fusion_score
        deduped = sorted(
            all_chunks.values(), key=lambda r: r["fusion_score"], reverse=True
        )[:5]

        logger.info(
            "retrieval deduped",
            chunk_count=len(deduped),
            top_scores=[round(r["fusion_score"], 4) for r in deduped],
        )

        # Pre-set search_all for possible second pass
        expand_next = confidence < CONFIDENCE_THRESHOLD and iterations < MAX_ITERATIONS

        return {
            "retrieved_chunks": deduped,
            "confidence": confidence,
            "iterations": iterations,
            "search_all": expand_next,
        }

    def generate_node(state: AgentState) -> dict:
        query = state["query"]
        chunks = state["retrieved_chunks"]
        dgca_query = state["dgca_query"]

        logger.info("generating answer", dgca_query=dgca_query)

        airline = state.get("airline", "all")
        context = engine.build_context(chunks)
        prompt = engine.build_prompt(query, context, airline=airline)
        if dgca_query:
            prompt = prompt + DGCA_INSTRUCTION

        t0 = time.time()
        answer = generate_answer(prompt)
        latency_ms = int((time.time() - t0) * 1000)

        try:
            from src.observability.logger import log_query
            log_query(
                query=query,
                selected_tools=state["selected_tools"],
                retrieved_chunks=chunks,
                confidence=state["confidence"],
                answer=answer,
                latency_ms=latency_ms,
                dgca_query=dgca_query,
            )
        except Exception:
            logger.warning("query log write failed", exc_info=True)

        return {"context": context, "answer": answer}

    def should_continue(state: AgentState) -> str:
        confidence = state["confidence"]
        iterations = state["iterations"]
        next_step = "generate" if confidence >= CONFIDENCE_THRESHOLD or iterations >= MAX_ITERATIONS else "retrieve"
        logger.info("routing decision", confidence=round(confidence, 4), iterations=iterations, next_step=next_step)
        return next_step

    workflow = StateGraph(AgentState)
    workflow.add_node("select_tools", select_tools_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("generate", generate_node)

    workflow.set_entry_point("select_tools")
    workflow.add_edge("select_tools", "retrieve")
    workflow.add_conditional_edges(
        "retrieve",
        should_continue,
        {"generate": "generate", "retrieve": "retrieve"},
    )
    workflow.add_edge("generate", END)

    return workflow.compile()


def run_agent(query: str, graph, airline: str = "all") -> AgentState:
    logger.info("query received", query=query, airline=airline)

    initial_state: AgentState = {
        "query": query,
        "airline": airline,
        "selected_tools": [],
        "retrieved_chunks": [],
        "context": "",
        "answer": "",
        "confidence": 0.0,
        "iterations": 0,
        "search_all": False,
        "dgca_query": False,
    }

    final_state = graph.invoke(initial_state)

    logger.info(
        "query complete",
        confidence=round(final_state["confidence"], 4),
        iterations=final_state["iterations"],
        dgca_query=final_state["dgca_query"],
        answer_length=len(final_state["answer"]),
    )
    return final_state


if __name__ == "__main__":
    from data.indigo_documents import DOCUMENTS
    from src.ingestion.chunker import ingest_all

    print("Loading documents and building indexes...")
    chunks = ingest_all(DOCUMENTS)
    store = QdrantVectorStore()
    graph = build_graph(chunks, store)

    test_queries = [
        "IndiGo cancelled my flight 3 days before departure — what am I entitled to under DGCA?",
        "What is the baggage allowance on 6E Prime?",
        "Can I carry a lithium power bank over 20000mAh?",
    ]

    for q in test_queries:
        run_agent(q, graph)
