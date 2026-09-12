import uuid
from unittest.mock import MagicMock,patch
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct,VectorParams,Distance
from src.embedding.vector_store import QdrantVectorStore
from src.retrieval.hybrid_search import BM25Index,hybrid_search
from src.reliability.public_corpus import migrate_public_corpus
from src.tenancy.registry import TenantConfig


def test_public_search_excludes_private_legacy_and_other_airline_uploads():
    store=QdrantVectorStore.__new__(QdrantVectorStore)
    store.client=QdrantClient(':memory:');store.collection_name='kb'
    store.client.create_collection('kb',vectors_config=VectorParams(size=3,distance=Distance.COSINE))
    chunks=[]
    for i,(airline,visibility) in enumerate([('indigo','public'),('indigo','private'),('spicejet','private'),('dgca','private'),('indigo',None),('dgca','public')]):
        metadata={'airline':airline,'category':'baggage'}
        if visibility: metadata['visibility']=visibility
        chunks.append({'chunk_id':str(i),'text':'baggage policy '+str(i),'metadata':metadata})
    store.client.upsert('kb',points=[PointStruct(id=i,vector=[1.,0.,0.],payload={'chunk_id':c['chunk_id'],'text':c['text'],**c['metadata']}) for i,c in enumerate(chunks)])
    public=store.query([1.,0.,0.],top_k=10)
    assert {r['chunk_id'] for r in public} == {'0','5'}
    tenant=TenantConfig('indigo','indigo','IndiGo','key')
    private=store.query_for_tenant(tenant,[1.,0.,0.],top_k=10)
    assert {r['chunk_id'] for r in private} == {'0','1','4','5'}
    index=BM25Index();index.build(chunks)
    merged=hybrid_search('baggage',[1.,0.,0.],index,store,top_k=10)
    assert {r['chunk_id'] for r in merged} == {'0','5'}
    store.client.close()


def test_migration_never_publishes_changed_or_explicitly_private_payloads():
    client=MagicMock()
    chunks=[{'chunk_id':str(i),'text':'public text','metadata':{'source_doc_id':str(i),'airline':'indigo'}} for i in range(3)]
    points=[]
    for i,c in enumerate(chunks):
        point=MagicMock();point.id=str(uuid.uuid5(uuid.NAMESPACE_DNS,c['chunk_id']))
        point.payload={'chunk_id':c['chunk_id'],'text':c['text'],**c['metadata']}
        if i==1: point.payload['text']='private replacement'
        if i==2: point.payload['visibility']='private'
        points.append(point)
    client.retrieve.return_value=points
    assert migrate_public_corpus(client,'kb',chunks)['matched_legacy_points'] == 1
    client.set_payload.assert_not_called()
    migrate_public_corpus(client,'kb',chunks,apply=True)
    assert client.set_payload.call_args.kwargs['points'] == [points[0].id]


def test_upload_is_private_even_with_public_sounding_title():
    from src.ingestion.self_serve import ingest_document_for_tenant
    store=MagicMock()
    with patch('src.ingestion.self_serve.embed_chunks',side_effect=lambda chunks: chunks):
        ingest_document_for_tenant(TenantConfig('indigo','indigo','IndiGo','k'),
                                  'Public airline policy','Private instructions. '*30,'baggage',store)
    assert all(c['metadata']['visibility']=='private' for c in store.upsert.call_args.args[0])
