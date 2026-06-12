import os

from src.embedding.embedder import embed_batch
from src.embedding.vector_store import QdrantVectorStore

DEFAULT_TOP_K = 5
MAX_PER_DOC = 2
MAX_CONTEXT_CHARS = 3000

# Calibrated 2026-06-12: relevant queries scored 0.62–0.77; irrelevant
# ("capital of France") topped at 0.15. Threshold at 0.35 sits midway,
# giving ~0.20 margin above noise and ~0.27 below the weakest real hit.
MIN_SCORE_REAL = 0.35
MIN_SCORE_MOCK = 0.0

_SYSTEM_TEMPLATE = """\
You are IndiGo's virtual support agent. Answer the user's question using \
ONLY the context passages provided below. Rules:
- Cite documents by name when using their content.
- Use bullet points for any step-by-step instructions.
- State all amounts in INR (₹).
- If the answer cannot be found in the provided context, respond with:
  "I could not find this in IndiGo's policy documents. Please contact \
IndiGo at 0124-6173838 or visit www.goindigo.in"
- Do not speculate or use outside knowledge.

CONTEXT:
{context}"""


def embed_query(query: str) -> list[float]:
    return embed_batch([query])[0]


class RetrievalEngine:
    def __init__(self, store: QdrantVectorStore) -> None:
        self.store = store
        self.min_score = (
            MIN_SCORE_REAL if os.environ.get("OPENAI_API_KEY") else MIN_SCORE_MOCK
        )

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        filters: dict | None = None,
        max_per_doc: int = MAX_PER_DOC,
    ) -> list[dict]:
        qvec = embed_query(query)
        candidates = self.store.query(qvec, top_k=top_k * 2, filters=filters)

        before = len(candidates)
        candidates = [r for r in candidates if r["score"] >= self.min_score]
        discarded = before - len(candidates)
        if discarded:
            print(f"[retriever] Discarded {discarded} results below min_score={self.min_score}")

        seen_docs: dict[str, int] = {}
        deduped: list[dict] = []
        for r in candidates:
            doc_id = r["metadata"].get("source_doc_id", r["chunk_id"])
            if seen_docs.get(doc_id, 0) < max_per_doc:
                deduped.append(r)
                seen_docs[doc_id] = seen_docs.get(doc_id, 0) + 1

        return deduped[:top_k]

    def build_context(self, results: list[dict]) -> str:
        blocks: list[str] = []
        for i, r in enumerate(results, 1):
            m = r["metadata"]
            header = (
                f"[Source {i}] {m.get('title', 'Unknown')} "
                f"({m.get('doc_type', '')} | {m.get('category', '')} | "
                f"Updated: {m.get('last_updated', '')}) — "
                f"Relevance: {r['score']:.3f}"
            )
            blocks.append(f"{header}\n{r['text']}")

        full = "\n\n---\n\n".join(blocks)
        if len(full) > MAX_CONTEXT_CHARS:
            full = full[:MAX_CONTEXT_CHARS] + "\n[context truncated]"
        return full

    def build_prompt(self, query: str, context: str) -> str:
        system = _SYSTEM_TEMPLATE.format(context=context)
        return f"{system}\n\nUSER QUESTION: {query}"


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

    from dotenv import load_dotenv
    load_dotenv()

    store = QdrantVectorStore()
    engine = RetrievalEngine(store)

    queries = [
        "What is the carry-on baggage weight limit?",
        "Can I get a refund if I cancel my 6E Prime ticket?",
        "My flight was delayed 4 hours, what compensation am I owed?",
        "How do I redeem BluChip points?",
        "Can I carry a power bank in cabin baggage?",
    ]

    for q in queries:
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        print("=" * 60)
        results = engine.retrieve(q, top_k=3)
        for r in results:
            print(f"  {r['score']:.4f}  [{r['chunk_id']}]  {r['metadata']['title']}")
        ctx = engine.build_context(results)
        print(f"\nContext preview (first 200 chars):\n  {ctx[:200].replace(chr(10), ' ')}")
