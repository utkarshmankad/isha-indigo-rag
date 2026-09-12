from types import SimpleNamespace
from unittest.mock import MagicMock
import json
import pytest
from src.reliability.qdrant_probe import probe_qdrant


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('QDRANT_URL', 'https://private.example')
    monkeypatch.setenv('QDRANT_API_KEY', 'secret-value')
    monkeypatch.setenv('QDRANT_COLLECTION', 'tenant_kb')
    client = MagicMock()
    client.get_collection.return_value = SimpleNamespace(status='green')
    client.scroll.return_value = ([SimpleNamespace(id=1)], None)
    return client


def test_probe_reads_points_without_vectors_or_payload(configured):
    factory = MagicMock(return_value=configured)
    assert probe_qdrant(factory)['status'] == 'ok'
    configured.get_collection.assert_called_once_with('tenant_kb')
    configured.scroll.assert_called_once_with('tenant_kb', limit=1, with_payload=False, with_vectors=False)
    assert factory.call_args.kwargs['timeout'] == 10
    configured.close.assert_called_once()


def test_probe_detects_empty_collection(configured):
    configured.scroll.return_value = ([], None)
    assert probe_qdrant(lambda **kw: configured)['reason'] == 'collection_empty'


def test_probe_redacts_failure_and_recovers_on_next_attempt(configured):
    configured.get_collection.side_effect = [RuntimeError('private.example secret-value'), SimpleNamespace(status='green')]
    failed = probe_qdrant(lambda **kw: configured)
    assert failed['status'] == 'error'
    assert 'secret-value' not in json.dumps(failed)
    assert 'private.example' not in json.dumps(failed)
    assert probe_qdrant(lambda **kw: configured)['status'] == 'ok'


def test_missing_configuration_does_not_connect(monkeypatch):
    monkeypatch.delenv('QDRANT_API_KEY', raising=False)
    factory = MagicMock()
    assert probe_qdrant(factory)['reason'] == 'missing_configuration'
    factory.assert_not_called()
