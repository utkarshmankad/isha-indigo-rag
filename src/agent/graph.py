import math
import os
import time
import uuid
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from src.embedding.embedder import embed_batch
from src.embedding.vector_store import QdrantVectorStore
from src.observability.logging_config import get_logger
from src.reliability.circuit_breaker import CircuitBreaker
from src.retrieval.hybrid_search import BM25Index, hybrid_search
from src.retrieval.retriever import MAX_CONTEXT_CHARS, RetrievalEngine
from src.retrieval.tool_selector import route_query
from src.security.prompt_protection import PromptGuard

load_dotenv()

logger = get_logger("agent.graph")

# Trip after 5 consecutive OpenAI failures, fail fast for 30s, then probe again.
llm_circuit_breaker = CircuitBreaker(
    name="openai_chat_completions", failure_threshold=5, recovery_timeout_seconds=30.0,
)

CONFIDENCE_THRESHOLD = 0.65
# Below this, even after exhausting retries, retrieval found nothing usable —
# refuse instead of asking the LLM to answer from a near-empty/irrelevant context.
REFUSAL_FLOOR = 0.35
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
    stage_error: str
    refused: bool
    correlation_id: str
    history: list[dict[str, str]]


_FALLBACK_CONTACTS = {
    "indigo": "IndiGo at 0124-6173838 or visit www.goindigo.in",
    "air_india": "Air India at 1860-233-1407 or visit www.airindia.com",
    "spicejet": "SpiceJet at 0124-7180000 or visit www.spicejet.com",
    "all": "the airline's customer support or their official website",
}


def _fallback_answer(airline: str) -> str:
    contact = _FALLBACK_CONTACTS.get(airline, _FALLBACK_CONTACTS["all"])
    return (
        "I'm having trouble generating an answer right now. "
        f"Please try again shortly, or contact {contact}."
    )


def _last_user_turn(history: list[dict[str, str]]) -> str:
    """Most recent prior user message, if any — used to give short follow-up
    queries ("what about international flights?") enough context for tool
    routing and retrieval to find the right documents. Conversation memory
    (S7-T2) originally only reached the final generation prompt; a short
    follow-up with no topic keywords of its own still failed retrieval
    entirely, which defeats the point of remembering the conversation.

    Delimiter-neutralized before returning: this text gets concatenated
    into both the tool-routing input and the HyDE LLM prompt below, so it
    must not be able to forge ISHA's own prompt sentinel strings (S8
    security review finding).
    """
    for turn in reversed(history):
        if turn.get("role") == "user":
            return PromptGuard.neutralize_delimiters(turn.get("content", ""))
    return ""


def _refusal_answer(airline: str) -> str:
    contact = _FALLBACK_CONTACTS.get(airline, _FALLBACK_CONTACTS["all"])
    return (
        "I could not find this in the policy documents. "
        f"Please contact {contact}."
    )


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

    def _call():
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_part},
                {"role": "user", "content": user_part},
            ],
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""

    return llm_circuit_breaker.call(_call)


