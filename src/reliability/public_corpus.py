"""Publish only unchanged, repository-bundled points in a legacy collection."""
import uuid


def migrate_public_corpus(client, collection: str, chunks: list[dict], *, apply=False) -> dict:
    candidates = []
    for start in range(0, len(chunks), 100):
        batch = chunks[start:start + 100]
        expected = {str(uuid.uuid5(uuid.NAMESPACE_DNS, c['chunk_id'])): c for c in batch}
        points = client.retrieve(collection, ids=list(expected), with_payload=True, with_vectors=False)
        for point in points:
            chunk = expected.get(str(point.id))
            payload = point.payload or {}
            if (chunk and payload.get('visibility') is None
                    and payload.get('text') == chunk['text']
                    and payload.get('chunk_id') == chunk['chunk_id']
                    and payload.get('source_doc_id') == chunk['metadata']['source_doc_id']
                    and payload.get('airline') == chunk['metadata']['airline']):
                candidates.append(point.id)
    if apply:
        from qdrant_client.models import PayloadSchemaType
        client.create_payload_index(collection, field_name='visibility', field_schema=PayloadSchemaType.KEYWORD, wait=True)
        for start in range(0, len(candidates), 100):
            client.set_payload(collection, payload={'visibility': 'public'},
                               points=candidates[start:start + 100], wait=True)
    return {'matched_legacy_points': len(candidates), 'applied': apply}
