"""Small authenticated reads for readiness monitoring; never embeds or generates."""
import os
import time


def probe_qdrant(client_factory=None) -> dict:
    from qdrant_client import QdrantClient
    factory = client_factory or QdrantClient
    url = os.environ.get('QDRANT_URL')
    key = os.environ.get('QDRANT_API_KEY')
    collection = os.environ.get('QDRANT_COLLECTION', 'airline_kb')
    if not url or not key:
        return {'status': 'error', 'reason': 'missing_configuration'}
    start = time.monotonic()
    client = None
    try:
        client = factory(url=url, api_key=key, timeout=10, check_compatibility=False)
        info = client.get_collection(collection)
        if str(info.status) not in ('green', 'yellow'):
            return {'status': 'error', 'reason': 'collection_unhealthy'}
        points, _ = client.scroll(collection, limit=1, with_payload=False, with_vectors=False)
        if not points:
            return {'status': 'error', 'reason': 'collection_empty'}
        return {'status': 'ok', 'latency_ms': round((time.monotonic() - start) * 1000)}
    except Exception:
        # Do not include URLs, credentials, response bodies, or policy content.
        return {'status': 'error', 'reason': 'collection_unavailable'}
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
