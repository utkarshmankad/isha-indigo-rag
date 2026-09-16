"""Self-serve document ingestion (S5-T1, extended S9-T1 and Weeks 3-4 items 1, 3).

Lets an authenticated tenant add, update, delete, approve, or reject a
policy document in their own airline's scope without a maintainer running
scripts/ingest.py by hand. Reuses the existing chunk → embed pipeline; the
only new piece is building a single ad-hoc `doc` dict and forcing its
`airline` tag to the tenant's own airline, so a tenant can never tag a
document into another tenant's scope.

All operations go through IndexManager so the canonical record, the dense
(Qdrant) index and the lexical (BM25) index stay consistent within the
running process — see src/ingestion/index_manager.py for the
consistency/rollback contract and its current limits, and
src/documents/document_store.py for what the canonical record preserves
(original un-chunked content, source URL, effective/verified dates, version
history, approval status, supersession).

Approval workflow: a new upload or content update always starts `pending`
and is excluded from retrieval (see docs/INDEX-CONSISTENCY.md) until an
admin calls `approve_document_for_tenant`. This means an upload is fully
indexed (dense + lexical + canonical record) immediately, so an admin can
review exactly what was ingested, but end users won't see it in answers
until it's approved.

Dedup: `ingest_document_for_tenant` checks the canonical store for an
existing non-rejected/non-superseded document with identical
(title, content) for the same airline before creating a new one, and raises
`DuplicateDocumentError` unless the caller passes `force=True`.
"""
import re
from datetime import date, datetime, timezone

from src.documents.document_store import DocumentStore, build_record, hash_content
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


class DuplicateDocumentError(ValueError):
    def __init__(self, existing_doc_id: str):
        self.existing_doc_id = existing_doc_id
        super().__init__(
            f"An existing document '{existing_doc_id}' already has identical content. "
            "Pass force=True to upload anyway."
        )


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "doc"


def _tenant_doc_prefix(tenant) -> str:
    return f"{_DOC_ID_PREFIX}-{tenant.airline.upper()}-"


def _require_owned_doc_id(tenant, doc_id: str) -> None:
    """A tenant may only update/delete/approve/reject self-serve documents
    tagged with their own airline — never another tenant's, and never a
    bundled (non-self-serve) document."""
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
        # New uploads and content updates always require approval — see
        # module docstring and docs/INDEX-CONSISTENCY.md.
        "status": "pending",
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
    document_store: DocumentStore | None = None,
    *,
    source_url: str | None = None,
    effective_date: str | None = None,
    verified_date: str | None = None,
    supersedes: str | None = None,
    force: bool = False,
) -> dict:
    """Chunk, embed, and add a single new document scoped to `tenant.airline`.
    Starts in `pending` status — see module docstring.

    If `document_store` is given and an existing non-rejected/non-superseded
    document for this airline has identical (title, content), raises
    `DuplicateDocumentError` unless `force=True`.

    If `supersedes` is given, that doc_id (which must be this tenant's own
    self-serve document) is marked `superseded` and linked to the new
    doc_id once the new document is committed.

    Returns a small summary dict (doc_id, chunk_count) for UI feedback.
    """
    validate_upload(title, content)
    if supersedes is not None:
        _require_owned_doc_id(tenant, supersedes)

    if document_store and not force:
        content_hash = hash_content(title, content)
        duplicate = document_store.find_by_content_hash(tenant.airline, content_hash)
        if duplicate is not None:
            raise DuplicateDocumentError(duplicate["doc_id"])

    doc_id = f"{_tenant_doc_prefix(tenant)}{_slugify(title)}-{int(datetime.now(timezone.utc).timestamp())}"
    chunks = _build_chunks(doc_id, title, content, category, tenant.airline)
    embedded = embed_chunks(chunks)
    record = build_record(
        doc_id=doc_id, title=title.strip(), category=category, airline=tenant.airline,
        original_content=content, uploaded_by=tenant.tenant_id,
        source_url=source_url, effective_date=effective_date, verified_date=verified_date,
        supersedes=supersedes,
    )
    index_manager.add_document(record, embedded)

    if supersedes is not None:
        index_manager.set_status(supersedes, "superseded", superseded_by=doc_id)

    logger.info(
        "self-serve document ingested",
        tenant=tenant.tenant_id, airline=tenant.airline, doc_id=doc_id, chunk_count=len(embedded),
        supersedes=supersedes,
    )
    return {"doc_id": doc_id, "chunk_count": len(embedded)}


