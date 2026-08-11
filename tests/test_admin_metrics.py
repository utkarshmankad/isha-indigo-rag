from unittest.mock import patch

from src.observability.admin_metrics import compute_tenant_metrics

FAKE_LOGS = [
    {"airline": "indigo", "confidence": 0.8, "refused": False, "fallback_triggered": False},
    {"airline": "indigo", "confidence": 0.9, "refused": False, "fallback_triggered": False},
    {"airline": "indigo", "confidence": 0.2, "refused": True, "fallback_triggered": True},
    {"airline": "spicejet", "confidence": 0.7, "refused": False, "fallback_triggered": False},
]


@patch("src.observability.admin_metrics.read_logs", return_value=FAKE_LOGS)
def test_metrics_scoped_to_single_airline(mock_read):
    metrics = compute_tenant_metrics("indigo")
    assert metrics.query_count == 3
    assert metrics.unanswered_count == 1
    assert metrics.unanswered_rate == round(1 / 3, 4)
    assert metrics.avg_confidence == round((0.8 + 0.9 + 0.2) / 3, 4)


@patch("src.observability.admin_metrics.read_logs", return_value=FAKE_LOGS)
def test_metrics_do_not_leak_other_tenants(mock_read):
    metrics = compute_tenant_metrics("spicejet")
    assert metrics.query_count == 1
    assert metrics.avg_confidence == 0.7


@patch("src.observability.admin_metrics.read_logs", return_value=[])
def test_metrics_empty_log(mock_read):
    metrics = compute_tenant_metrics("indigo")
    assert metrics.query_count == 0
    assert metrics.unanswered_rate == 0.0
