"""Canonical document store and original-source preservation (Weeks 3-4, item 1).

Chunking is lossy: `chunk_document` splits and overlaps text for retrieval,
and nothing before this kept the original, un-chunked document text or its
provenance (an authoritative source URL, an effective date, a verified-as-
current date) as a first-class record. This module adds exactly that, as one
record per doc_id.

Scope: covers self-serve uploads, the only place documents are created or
changed at runtime. The bundled static corpus (`data/*.py`) already has a
source of truth — the files themselves, in git — so this store does not
retroactively index them; doing so, plus auditing them for staleness, is
separate Weeks 3-4 scope (authoritative URLs/dates on the bundled corpus)
that has not been started.

No Postgres is available (Qdrant-only environment, per the reliability
roadmap's stated constraint), so records live in their own Qdrant
collection, one point per doc_id, addressed by a deterministic point id
derived from doc_id. Vectors are unused (a fixed 1-dim placeholder) —
this collection is never searched by similarity, only fetched/filtered by
doc_id or airline.

This is a record store, not a version history: an update overwrites the
previous record in place (bumping `version` and `updated_at`) rather than
keeping prior revisions queryable. Full version history and supersession
tracking is separate, larger, not-yet-authorized scope (Weeks 3-4 item 3).
"""
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


def _point_id(doc_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"document-record:{doc_id}"))


class DocumentStore:
    """One canonical record per doc_id: original content plus provenance
    metadata (source_url, effective_date, verified_date), independent of how
    that content was later chunked for retrieval."""

    def __init__(self, client: QdrantClient, collection_name: str | None = None) -> None:
        base = os.environ.get("QDRANT_COLLECTION", "airline_kb")
        self.collection_name = collection_name or f"{base}_documents"
        self.client = client

        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=len(_PLACEHOLDER_VECTOR), distance=Distance.COSINE),
            )
            self.client.create_payload_index(
                collection_name=self.collection_name, field_name="doc_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name, field_name="airline",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("created document-record collection", collection=self.collection_name)

    def put(self, record: dict) -> None:
        """Insert or overwrite the canonical record for `record['doc_id']`."""
        doc_id = record["doc_id"]
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=_point_id(doc_id), vector=_PLACEHOLDER_VECTOR, payload=record)],
        )

    def get(self, doc_id: str) -> dict | None:
        points = self.client.retrieve(
            collection_name=self.collection_name, ids=[_point_id(doc_id)], with_payload=True,
        )
        return points[0].payload if points else None

    def delete(self, doc_id: str) -> None:
        self.client.delete(
            collection_name=self.collection_name, points_selector=[_point_id(doc_id)],
        )

    def list_for_airline(self, airline: str) -> list[dict]:
        records: list[dict] = []
        next_offset = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=[FieldCondition(key="airline", match=MatchValue(value=airline))]),
                with_payload=True,
                limit=100,
                offset=next_offset,
            )
            records.extend(p.payload for p in points)
            if next_offset is None:
                break
        return records


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
    previous: dict | None = None,
) -> dict:
    """Build a canonical record dict, carrying `created_at` and incrementing
    `version` forward from `previous` when this is an update."""
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
        "version": (previous["version"] + 1) if previous else 1,
        "created_at": previous["created_at"] if previous else now,
        "updated_at": now,
    }
