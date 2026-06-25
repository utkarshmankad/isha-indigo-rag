import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from data.indigo_documents import DOCUMENTS as INDIGO_DOCS
from data.air_india_documents import DOCUMENTS as AI_DOCS
from data.spicejet_documents import DOCUMENTS as SJ_DOCS
from data.dgca_documents import DOCUMENTS as DGCA_DOCS
from src.embedding.embedder import embed_batch, embed_chunks
from src.embedding.vector_store import QdrantVectorStore
from src.ingestion.chunker import ingest_all

ALL_DOCUMENTS = INDIGO_DOCS + AI_DOCS + SJ_DOCS + DGCA_DOCS

VERIFY_QUERIES = [
    "What is the carry-on baggage weight limit?",
    "How do I redeem Flying Returns miles on Air India?",
    "What happens if my flight is delayed under DGCA rules?",
    "What is SpiceJet SpiceFlex fare?",
]


def run_verify(store: QdrantVectorStore) -> None:
    print(f"\n[verify] Running {len(VERIFY_QUERIES)} test queries...")
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
    parser = argparse.ArgumentParser(description="Ingest all airline documents into Qdrant.")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate collection before ingesting.")
    parser.add_argument("--verify", action="store_true", help="Run test queries after ingestion.")
    parser.add_argument(
        "--airline",
        choices=["all", "indigo", "air_india", "spicejet", "dgca"],
        default="all",
        help="Ingest only a specific airline's documents (default: all).",
    )
    args = parser.parse_args()

    airline_map = {
        "all": ALL_DOCUMENTS,
        "indigo": INDIGO_DOCS,
        "air_india": AI_DOCS,
        "spicejet": SJ_DOCS,
        "dgca": DGCA_DOCS,
    }
    docs_to_ingest = airline_map[args.airline]
    print(f"[ingest] Airline filter: {args.airline} ({len(docs_to_ingest)} documents)")

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
        if args.airline == "all":
            store.recreate_collection()
        else:
            # Partial reset: delete only the targeted airline's points so
            # other airlines' data is preserved.
            print(f"[ingest] Partial reset: deleting existing vectors for airline='{args.airline}'")
            store.delete_by_airline(args.airline)

    chunks = ingest_all(docs_to_ingest)
    embedded = embed_chunks(chunks)
    store.upsert(embedded)
    print(store.stats())

    if args.verify:
        run_verify(store)


if __name__ == "__main__":
    main()