def update_document_for_tenant(
    tenant,
    doc_id: str,
    title: str,
    content: str,
    category: str,
    index_manager: IndexManager,
    document_store: DocumentStore | None = None,
    *,
    source_url: str | None = None,
    effective_date: str | None = None,
    verified_date: str | None = None,
) -> dict:
    """Replace an existing self-serve document's content in place, keeping
    its doc_id and its version history, but resetting status to `pending`
    (a content change requires fresh approval). Raises OwnershipError if
    `doc_id` was not this tenant's own self-serve upload."""
    _require_owned_doc_id(tenant, doc_id)
    validate_upload(title, content)

    chunks = _build_chunks(doc_id, title, content, category, tenant.airline)
    embedded = embed_chunks(chunks)
    previous = document_store.get(doc_id) if document_store else None
    record = build_record(
        doc_id=doc_id, title=title.strip(), category=category, airline=tenant.airline,
        original_content=content, uploaded_by=tenant.tenant_id,
        source_url=source_url, effective_date=effective_date, verified_date=verified_date,
        previous=previous,
    )
    index_manager.update_document(doc_id, record, embedded)

    logger.info(
        "self-serve document updated",
        tenant=tenant.tenant_id, airline=tenant.airline, doc_id=doc_id, chunk_count=len(embedded),
    )
    return {"doc_id": doc_id, "chunk_count": len(embedded)}


def delete_document_for_tenant(tenant, doc_id: str, index_manager: IndexManager) -> None:
    """Remove a self-serve document from both indexes and its canonical
    record. Raises OwnershipError if `doc_id` was not this tenant's own
    self-serve upload."""
    _require_owned_doc_id(tenant, doc_id)
    index_manager.delete_document(doc_id)
    logger.info(
        "self-serve document deleted",
        tenant=tenant.tenant_id, airline=tenant.airline, doc_id=doc_id,
    )


def get_version_history_for_tenant(tenant, doc_id: str, document_store: DocumentStore) -> list[dict]:
    """Version history, including full `original_content`, for one of this
    tenant's own self-serve documents. Raises OwnershipError if `doc_id`
    was not this tenant's own self-serve upload — this record contains the
    document's full text and provenance, so unlike a doc_id-only operation,
    leaking it to another tenant is a content-disclosure issue, not just an
    unauthorized-write issue."""
    _require_owned_doc_id(tenant, doc_id)
    return document_store.list_versions(doc_id)


def approve_document_for_tenant(tenant, doc_id: str, index_manager: IndexManager) -> None:
    """Make a pending self-serve document searchable. Raises OwnershipError
    if `doc_id` was not this tenant's own self-serve upload."""
    _require_owned_doc_id(tenant, doc_id)
    index_manager.set_status(doc_id, "approved")
    logger.info(
        "self-serve document approved",
        tenant=tenant.tenant_id, airline=tenant.airline, doc_id=doc_id,
    )


def reject_document_for_tenant(tenant, doc_id: str, index_manager: IndexManager) -> None:
    """Mark a self-serve document rejected — kept in the canonical record
    and version history, but permanently excluded from retrieval unless
    re-approved. Raises OwnershipError if `doc_id` was not this tenant's own
    self-serve upload."""
    _require_owned_doc_id(tenant, doc_id)
    index_manager.set_status(doc_id, "rejected")
    logger.info(
        "self-serve document rejected",
        tenant=tenant.tenant_id, airline=tenant.airline, doc_id=doc_id,
    )
