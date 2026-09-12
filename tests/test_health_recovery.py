from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
import src.api.main as api
from src.agent.graph import build_graph, run_agent
from tests.test_refusal import SAMPLE_CHUNKS


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    monkeypatch.setattr(api, '_pipeline', {})
    monkeypatch.setattr(api, '_last_init_attempt', float('-inf'))


def test_startup_outage_does_not_kill_api_and_health_recovers(monkeypatch):
    def recovered():
        api._pipeline['graph'] = MagicMock()
    with patch.object(api, 'init_app_state', side_effect=RuntimeError('offline')):
        with TestClient(api.app) as client:
            assert client.get('/live').status_code == 200
            with patch.object(api, 'check_qdrant', return_value={'status':'error'}):
                assert client.get('/health').status_code == 503
            monkeypatch.setattr(api, '_last_init_attempt', float('-inf'))
            with patch.object(api, 'init_app_state', side_effect=recovered), \
                 patch.object(api, 'check_qdrant', return_value={'status':'ok'}), \
                 patch.object(api, 'check_openai_key', return_value={'status':'ok'}):
                assert client.get('/health').status_code == 200


def test_initialization_cooldown_prevents_repeated_connection_attempts():
    with patch.object(api, 'init_app_state', side_effect=RuntimeError('offline')) as init:
        assert not api.ensure_pipeline()
        assert not api.ensure_pipeline()
        assert init.call_count == 1


def test_cached_pipeline_does_not_mask_database_outage():
    api._pipeline['graph'] = MagicMock()
    with patch.object(api, 'check_qdrant', return_value={'status':'error'}):
        assert TestClient(api.app).get('/health').status_code == 503


def test_read_only_app_initialization_never_creates_missing_collection(monkeypatch):
    from src.embedding.vector_store import QdrantVectorStore
    monkeypatch.setenv('QDRANT_URL','https://example.test')
    monkeypatch.setenv('QDRANT_API_KEY','test')
    client = MagicMock(); client.get_collections.return_value.collections = []
    with patch('src.embedding.vector_store.QdrantClient', return_value=client):
        with pytest.raises(RuntimeError, match='Collection unavailable'):
            QdrantVectorStore(create_if_missing=False)
    client.create_collection.assert_not_called()
    client.create_payload_index.assert_not_called()
    client.close.assert_called_once()


def test_retrieval_outage_preserves_error_instead_of_policy_refusal():
    store = MagicMock()
    store.query.side_effect = RuntimeError('offline')
    with patch('src.agent.graph.embed_batch', return_value=[[0.0]*8]), \
         patch('src.agent.graph.generate_answer', return_value='hypothetical'):
        state = run_agent('What is the baggage allowance?', build_graph(SAMPLE_CHUNKS,store),airline='indigo')
    assert state['stage_error'] == 'retrieval'
    assert 'could not find this in the policy' not in state['answer']


def test_query_returns_503_on_dependency_error_then_recovers():
    from src.tenancy.registry import TenantConfig
    api._pipeline['graph'] = MagicMock()
    api.app.dependency_overrides[api.get_tenant] = lambda: TenantConfig('test','indigo','Test','secret')
    try:
        client=TestClient(api.app)
        with patch.object(api,'run_agent_for_tenant',side_effect=[
            {'stage_error':'retrieval'},
            {'answer':'restored', 'confidence':0.8,'retrieved_chunks':[]}]) :
            response=client.post('/v1/query',json={'query':'What is baggage allowance?'})
            assert response.status_code == 503
            assert response.headers['retry-after'] == '5'
            assert client.post('/v1/query',json={'query':'What is baggage allowance?'}).status_code == 200
    finally:
        api.app.dependency_overrides.clear()
