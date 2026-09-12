import uuid
import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from src.reliability.backup import export_collection, restore_collection, verify_export


def test_backup_restores_vectors_and_uploaded_text_without_overwriting(tmp_path):
    source = QdrantClient(':memory:')
    source.create_collection('kb', vectors_config=VectorParams(size=3, distance=Distance.COSINE))
    point_id = str(uuid.uuid4())
    source.upsert('kb', points=[PointStruct(id=point_id, vector=[1., 0., 0.],
                  payload={'text': 'Uploaded policy not in bundled documents', 'airline': 'indigo'})])
    backup = tmp_path / 'backup'
    export_collection(source, 'kb', backup, [{'id': 'bundled-source'}])
    target = QdrantClient(':memory:')
    assert restore_collection(target, backup, 'recovered') == 1
    restored = target.retrieve('recovered', ids=[point_id], with_vectors=True)[0]
    assert restored.vector == [1., 0., 0.]
    assert restored.payload['text'] == 'Uploaded policy not in bundled documents'
    with pytest.raises(ValueError, match='already exists'):
        restore_collection(target, backup, 'recovered')
    source.close(); target.close()


def test_corruption_is_rejected_before_creating_collection(tmp_path):
    source = QdrantClient(':memory:')
    source.create_collection('kb', vectors_config=VectorParams(size=3, distance=Distance.COSINE))
    backup = tmp_path / 'backup'
    export_collection(source, 'kb', backup, [])
    (backup / 'points.jsonl').write_text('corrupt')
    target = QdrantClient(':memory:')
    with pytest.raises(ValueError, match='Checksum'):
        restore_collection(target, backup, 'recovered')
    assert not target.collection_exists('recovered')
    source.close(); target.close()
