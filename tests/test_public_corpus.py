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
        metadata['status'] = 'approved'
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


def test_query_excludes_pending_rejected_and_superseded_by_default():
    store=QdrantVectorStore.__new__(QdrantVectorStore)
    store.client=QdrantClient(':memory:');store.collection_name='kb'
    store.client.create_collection('kb',vectors_config=VectorParams(size=3,distance=Distance.COSINE))
    rows=[
        ('approved','approved'),('pending','pending'),('rejected','rejected'),
        ('superseded','superseded'),('bundled',None),
    ]
    points=[]
    for i,(chunk_id,status) in enumerate(rows):
        payload={'chunk_id':chunk_id,'text':'baggage policy','airline':'indigo','visibility':'public'}
        if status: payload['status']=status
        points.append(PointStruct(id=i,vector=[1.,0.,0.],payload=payload))
    store.client.upsert('kb',points=points)

    public=store.query([1.,0.,0.],top_k=10)
    assert {r['chunk_id'] for r in public} == {'approved','bundled'}

    tenant=TenantConfig('indigo','indigo','IndiGo','key')
    scoped=store.query_for_tenant(tenant,[1.,0.,0.],top_k=10)
    assert {r['chunk_id'] for r in scoped} == {'approved','bundled'}
    store.client.close()


def test_set_status_by_doc_id_patches_payload_without_touching_vector():
    store=QdrantVectorStore.__new__(QdrantVectorStore)
    store.client=QdrantClient(':memory:');store.collection_name='kb'
    store.client.create_collection('kb',vectors_config=VectorParams(size=3,distance=Distance.COSINE))
    store.client.upsert('kb',points=[PointStruct(
        id=0,vector=[1.,0.,0.],
        payload={'chunk_id':'c0','text':'t','airline':'indigo','visibility':'public','source_doc_id':'doc_1','status':'pending'},
    )])

    store.set_status_by_doc_id('doc_1','approved')

    fetched=store.client.retrieve('kb',ids=[0],with_payload=True,with_vectors=True)[0]
    assert fetched.payload['status']=='approved'
    assert fetched.vector==[1.,0.,0.]
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
    manager=MagicMock()
    with patch('src.ingestion.self_serve.embed_chunks',side_effect=lambda chunks: chunks):
        ingest_document_for_tenant(TenantConfig('indigo','indigo','IndiGo','k'),
                                  'Public airline policy','Private instructions. '*30,'baggage',manager)
    assert all(c['metadata']['visibility']=='private' for c in manager.add_document.call_args.args[1])


def test_approval_allowlist_matches_dense_and_lexical_paths():
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store.client = QdrantClient(':memory:')
    store.collection_name = 'approval'
    store.client.create_collection('approval', vectors_config=VectorParams(size=3, distance=Distance.COSINE))
    chunks = []
    for i, (visibility, status) in enumerate([
        ('private', None), ('private', 'unexpected'), ('private', 'approved'),
        ('public', 'unexpected'), ('public', None), ('private', 'pending'),
    ]):
        chunks.append({'chunk_id': str(i), 'text': 'baggage policy',
                       'metadata': {'airline': 'indigo', 'visibility': visibility, 'status': status}})
    store.client.upsert('approval', points=[PointStruct(
        id=i, vector=[1., 0., 0.], payload={'chunk_id': c['chunk_id'], 'text': c['text'], **c['metadata']},
    ) for i, c in enumerate(chunks)])
    index = BM25Index()
    index.build(chunks)
    for scope, expected in [(None, {'4'}), (['indigo', 'dgca'], {'2', '4'})]:
        assert {r['chunk_id'] for r in store.query([1., 0., 0.], top_k=10, airline_filter=scope)} == expected
        # No dense results: prove the lexical path independently applies approval.
        dense = MagicMock()
        dense.query.return_value = []
        assert {r['chunk_id'] for r in hybrid_search('baggage', [1., 0., 0.], index, dense,
                top_k=10, airline_filter=scope)} == expected
    store.client.close()
