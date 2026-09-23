import os
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    IsEmptyCondition,
    PayloadField,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.embedding.embedder import EMBEDDING_DIM
from src.observability.logging_config import get_logger

logger = get_logger("embedding.vector_store")

_BATCH_SIZE = 100
# Approval is explicit for private uploads; only published legacy corpus
# points may omit status. Unknown status values are never searchable.


class QdrantVectorStore:
    def __init__(self, collection_name: str | None = None, *, create_if_missing: bool = True) -> None:
        collection_name = collection_name or os.environ.get("QDRANT_COLLECTION", "airline_kb")
        url = os.environ.get("QDRANT_URL")
        api_key = os.environ.get("QDRANT_API_KEY")
        if not url:
            raise EnvironmentError("QDRANT_URL env var not set.")
        if not api_key:
            raise EnvironmentError("QDRANT_API_KEY env var not set.")

        self.collection_name = collection_name
        self.client = QdrantClient(url=url, api_key=api_key, timeout=10, check_compatibility=False)

        try:
            existing = {c.name for c in self.client.get_collections().collections}
            if collection_name not in existing:
                if not create_if_missing:
                    raise RuntimeError("Collection unavailable; follow docs/RECOVERY.md")
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )
                logger.info("created collection", collection=collection_name, dim=EMBEDDING_DIM)
            else:
                info = self.client.get_collection(collection_name)
                stored_dim = info.config.params.vectors.size
                if stored_dim != EMBEDDING_DIM:
                    raise RuntimeError(
                        f"Collection '{collection_name}' has dim={stored_dim}, "
                        f"expected {EMBEDDING_DIM}. Check collection configuration before recovery."
                    )
                count = info.points_count
                logger.info("connected to collection", collection=collection_name, dim=stored_dim, points=count)
            if create_if_missing:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name="category",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name="airline",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=collection_name, field_name="visibility",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=collection_name, field_name="source_doc_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            # "status" is filtered on every query() call (see
            # _UNSEARCHABLE_STATUSES below) regardless of create_if_missing,
            # including against collections that already existed before this
            # field was introduced — unlike the indexes above, this one must
            # be ensured unconditionally, or filtering 400s on a strict-mode
            # Qdrant deployment that requires an index for every filtered
            # field. create_payload_index is idempotent; Qdrant no-ops (or
            # error-tolerates) a duplicate call for an existing index.
            try:
                self.client.create_payload_index(
                    collection_name=collection_name, field_name="status",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                logger.warning("could not ensure 'status' payload index", collection=collection_name)
        except Exception:
            self.client.close()
            raise


    def upsert(self, chunks: list[dict]) -> None:
        total = len(chunks)
        upserted = 0
        for batch_start in range(0, total, _BATCH_SIZE):
            batch = chunks[batch_start : batch_start + _BATCH_SIZE]
            points = []
            for chunk in batch:
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"]))
                payload = {
                    "text": chunk["text"],
                    "chunk_id": chunk["chunk_id"],
                    "chunk_index": chunk.get("chunk_index"),
                    **chunk["metadata"],
                }
                points.append(
                    PointStruct(id=point_id, vector=chunk["embedding"], payload=payload)
                )
            self.client.upsert(collection_name=self.collection_name, points=points)
            upserted += len(batch)
            print(f"[vector_store] Upserted {upserted}/{total} points.")

    def query(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filters: dict | None = None,
        airline_filter: list[str] | None = None,
    ) -> list[dict]:
        must = []
        if filters:
            must.extend(
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            )
        if airline_filter:
            must.append(FieldCondition(key="airline", match=MatchAny(any=airline_filter)))
        if not airline_filter:
            # Every unscoped path, including public All Airlines and confidence
            # searches, must fail closed for legacy/unknown/private payloads.
            must.append(FieldCondition(key="visibility", match=MatchValue(value="public")))
        else:
            # DGCA is shared only when published. Private airline documents are
            # available only through an explicitly scoped trusted tenant path.
            owned = [airline for airline in airline_filter if airline != "dgca"]
            allowed = [FieldCondition(key="visibility", match=MatchValue(value="public"))]
            if owned:
                allowed.append(FieldCondition(key="airline", match=MatchAny(any=owned)))
            must.append(Filter(should=allowed))
        # Only explicit approval can publish private uploads. Legacy bundled
        # public policies have no status; unknown status values fail closed.
        must.append(Filter(should=[
            FieldCondition(key="status", match=MatchValue(value="approved")),
            Filter(must=[
                IsEmptyCondition(is_empty=PayloadField(key="status")),
                FieldCondition(key="visibility", match=MatchValue(value="public")),
            ]),
        ]))
        qdrant_filter = Filter(must=must)

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        hits = []
        for r in response.points:
            payload = r.payload or {}
            hits.append(
                {
                    "chunk_id": payload.get("chunk_id", ""),
                    "score": r.score,
                    "text": payload.get("text", ""),
                    "metadata": {
                        k: v
                        for k, v in payload.items()
                        if k not in ("text", "chunk_id")
                    },
                }
            )
        return hits

    def query_for_tenant(
        self,
        tenant,
        query_vector: list[float],
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        """Tenant-scoped query — always filters to the tenant's airline (plus
        shared DGCA regulatory docs). Unlike `query()`, there is no way to
        pass `airline_filter=None` here: a tenant can never see another
        tenant's chunks, even if a caller forgets to scope the request.
        """
        return self.query(
            query_vector, top_k=top_k, filters=filters,
            airline_filter=[tenant.airline, "dgca"],
        )

    def recreate_collection(self) -> None:
        self.client.delete_collection(self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="category",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="airline",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection_name, field_name="visibility",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection_name, field_name="source_doc_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection_name, field_name="status",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        print(
            f"[vector_store] Recreated collection '{self.collection_name}' "
            f"(dim={EMBEDDING_DIM})."
        )

    def chunks_for_document(self, doc_id: str) -> list[dict]:
        """Read the durable dense version for update cleanup and compensation."""
        chunks = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=[FieldCondition(key="source_doc_id", match=MatchValue(value=doc_id))]),
                with_payload=True, with_vectors=True, limit=100, offset=offset,
            )
            for point in points:
                payload = point.payload or {}
                chunks.append({
                    "chunk_id": payload["chunk_id"], "doc_id": doc_id,
                    "text": payload["text"], "embedding": point.vector,
                    "metadata": {k: v for k, v in payload.items() if k not in ("text", "chunk_id")},
                })
            if offset is None:
                return chunks

    def delete_by_doc_id(self, doc_id: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="source_doc_id", match=MatchValue(value=doc_id))])
            ),
        )
        print(f"[vector_store] Deleted all points for source_doc_id='{doc_id}'.")

    def delete_by_chunk_ids(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="chunk_id", match=MatchAny(any=chunk_ids))])
            ),
        )
        print(f"[vector_store] Deleted {len(chunk_ids)} point(s) by chunk_id.")

    def set_status_by_doc_id(self, doc_id: str, status: str, *, superseded_by: str | None = None) -> None:
        """Patch the `status` payload field on every chunk for `doc_id`
        without touching vectors or any other payload field — used for
        approve/reject/supersede, which are metadata transitions, not
        content changes."""
        payload = {"status": status}
        if superseded_by is not None:
            payload["superseded_by"] = superseded_by
        self.client.set_payload(
            collection_name=self.collection_name,
            payload=payload,
            points=FilterSelector(
                filter=Filter(must=[FieldCondition(key="source_doc_id", match=MatchValue(value=doc_id))])
            ),
        )

    def delete_by_airline(self, airline: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="airline", match=MatchValue(value=airline))])
            ),
        )
        print(f"[vector_store] Deleted all points for airline='{airline}'.")

    def stats(self) -> dict:
        info = self.client.get_collection(self.collection_name)
        return {"total_vectors": info.points_count, "backend": "qdrant"}
