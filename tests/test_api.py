from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import src.api.main as api_main
from src.tenancy.registry import TenantConfig


@pytest.fixture(autouse=True)
def _fixed_registry(monkeypatch):
    fake = {
        "indigo": TenantConfig("indigo", "indigo", "IndiGo (6E)", "indigo-secret-key", "indigo-admin-key"),
        "spicejet": TenantConfig("spicejet", "spicejet", "SpiceJet (SG)", "sj-secret-key"),
    }
    monkeypatch.setattr("src.tenancy.registry.TENANTS", fake)
    return fake


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    api_main._query_times.clear()
    yield
    api_main._query_times.clear()


@pytest.fixture
def client():
    return TestClient(api_main.app)


def test_health_before_pipeline_ready(client):
    api_main._pipeline.clear()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["pipeline_ready"] is False


def test_query_without_api_key_rejected(client):
    resp = client.post("/v1/query", json={"query": "baggage allowance?"})
    assert resp.status_code == 422  # missing required header


def test_query_with_wrong_api_key_rejected(client):
    resp = client.post(
        "/v1/query", json={"query": "baggage allowance?"}, headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_query_with_valid_key_calls_tenant_scoped_agent(client):
    api_main._pipeline["graph"] = MagicMock()
    fake_state = {
        "answer": "You may carry 7kg.", "confidence": 0.8, "retrieved_chunks": [],
    }
    with patch("src.api.main.run_agent_for_tenant", return_value=fake_state) as mock_run:
        resp = client.post(
            "/v1/query", json={"query": "baggage allowance?"},
            headers={"X-API-Key": "indigo-secret-key"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "You may carry 7kg."
    assert body["confidence"] == 0.8

    tenant_arg = mock_run.call_args[0][2]
    assert tenant_arg.airline == "indigo"


def test_spicejet_key_cannot_scope_to_indigo(client):
    """A valid key always resolves to its own tenant's airline, never a
    caller-requested one — the request body has no airline field at all."""
    api_main._pipeline["graph"] = MagicMock()
    fake_state = {"answer": "ok", "confidence": 0.5, "retrieved_chunks": []}
    with patch("src.api.main.run_agent_for_tenant", return_value=fake_state) as mock_run:
        client.post(
            "/v1/query", json={"query": "what is the baggage allowance"}, headers={"X-API-Key": "sj-secret-key"},
        )
    tenant_arg = mock_run.call_args[0][2]
    assert tenant_arg.airline == "spicejet"


def test_rate_limit_enforced_per_tenant(client):
    api_main._pipeline["graph"] = MagicMock()
    fake_state = {"answer": "ok", "confidence": 0.5, "retrieved_chunks": []}
    with patch("src.api.main.run_agent_for_tenant", return_value=fake_state):
        for _ in range(api_main._QPM_LIMIT):
            resp = client.post(
                "/v1/query", json={"query": "what is the baggage allowance"}, headers={"X-API-Key": "indigo-secret-key"},
            )
            assert resp.status_code == 200
        resp = client.post(
            "/v1/query", json={"query": "what is the baggage allowance"}, headers={"X-API-Key": "indigo-secret-key"},
        )
    assert resp.status_code == 429


def test_admin_metrics_requires_valid_key(client):
    resp = client.get("/v1/admin/metrics", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_admin_metrics_scoped_to_own_tenant(client):
    fake_logs = [
        {"airline": "indigo", "confidence": 0.8, "refused": False, "fallback_triggered": False},
        {"airline": "spicejet", "confidence": 0.9, "refused": False, "fallback_triggered": False},
    ]
    with patch("src.observability.admin_metrics.read_logs", return_value=fake_logs):
        resp = client.get("/v1/admin/metrics", headers={"X-Admin-Key": "indigo-admin-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["airline"] == "indigo"
    assert body["query_count"] == 1  # not 2 — spicejet's entry must not leak in
