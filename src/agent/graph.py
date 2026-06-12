import os
import time
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from src.embedding.embedder import embed_batch
from src.embedding.vector_store import QdrantVectorStore
from src.retrieval.hybrid_search import BM25Index, hybrid_search
from src.retrieval.retriever import RetrievalEngine
from src.retrieval.tool_selector import route_query

load_dotenv()

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
    selected_tools: list[str]
    retrieved_chunks: list[dict]
    context: str
    answer: str
    confidence: float
    iterations: int
    search_all: bool
    dgca_query: bool


def generate_answer(prompt: str) -> str:
    """Try Anthropic claude-opus-4-8 (adaptive thinking), fall back to OpenAI gpt-4o-mini."""
    def split_prompt(p: str) -> tuple[str, str]:
        if "\n\nUSER QUESTION: " in p:
            sys, usr = p.split("\n\nUSER QUESTION: ", 1)
            return sys, usr
        return p, ""

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            system_part, user_part = split_prompt(prompt)
            response = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=system_part,
                messages=[{"role": "user", "content": user_part}],
            )
            for block in response.content:
                if block.type == "text":
                    return block.text
        except Exception as e:
            print(f"[generate] Anthropic error: {e} — falling back to OpenAI")

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
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
        except Exception as e:
            print(f"[generate] OpenAI error: {e}")

    return "Error: no LLM API keys configured."


def build_graph(chunks: list[dict], vector_store: QdrantVectorStore):
    bm25_index = BM25Index()
    bm25_index.build(chunks)
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
            print(f"[select_tools] DGCA detected — force-added {DGCA_TOOLS}")

        print(f"[select_tools] tools={selected}, search_all={search_all}, dgca={dgca_query}")
        print(f"[select_tools] reasoning: {route['reasoning']}")

        return {
            "selected_tools": selected,
            "search_all": search_all,
            "dgca_query": dgca_query,
            "iterations": 0,
            "retrieved_chunks": [],
            "context": "",
            "answer": "",
            "confidence": 0.0,
        }

    def retrieve_node(state: AgentState) -> dict:
        query = state["query"]
        iterations = state["iterations"] + 1
        search_all = state["search_all"]
        selected_tools = state["selected_tools"]

        print(f"\n[retrieve] iteration={iterations}, search_all={search_all}")

        qvec = embed_batch([query])[0]

        # Confidence from unfiltered cosine similarity — global KB coverage check
        conf_results = vector_store.query(qvec, top_k=3)
        confidence = max((r["score"] for r in conf_results), default=0.0)
        print(f"[retrieve] confidence (max cosine, unfiltered)={confidence:.4f}")

        # Hybrid search: per-tool filtered or global
        all_chunks: dict[str, dict] = {}
        if search_all:
            results = hybrid_search(query, qvec, bm25_index, vector_store, top_k=10)
            for r in results:
                all_chunks[r["chunk_id"]] = r
        else:
            for tool in selected_tools:
                results = hybrid_search(
                    query, qvec, bm25_index, vector_store,
                    top_k=5, filters={"category": tool},
                )
                for r in results:
                    all_chunks[r["chunk_id"]] = r

        # Dedupe, keep top 5 by fusion_score
        deduped = sorted(
            all_chunks.values(), key=lambda r: r["fusion_score"], reverse=True
        )[:5]

        print(f"[retrieve] {len(deduped)} chunks after dedup+top5")
        for r in deduped:
            title = r["metadata"].get("title", "")[:60]
            print(f"  fusion={r['fusion_score']:.4f}  score={r['score']:.4f}  {title}")

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

        print(f"\n[generate] building answer (dgca_query={dgca_query})")

        context = engine.build_context(chunks)
        prompt = engine.build_prompt(query, context)
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
        except Exception as log_err:
            print(f"[logger] warning: {log_err}")

        return {"context": context, "answer": answer}

    def should_continue(state: AgentState) -> str:
        confidence = state["confidence"]
        iterations = state["iterations"]
        if confidence >= CONFIDENCE_THRESHOLD or iterations >= MAX_ITERATIONS:
            print(f"[router] confidence={confidence:.4f}, iterations={iterations} → generate")
            return "generate"
        print(f"[router] confidence={confidence:.4f}, iterations={iterations} → retrieve (expand)")
        return "retrieve"

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


def run_agent(query: str, graph) -> AgentState:
    print(f"\n{'='*70}")
    print(f"QUERY: {query}")
    print("=" * 70)

    initial_state: AgentState = {
        "query": query,
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

    print(f"\n{'─'*70}")
    print(f"ANSWER:\n{final_state['answer']}")
    print(f"{'─'*70}")
    print(
        f"confidence={final_state['confidence']:.4f}  "
        f"iterations={final_state['iterations']}  "
        f"dgca={final_state['dgca_query']}"
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
