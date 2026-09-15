"""Canonical document store, original source preservation, version history,
approval workflow and supersession (Weeks 3-4, items 1 and 3).

Chunking is lossy: `chunk_document` splits and overlaps text for retrieval,
and nothing before this kept the original, un-chunked document text or its
provenance (an authoritative source URL, an effective date, a verified-as-
current date) as a first-class record. This module adds exactly that, as one
current record per doc_id, plus:

- **Version history**: every overwritten record is archived, not discarded,
  so `list_versions(doc_id)` can show what a document looked like before an
  update.
- **Approval status**: every record has a `status` of `pending`, `approved`,
  `rejected`, or `superseded`. New uploads and content updates start
  `pending`; only an explicit approval (see `IndexManager.set_status` and
  `self_serve.approve_document_for_tenant`) makes a document searchable —
  see `docs/INDEX-CONSISTENCY.md` for how that status feeds retrieval
  filtering.
- **Dedup**: `find_by_content_hash` lets a caller check, before ingesting,
  whether the same airline already has a non-rejected document with
  identical content.
- **Supersession**: `supersedes` / `superseded_by` link an old and new
  doc_id when one is meant to replace the other in search results, without
  deleting the old record's history.

Scope: covers self-serve uploads, the only place documents are created or
changed at runtime. The bundled static corpus (`data/*.py`) already has a
source of truth — the files themselves, in git — so this store does not
retroactively index them; auditing them for staleness is separate Weeks 3-4
scope (see `scripts/audit_bundled_corpus.py`).

No Postgres is available (Qdrant-only environment, per the reliability
roadmap's stated constraint), so records live in their own Qdrant
collection, one point per doc_id, addressed by a deterministic point id
derived from doc_id, plus a second collection for archived versions.
Vectors are unused (a fixed 1-dim placeholder) — neither collection is ever
searched by similarity, only fetched/filtered by doc_id, airline, or
content_hash.
"""
import hashlib
import os
import uuid
from datetime import datetime, timezone

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.observability.logging_config import get_logger

logger = get_logger("documents.document_store")

_PLACEHOLDER_VECTOR = [0.0]
VALID_STATUSES = ("pending", "approved", "rejected", "superseded")


def _point_id(doc_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"document-record:{doc_id}"))


def _version_point_id(doc_id: str, version: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"document-version:{doc_id}:{version}"))


def hash_content(title: str, content: str) -> str:
    """Stable fingerprint of a document's meaningful text, for dedup. Title
    is included so an identical body under a clearly different title isn't
    flagged — only near-identical uploads are."""
    normalized = f"{title.strip().lower()}\n{content.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class DocumentStore:
    """One canonical current record per doc_id, plus an append-only archive
    of prior versions."""

    def __init__(self, client: QdrantClient, collection_name: str | None = None) -> None:
        base = os.environ.get("QDRANT_COLLECTION", "airline_kb")
        self.collection_name = collection_name or f"{base}_documents"
        self.history_collection_name = f"{self.collection_name}_history"
        self.client = client

        existing = {c.name for c in self.client.get_collections().collections}
        for name in (self.collection_name, self.history_collection_name):
            if name in existing:
                continue
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=len(_PLACEHOLDER_VECTOR), distance=Distance.COSINE),
            )
            self.client.create_payload_index(
                collection_name=name, field_name="doc_id", field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=name, field_name="airline", field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=name, field_name="content_hash", field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("created document collection", collection=name)

    def put(self, record: dict) -> None:
        """Insert or overwrite the canonical record for `record['doc_id']`.
        If a record already exists for that doc_id, it is archived into the
        version-history collection first — this is a full content
        replacement (a new version), not a metadata patch; use `patch` for
        status/supersession-only changes that shouldn't create a new
        history entry."""
        doc_id = record["doc_id"]
        existing = self.get(doc_id)
        if existing is not None:
            self.client.upsert(
                collection_name=self.history_collection_name,
                points=[PointStruct(
                    id=_version_point_id(doc_id, existing["version"]),
                    vector=_PLACEHOLDER_VECTOR, payload=existing,
                )],
            )
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=_point_id(doc_id), vector=_PLACEHOLDER_VECTOR, payload=record)],
        )

    def patch(self, doc_id: str, **fields) -> dict | None:
        """Update fields on the current record in place — no version bump,
        no history archive. Used for status transitions (approve/reject/
        supersede) that don't change the document's content."""
        record = self.get(doc_id)
        if record is None:
            return None
        record = {**record, **fields}
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=_point_id(doc_id), vector=_PLACEHOLDER_VECTOR, payload=record)],
        )
        return record

    def get(self, doc_id: str) -> dict | None:
        points = self.client.retrieve(
            collection_name=self.collection_name, ids=[_point_id(doc_id)], with_payload=True,
        )
        return points[0].payload if points else None

    def delete(self, doc_id: str) -> None:
        self.client.delete(
            collection_name=self.collection_name, points_selector=[_point_id(doc_id)],
        )

    def list_for_airline(self, airline: str, *, status: str | None = None) -> list[dict]:
        must = [FieldCondition(key="airline", match=MatchValue(value=airline))]
        if status:
            must.append(FieldCondition(key="status", match=MatchValue(value=status)))
        records: list[dict] = []
        next_offset = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=must),
                with_payload=True,
                limit=100,
                offset=next_offset,
            )
            records.extend(p.payload for p in points)
            if next_offset is None:
                break
        return records

    def find_by_content_hash(self, airline: str, content_hash: str) -> dict | None:
        """First non-rejected, non-superseded record for this airline with
        matching content, or None. Used to warn on/block near-duplicate
        uploads."""
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(must=[
                FieldCondition(key="airline", match=MatchValue(value=airline)),
                FieldCondition(key="content_hash", match=MatchValue(value=content_hash)),
            ]),
            with_payload=True,
            limit=10,
        )
        for point in points:
            if point.payload.get("status") not in ("rejected", "superseded"):
                return point.payload
        return None

    def list_versions(self, doc_id: str) -> list[dict]:
        """All archived versions plus the current record, oldest first."""
        versions: list[dict] = []
        next_offset = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.history_collection_name,
                scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
                with_payload=True,
                limit=100,
                offset=next_offset,
            )
            versions.extend(p.payload for p in points)
            if next_offset is None:
                break
        current = self.get(doc_id)
        if current is not None:
            versions.append(current)
        return sorted(versions, key=lambda r: r["version"])


def build_record(
    *,
    doc_id: str,
    title: str,
    category: str,
    airline: str,
    original_content: str,
    uploaded_by: str,
    source_url: str | None = None,
    effective_date: str | None = None,
    verified_date: str | None = None,
    supersedes: str | None = None,
    previous: dict | None = None,
) -> dict:
    """Build a canonical record dict, carrying `created_at` and incrementing
    `version` forward from `previous` when this is an update. New/updated
    content always starts `pending` — content changes require a fresh
    approval, even if the prior version was approved."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "doc_id": doc_id,
        "title": title,
        "category": category,
        "airline": airline,
        "original_content": original_content,
        "uploaded_by": uploaded_by,
        "source_url": source_url,
        "effective_date": effective_date,
        "verified_date": verified_date,
        "content_hash": hash_content(title, original_content),
        "status": "pending",
        "supersedes": supersedes,
        "superseded_by": None,
        "version": (previous["version"] + 1) if previous else 1,
        "created_at": previous["created_at"] if previous else now,
        "updated_at": now,
    }
