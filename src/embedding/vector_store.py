import os
import uuid

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

from src.embedding.embedder import EMBEDDING_DIM

_BATCH_SIZE = 100


class QdrantVectorStore:
    def __init__(self, collection_name: str = "indigo_kb") -> None:
        url = os.environ.get("QDRANT_URL")
        api_key = os.environ.get("QDRANT_API_KEY")
        if not url:
            raise EnvironmentError("QDRANT_URL env var not set.")
        if not api_key:
            raise EnvironmentError("QDRANT_API_KEY env var not set.")

        self.collection_name = collection_name
        self.client = QdrantClient(url=url, api_key=api_key)

        existing = {c.name for c in self.client.get_collections().collections}
        if collection_name not in existing:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
            print(f"[vector_store] Created collection '{collection_name}' (dim={EMBEDDING_DIM}).")
        else:
            info = self.client.get_collection(collection_name)
            stored_dim = info.config.params.vectors.size
            if stored_dim != EMBEDDING_DIM:
                raise RuntimeError(
                    f"Collection '{collection_name}' has dim={stored_dim}, "
                    f"expected {EMBEDDING_DIM}. Run ingest.py --reset to rebuild."
                )
            count = info.points_count
            print(
                f"[vector_store] Connected to '{collection_name}' "
                f"(dim={stored_dim}, {count} points)."
            )
        self.client.create_payload_index(
            collection_name=collection_name,
            field_name="category",
            field_schema=PayloadSchemaType.KEYWORD,
        )

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
    ) -> list[dict]:
        qdrant_filter = None
        if filters:
            must = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
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

    def recreate_collection(self) -> None:
        self.client.delete_collection(self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        print(
            f"[vector_store] Recreated collection '{self.collection_name}' "
            f"(dim={EMBEDDING_DIM})."
        )

    def stats(self) -> dict:
        info = self.client.get_collection(self.collection_name)
        return {"total_vectors": info.points_count, "backend": "qdrant"}
