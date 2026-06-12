import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from data.indigo_documents import DOCUMENTS
from src.embedding.embedder import embed_batch, embed_chunks
from src.embedding.vector_store import QdrantVectorStore
from src.ingestion.chunker import ingest_all

VERIFY_QUERIES = [
    "What is the carry-on baggage weight limit?",
    "How do I redeem BluChip points?",
    "What happens if my flight is delayed?",
]


def run_verify(store: QdrantVectorStore) -> None:
    print("\n[verify] Running 3 test queries...")
    for q in VERIFY_QUERIES:
        vec = embed_batch([q])[0]
        results = store.query(vec, top_k=1)
        if results:
            r = results[0]
            print(f"  Q: {q}")
            print(f"     → score={r['score']:.3f}  title={r['metadata']['title']}")
        else:
            print(f"  Q: {q}\n     → no results")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Indigo documents into Qdrant.")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate collection before ingesting.")
    parser.add_argument("--verify", action="store_true", help="Run 3 test queries after ingestion.")
    args = parser.parse_args()

    store = QdrantVectorStore()

    if not args.reset:
        stats = store.stats()
        n = stats["total_vectors"]
        if n > 0:
            print(f"Collection already has {n} vectors. Use --reset to re-ingest.")
            if args.verify:
                run_verify(store)
            return

    if args.reset:
        store.recreate_collection()

    chunks = ingest_all(DOCUMENTS)
    embedded = embed_chunks(chunks)
    store.upsert(embedded)
    print(store.stats())

    if args.verify:
        run_verify(store)


if __name__ == "__main__":
    main()
