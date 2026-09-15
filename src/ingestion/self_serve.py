"""Self-serve document ingestion (S5-T1, extended S9-T1).

Lets an authenticated tenant add, update, or delete a policy document in
their own airline's scope without a maintainer running scripts/ingest.py by
hand. Reuses the existing chunk → embed pipeline; the only new piece is
building a single ad-hoc `doc` dict and forcing its `airline` tag to the
tenant's own airline, so a tenant can never tag a document into another
tenant's scope.

All three operations go through IndexManager so the dense (Qdrant) and
lexical (BM25) indexes stay consistent within the running process — see
src/ingestion/index_manager.py for the consistency/rollback contract and its
current limits (no cross-process persistence yet).
"""
import re
from datetime import date, datetime, timezone

from src.embedding.embedder import embed_chunks
from src.ingestion.chunker import chunk_document
from src.ingestion.index_manager import IndexManager
from src.observability.logging_config import get_logger

logger = get_logger("ingestion.self_serve")

MIN_CONTENT_CHARS = 50
MAX_CONTENT_CHARS = 50_000
_DOC_ID_PREFIX = "SELFSERVE"


class UploadValidationError(ValueError):
    pass


class OwnershipError(ValueError):
    pass


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "doc"


def _tenant_doc_prefix(tenant) -> str:
    return f"{_DOC_ID_PREFIX}-{tenant.airline.upper()}-"


def _require_owned_doc_id(tenant, doc_id: str) -> None:
    """A tenant may only update/delete self-serve documents tagged with
    their own airline — never another tenant's, and never a bundled
    (non-self-serve) document."""
    if not doc_id.startswith(_tenant_doc_prefix(tenant)):
        raise OwnershipError(f"'{doc_id}' does not belong to {tenant.airline}.")


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


def _build_chunks(doc_id: str, title: str, content: str, category: str, airline: str) -> list[dict]:
    doc = {
        "id": doc_id,
        "title": title.strip(),
        "category": category,
        "airline": airline,
        "department": "Self-Serve Upload",
        "doc_type": "policy",
        "visibility": "private",
        "last_updated": date.today().isoformat(),
        "content": content,
    }
    chunks = chunk_document(doc)
    if not chunks:
        raise UploadValidationError("Document produced no usable chunks after cleaning.")
    return chunks


def ingest_document_for_tenant(
    tenant,
    title: str,
    content: str,
    category: str,
    index_manager: IndexManager,
) -> dict:
    """Chunk, embed, and add a single new document scoped to `tenant.airline`.

    Returns a small summary dict (doc_id, chunk_count) for UI feedback.
    """
    validate_upload(title, content)

    doc_id = f"{_tenant_doc_prefix(tenant)}{_slugify(title)}-{int(datetime.now(timezone.utc).timestamp())}"
    chunks = _build_chunks(doc_id, title, content, category, tenant.airline)
    embedded = embed_chunks(chunks)
    index_manager.add_document(embedded)

    logger.info(
        "self-serve document ingested",
        tenant=tenant.tenant_id, airline=tenant.airline, doc_id=doc_id, chunk_count=len(embedded),
    )
    return {"doc_id": doc_id, "chunk_count": len(embedded)}


def update_document_for_tenant(
    tenant,
    doc_id: str,
    title: str,
    content: str,
    category: str,
    index_manager: IndexManager,
) -> dict:
    """Replace an existing self-serve document's content in place, keeping
    its doc_id. Raises OwnershipError if `doc_id` was not this tenant's own
    self-serve upload."""
    _require_owned_doc_id(tenant, doc_id)
    validate_upload(title, content)

    chunks = _build_chunks(doc_id, title, content, category, tenant.airline)
    embedded = embed_chunks(chunks)
    index_manager.update_document(doc_id, embedded)

    logger.info(
        "self-serve document updated",
        tenant=tenant.tenant_id, airline=tenant.airline, doc_id=doc_id, chunk_count=len(embedded),
    )
    return {"doc_id": doc_id, "chunk_count": len(embedded)}


def delete_document_for_tenant(tenant, doc_id: str, index_manager: IndexManager) -> None:
    """Remove a self-serve document from both indexes. Raises OwnershipError
    if `doc_id` was not this tenant's own self-serve upload."""
    _require_owned_doc_id(tenant, doc_id)
    index_manager.delete_document(doc_id)
    logger.info(
        "self-serve document deleted",
        tenant=tenant.tenant_id, airline=tenant.airline, doc_id=doc_id,
    )