def build_graph(chunks: list[dict], vector_store: QdrantVectorStore):
    bm25_index = BM25Index.build_or_load(chunks)
    engine = RetrievalEngine(vector_store)

    def select_tools_node(state: AgentState) -> dict:
        query = state["query"]
        cid = state["correlation_id"]
        hist_snippet = _last_user_turn(state.get("history", []))
        routing_input = f"{hist_snippet} {query}".strip() if hist_snippet else query

        try:
            route = route_query(routing_input)
            selected = list(route["selected_tools"])
            search_all = route["search_all"]

            q_lower = routing_input.lower()
            dgca_query = any(kw.lower() in q_lower for kw in DGCA_KEYWORDS)

            if dgca_query:
                for tool in DGCA_TOOLS:
                    if tool not in selected:
                        selected.append(tool)
                logger.info("DGCA detected, force-added tools", correlation_id=cid, dgca_tools=DGCA_TOOLS)

            logger.info(
                "tools selected",
                correlation_id=cid,
                selected_tools=selected, search_all=search_all, dgca_query=dgca_query,
                reasoning=route["reasoning"],
            )
            stage_error = ""
        except Exception:
            # Tool routing failed: degrade to a full-corpus search rather than crash.
            logger.error(
                "tool selection stage failed, degrading to search_all",
                correlation_id=cid, exc_info=True,
            )
            selected = []
            search_all = True
            dgca_query = False
            stage_error = "select_tools"

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
            "stage_error": stage_error,
        }

    def retrieve_node(state: AgentState) -> dict:
        query = state["query"]
        cid = state["correlation_id"]
        iterations = state["iterations"] + 1
        search_all = state["search_all"]
        selected_tools = state["selected_tools"]
        airline = state.get("airline", "all")
        hist_snippet = _last_user_turn(state.get("history", []))
        # Context-enriched text for embedding only — BM25 keyword search
        # below still uses the raw `query` untouched.
        query_with_context = f"{hist_snippet} {query}".strip() if hist_snippet else query

        # When a specific airline is selected, always include DGCA docs for regulatory context
        airline_filter = None if airline == "all" else [airline, "dgca"]

        logger.info(
            "retrieve start", correlation_id=cid, iteration=iterations, search_all=search_all, airline=airline,
        )

        stage_error = ""

        # HyDE (S7-T1): on the retry pass — the first attempt already scored
        # below CONFIDENCE_THRESHOLD — generate a hypothetical policy-style
        # passage and embed that instead of the raw (often vague) query.
        # Hypothetical answers tend to land closer to real policy text in
        # embedding space than short questions do. BM25 keyword matching
        # still uses the raw query below; only the vector side changes.
        embed_source = query_with_context
        if iterations > 1:
            try:
                hyde_prompt = (
                    "Write a short, plausible-sounding passage (2-3 sentences) that "
                    "could plausibly appear in an airline policy document answering "
                    "this customer support question. Be specific and confident — "
                    "don't hedge or say you don't know. This text is only used to "
                    "improve document search and is never shown to the user."
                    f"\n\nUSER QUESTION: {query_with_context}"
                )
                embed_source = generate_answer(hyde_prompt)
                logger.info("HyDE expansion applied", correlation_id=cid, iteration=iterations)
            except Exception:
                logger.warning(
                    "HyDE expansion failed, falling back to raw query",
                    correlation_id=cid, exc_info=True,
                )
                embed_source = query_with_context

        try:
            qvec = embed_batch([embed_source])[0]
        except Exception:
            # Embedding stage failed: no vector, so retrieval can't run this pass.
            logger.error("embedding stage failed", correlation_id=cid, exc_info=True)
            return {
                "retrieved_chunks": [],
                "confidence": 0.0,
                "iterations": iterations,
                "search_all": False,
                "stage_error": "embedding",
            }

        try:
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
                (r for r in all_chunks.values() if r.get("text", "").strip()),
                key=lambda r: r["fusion_score"], reverse=True
            )[:5]
            # Keep complete passages that actually fit the generation context.
            selected = []
            for chunk in deduped:
                if len(engine.build_context(selected + [chunk])) <= MAX_CONTEXT_CHARS:
                    selected.append(chunk)
            deduped = selected
            scores = [r.get("vector_score", 0.0) for r in deduped]
            confidence = max((min(1.0, max(0.0, score)) for score in scores
                              if isinstance(score, (int, float)) and math.isfinite(score)), default=0.0)
            logger.info("evidence similarity computed", correlation_id=cid, confidence=confidence)

            logger.info(
                "retrieval deduped",
                correlation_id=cid,
                chunk_count=len(deduped),
                top_scores=[round(r["fusion_score"], 4) for r in deduped],
            )
        except Exception:
            # Retrieval backend (Qdrant/BM25) failed: proceed with no chunks
            # instead of crashing the whole query.
            logger.error("retrieval stage failed", correlation_id=cid, exc_info=True)
            return {
                "retrieved_chunks": [],
                "confidence": 0.0,
                "iterations": iterations,
                "search_all": False,
                "stage_error": "retrieval",
            }

        # Pre-set search_all for possible second pass
        expand_next = confidence < CONFIDENCE_THRESHOLD and iterations < MAX_ITERATIONS

        return {
            "retrieved_chunks": deduped,
            "confidence": confidence,
            "iterations": iterations,
            "search_all": expand_next,
            "stage_error": stage_error,
        }

    def generate_node(state: AgentState) -> dict:
        query = state["query"]
        cid = state["correlation_id"]
        chunks = state["retrieved_chunks"]
        dgca_query = state["dgca_query"]

        logger.info("generating answer", correlation_id=cid, dgca_query=dgca_query)

        airline = state.get("airline", "all")
        confidence = state["confidence"]

        if state.get("stage_error") in {"embedding", "retrieval"}:
            return {"context": "", "answer": _fallback_answer(airline),
                    "stage_error": state["stage_error"]}

        if not chunks or confidence < REFUSAL_FLOOR:
            logger.info(
                "confidence below refusal floor, skipping LLM call",
                correlation_id=cid, confidence=round(confidence, 4), floor=REFUSAL_FLOOR,
            )
            answer = _refusal_answer(airline)
            try:
                from src.observability.logger import log_query
                log_query(
                    query=query, selected_tools=state["selected_tools"], retrieved_chunks=chunks,
                    confidence=confidence, answer=answer, latency_ms=0, dgca_query=dgca_query,
                    correlation_id=cid, expanded_search=state["iterations"] > 1,
                    stage_error=state.get("stage_error", ""), airline=airline, refused=True,
                )
            except Exception:
                logger.warning("query log write failed", correlation_id=cid, exc_info=True)

            try:
                from src.escalation.queue import enqueue_escalation
                enqueue_escalation(query=query, airline=airline, confidence=confidence, correlation_id=cid)
            except Exception:
                logger.warning("escalation enqueue failed", correlation_id=cid, exc_info=True)

            return {"context": "", "answer": answer, "stage_error": "", "refused": True}

        try:
            context = engine.build_context(chunks)
            prompt = engine.build_prompt(query, context, airline=airline, history=state.get("history"))
            if dgca_query:
                prompt = prompt + DGCA_INSTRUCTION
        except Exception:
            logger.error("prompt construction failed", correlation_id=cid, exc_info=True)
            return {"context": "", "answer": _fallback_answer(airline), "stage_error": "generation"}

        t0 = time.time()
        try:
            answer = generate_answer(prompt)
        except Exception:
            # LLM call failed outright: don't crash the request, give a safe fallback.
            logger.error("generation stage failed", correlation_id=cid, exc_info=True)
            return {"context": context, "answer": _fallback_answer(airline), "stage_error": "generation"}
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
                correlation_id=cid,
                expanded_search=state["iterations"] > 1,
                stage_error=state.get("stage_error", ""),
                airline=airline, refused=False,
            )
        except Exception:
            logger.warning("query log write failed", correlation_id=cid, exc_info=True)

        return {"context": context, "answer": answer, "stage_error": ""}

    def should_continue(state: AgentState) -> str:
        confidence = state["confidence"]
        iterations = state["iterations"]
        next_step = "generate" if confidence >= CONFIDENCE_THRESHOLD or iterations >= MAX_ITERATIONS else "retrieve"
        logger.info(
            "routing decision",
            correlation_id=state["correlation_id"],
            confidence=round(confidence, 4), iterations=iterations, next_step=next_step,
        )
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


def run_agent(
    query: str, graph, airline: str = "all", correlation_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> AgentState:
    cid = correlation_id or str(uuid.uuid4())
    logger.info("query received", correlation_id=cid, query=query, airline=airline)

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
        "stage_error": "",
        "refused": False,
        "correlation_id": cid,
        "history": history or [],
    }

    final_state = graph.invoke(initial_state)

    logger.info(
        "query complete",
        correlation_id=cid,
        confidence=round(final_state["confidence"], 4),
        iterations=final_state["iterations"],
        dgca_query=final_state["dgca_query"],
        answer_length=len(final_state["answer"]),
        stage_error=final_state.get("stage_error", ""),
    )
    return final_state


def run_agent_for_tenant(
    query: str, graph, tenant, correlation_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> AgentState:
    """Tenant-scoped entry point (S4-T2): airline comes from the authenticated
    tenant, not a caller-supplied argument, so a tenant can never widen its
    own scope by passing a different `airline` value.
    """
    return run_agent(query, graph, airline=tenant.airline, correlation_id=correlation_id, history=history)


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
