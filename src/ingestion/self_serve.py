"""Self-serve document ingestion (S5-T1).

Lets an authenticated tenant add a policy document to their own airline's
scope without a maintainer running scripts/ingest.py by hand. Reuses the
existing chunk → embed → upsert pipeline; the only new piece is building a
single ad-hoc `doc` dict and forcing its `airline` tag to the tenant's own
airline, so a tenant can never tag a document into another tenant's scope.

Note: this only upserts into Qdrant. The BM25 keyword index is built from
the static `data/*.py` document set (see hybrid_search.BM25Index) and is
unaware of self-serve uploads until someone re-runs ingestion against an
updated static set — semantic (vector) search picks up new uploads
immediately, exact-keyword matching does not.
"""
import re
from datetime import date, datetime, timezone

from src.embedding.embedder import embed_chunks
from src.embedding.vector_store import QdrantVectorStore
from src.ingestion.chunker import chunk_document
from src.observability.logging_config import get_logger

logger = get_logger("ingestion.self_serve")

MIN_CONTENT_CHARS = 50
MAX_CONTENT_CHARS = 50_000


class UploadValidationError(ValueError):
    pass


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "doc"


def validate_upload(title: str, content: str) -> None:
    if not title or not title.strip():
        raise UploadValidationError("Title is required.")
    if not content or not content.strip():
        raise UploadValidationError("Document content is required.")
    if len(content) < MIN_CONTENT_CHARS:
        raise UploadValidationError(
            f"Document too short ({len(content)} chars) — minimum {MIN_CONTENT_CHARS}."
        )
    if len(content) > MAX_CONTENT_CHARS:
        raise UploadValidationError(
            f"Document too long ({len(content)} chars) — maximum {MAX_CONTENT_CHARS}."
        )


def ingest_document_for_tenant(
    tenant,
    title: str,
    content: str,
    category: str,
    vector_store: QdrantVectorStore,
) -> dict:
    """Chunk, embed, and upsert a single document scoped to `tenant.airline`.

    Returns a small summary dict (doc_id, chunk_count) for UI feedback.
    """
    validate_upload(title, content)

    today = date.today().isoformat()
    doc_id = f"SELFSERVE-{tenant.airline.upper()}-{_slugify(title)}-{int(datetime.now(timezone.utc).timestamp())}"
    doc = {
        "id": doc_id,
        "title": title.strip(),
        "category": category,
        "airline": tenant.airline,
        "department": "Self-Serve Upload",
        "doc_type": "policy",
        "last_updated": today,
        "content": content,
    }

    chunks = chunk_document(doc)
    if not chunks:
        raise UploadValidationError("Document produced no usable chunks after cleaning.")

    embedded = embed_chunks(chunks)
    vector_store.upsert(embedded)

    logger.info(
        "self-serve document ingested",
        tenant=tenant.tenant_id, airline=tenant.airline, doc_id=doc_id, chunk_count=len(embedded),
    )
    return {"doc_id": doc_id, "chunk_count": len(embedded)}
