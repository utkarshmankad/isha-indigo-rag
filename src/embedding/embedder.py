import hashlib
import math
import os
import time

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
BATCH_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

_path_announced = False


def mock_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    seed = int(hashlib.sha256(text.encode()).hexdigest(), 16)
    vec = []
    state = seed
    for _ in range(dim):
        state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        # lower 32 bits → [0, 1) → centre to [-0.5, 0.5)
        val = (state & 0xFFFFFFFF) / 0x100000000 - 0.5
        vec.append(val)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed_batch(texts: list[str]) -> list[list[float]]:
    global _path_announced

    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        if not _path_announced:
            print("[embedder] No OPENAI_API_KEY — using mock embeddings.")
            _path_announced = True
        return [mock_embed(t) for t in texts]

    if not _path_announced:
        print(f"[embedder] Using OpenAI {EMBEDDING_MODEL}.")
        _path_announced = True

    try:
        from openai import OpenAI, RateLimitError, APIConnectionError
    except ImportError as e:
        raise ImportError("openai package required for real embeddings.") from e

    client = OpenAI(api_key=api_key)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
            ordered = sorted(response.data, key=lambda r: r.index)
            return [r.embedding for r in ordered]
        except (RateLimitError, APIConnectionError) as e:
            if attempt == MAX_RETRIES:
                raise
            print(f"[embedder] Retry {attempt}/{MAX_RETRIES} after error: {e}")
            time.sleep(RETRY_DELAY_SECONDS * attempt)


def embed_chunks(chunks: list[dict]) -> list[dict]:
    total = len(chunks)
    total_chars = sum(len(c['text']) for c in chunks)
    est_tokens = total_chars / 4
    est_cost = est_tokens / 1_000_000 * 0.02
    print(f"[embedder] {total} chunks | ~{est_tokens:.0f} tokens | est. cost ${est_cost:.6f}")

    embedded = []
    for batch_start in range(0, total, BATCH_SIZE):
        batch = chunks[batch_start:batch_start + BATCH_SIZE]
        batch_end = batch_start + len(batch)
        print(f"[embedder] Embedding batch {batch_start+1}–{batch_end} / {total} ...", flush=True)
        texts = [c['text'] for c in batch]
        vectors = embed_batch(texts)
        for chunk, vec in zip(batch, vectors):
            embedded.append({**chunk, 'embedding': vec})

    print(f"[embedder] Done. {len(embedded)} chunks embedded.")
    return embedded


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    denom = norm_a * norm_b
    return dot / denom if denom else 0.0


def similarity_sanity_check(embedded_chunks: list[dict]) -> None:
    query_chunk = next(
        (c for c in embedded_chunks if 'baggage' in c['text'].lower()),
        None,
    )
    if query_chunk is None:
        print("[sanity] No chunk containing 'baggage' found.")
        return

    print(f"\n[sanity] Query chunk  : {query_chunk['chunk_id']}")
    print(f"         Doc title    : {query_chunk['metadata']['title']}")
    print(f"         Text preview : {query_chunk['text'][:80].replace(chr(10),' ')}...")

    q_vec = query_chunk['embedding']
    scored = [
        (cosine_similarity(q_vec, c['embedding']), c)
        for c in embedded_chunks
        if c['chunk_id'] != query_chunk['chunk_id']
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    print("\n  Top 3 most similar:")
    for sim, c in scored[:3]:
        print(f"    {sim:.4f}  [{c['chunk_id']}]  {c['metadata']['title']}")

    print("\n  Bottom 3 least similar:")
    for sim, c in scored[-3:]:
        print(f"    {sim:.4f}  [{c['chunk_id']}]  {c['metadata']['title']}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

    from data.indigo_documents import DOCUMENTS
    from src.ingestion.chunker import ingest_all

    chunks = ingest_all(DOCUMENTS)
    embedded = embed_chunks(chunks)
    similarity_sanity_check(embedded)
