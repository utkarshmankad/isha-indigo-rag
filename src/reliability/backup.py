"""Portable, checksummed backup of the single dense-vector ISHA collection.

Stop ingestion during export. Snapshots provide a separate server-native recovery
path; portable exports also allow restore tests with Qdrant's local backend.
"""
import hashlib
import json
from pathlib import Path

from qdrant_client.models import PointStruct, VectorParams


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def export_collection(client, collection: str, directory: Path, documents: list[dict]) -> dict:
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    info = client.get_collection(collection)
    if not isinstance(info.config.params.vectors, VectorParams):
        raise ValueError('Only the ISHA single dense-vector collection is supported')
    offset = None
    count = 0
    with (directory / 'points.jsonl').open('w') as stream:
        while True:
            points, offset = client.scroll(collection, limit=100, offset=offset,
                                           with_payload=True, with_vectors=True)
            for point in points:
                stream.write(PointStruct(id=point.id, vector=point.vector, payload=point.payload).model_dump_json() + '\n')
                count += 1
            if offset is None:
                break
    after = client.count(collection, exact=True).count
    if count != after or count != info.points_count:
        raise RuntimeError('Collection changed during export; pause ingestion and retry in a new directory')
    (directory / 'documents.json').write_text(json.dumps(documents, ensure_ascii=False, indent=2))
    config = {'vectors': info.config.params.vectors.model_dump(mode='json'),
              'payload_indexes': {key: value.data_type.value for key, value in info.payload_schema.items()}}
    (directory / 'config.json').write_text(json.dumps(config, indent=2))
    manifest = {'format': 1, 'collection': collection, 'points': count,
                'files': {name: digest(directory / name)
                          for name in ('points.jsonl', 'documents.json', 'config.json')}}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return manifest


def verify_export(directory: Path) -> dict:
    manifest = json.loads((directory / 'manifest.json').read_text())
    names = {'points.jsonl', 'documents.json', 'config.json'}
    if manifest.get('format') != 1 or set(manifest.get('files', {})) != names:
        raise ValueError('Unsupported backup manifest')
    for name in names:
        if digest(directory / name) != manifest['files'][name]:
            raise ValueError(f'Checksum mismatch: {name}')
    return manifest


def restore_collection(client, directory: Path, target: str) -> int:
    manifest = verify_export(directory)
    if client.collection_exists(target):
        raise ValueError('Target collection already exists; choose a new recovery collection')
    config = json.loads((directory / 'config.json').read_text())
    # Validate every record before creating a target, including duplicates/counts.
    ids = set()
    with (directory / 'points.jsonl').open() as stream:
        for line in stream:
            point = PointStruct.model_validate_json(line)
            if point.id in ids:
                raise ValueError('Duplicate point ID in backup')
            ids.add(point.id)
    if len(ids) != manifest['points']:
        raise ValueError('Point count differs from manifest')
    client.create_collection(target, vectors_config=VectorParams.model_validate(config['vectors']))
    for name, schema in config['payload_indexes'].items():
        client.create_payload_index(target, field_name=name, field_schema=schema, wait=True)
    batch = []
    with (directory / 'points.jsonl').open() as stream:
        for line in stream:
            batch.append(PointStruct.model_validate_json(line))
            if len(batch) == 100:
                client.upsert(target, points=batch, wait=True)
                batch = []
    if batch:
        client.upsert(target, points=batch, wait=True)
    actual = client.count(target, exact=True).count
    if actual != manifest['points']:
        raise RuntimeError('Restore count mismatch; do not switch application traffic')
    return actual
