from unittest.mock import MagicMock

import pytest

from src.tenancy.registry import TenantConfig, authenticate


@pytest.fixture(autouse=True)
def _fixed_registry(monkeypatch):
    fake = {
        "indigo": TenantConfig("indigo", "indigo", "IndiGo (6E)", "indigo-secret-key"),
        "air_india": TenantConfig("air_india", "air_india", "Air India (AI)", "ai-secret-key"),
    }
    monkeypatch.setattr("src.tenancy.registry.TENANTS", fake)
    return fake


def test_correct_key_authenticates():
    tenant = authenticate("indigo", "indigo-secret-key")
    assert tenant is not None
    assert tenant.airline == "indigo"


def test_wrong_key_rejected():
    assert authenticate("indigo", "wrong-key") is None


def test_key_from_other_tenant_rejected():
    """A valid Air India key must not authenticate against IndiGo."""
    assert authenticate("indigo", "ai-secret-key") is None


def test_unknown_airline_rejected():
    assert authenticate("nonexistent_airline", "indigo-secret-key") is None


def test_empty_key_rejected():
    assert authenticate("indigo", "") is None


def test_query_for_tenant_always_scopes_to_tenant_airline():
    from src.embedding.vector_store import QdrantVectorStore

    store = MagicMock(spec=QdrantVectorStore)
    store.query = MagicMock(return_value=[])
    tenant = TenantConfig("indigo", "indigo", "IndiGo (6E)", "indigo-secret-key")

    QdrantVectorStore.query_for_tenant(store, tenant, [0.1] * 8, top_k=5)

    store.query.assert_called_once()
    _, kwargs = store.query.call_args
    assert kwargs["airline_filter"] == ["indigo", "dgca"]


def test_run_agent_for_tenant_ignores_caller_airline_arg():
    """Even if something upstream tries to widen scope, the tenant-scoped
    entry point only ever uses the authenticated tenant's airline."""
    from src.agent.graph import run_agent_for_tenant

    tenant = TenantConfig("indigo", "indigo", "IndiGo (6E)", "indigo-secret-key")
    graph = MagicMock()
    graph.invoke.return_value = {
        "query": "x", "airline": "indigo", "selected_tools": [], "retrieved_chunks": [],
        "context": "", "answer": "ok", "confidence": 0.0, "iterations": 1,
        "dgca_query": False, "stage_error": "", "correlation_id": "test",
    }

    run_agent_for_tenant("some query", graph, tenant)

    called_state = graph.invoke.call_args[0][0]
    assert called_state["airline"] == "indigo"
