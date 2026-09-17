from unittest.mock import patch

import src.feedback.collector as feedback_collector
from src.observability.admin_metrics import compute_tenant_metrics

FAKE_LOGS = [
    {"airline": "indigo", "confidence": 0.8, "refused": False, "fallback_triggered": False, "correlation_id": "c1"},
    {"airline": "indigo", "confidence": 0.9, "refused": False, "fallback_triggered": False, "correlation_id": "c2"},
    {"airline": "indigo", "confidence": 0.2, "refused": True, "fallback_triggered": True, "correlation_id": "c3"},
    {"airline": "spicejet", "confidence": 0.7, "refused": False, "fallback_triggered": False, "correlation_id": "c4"},
]


def _isolate_feedback(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback_collector, "FEEDBACK_FILE", str(tmp_path / "feedback.jsonl"))


@patch("src.observability.admin_metrics.read_logs", return_value=FAKE_LOGS)
def test_metrics_scoped_to_single_airline(mock_read, tmp_path, monkeypatch):
    _isolate_feedback(tmp_path, monkeypatch)
    metrics = compute_tenant_metrics("indigo")
    assert metrics.query_count == 3
    assert metrics.unanswered_count == 1
    assert metrics.unanswered_rate == round(1 / 3, 4)
    assert metrics.avg_confidence == round((0.8 + 0.9 + 0.2) / 3, 4)


@patch("src.observability.admin_metrics.read_logs", return_value=FAKE_LOGS)
def test_metrics_do_not_leak_other_tenants(mock_read, tmp_path, monkeypatch):
    _isolate_feedback(tmp_path, monkeypatch)
    metrics = compute_tenant_metrics("spicejet")
    assert metrics.query_count == 1
    assert metrics.avg_confidence == 0.7


@patch("src.observability.admin_metrics.read_logs", return_value=[])
def test_metrics_empty_log(mock_read, tmp_path, monkeypatch):
    _isolate_feedback(tmp_path, monkeypatch)
    metrics = compute_tenant_metrics("indigo")
    assert metrics.query_count == 0
    assert metrics.unanswered_rate == 0.0


@patch("src.observability.admin_metrics.read_logs", return_value=FAKE_LOGS)
def test_refused_and_fallback_counted_separately(mock_read, tmp_path, monkeypatch):
    """Regression: unanswered_rate used to conflate a hard refusal
    (confidence-gated decline) with a fallback answer (degraded search,
    but an answer was still given) — these need different admin
    responses, so they're now tracked separately."""
    _isolate_feedback(tmp_path, monkeypatch)
    metrics = compute_tenant_metrics("indigo")
    assert metrics.refused_count == 1
    assert metrics.refused_rate == round(1 / 3, 4)
    assert metrics.fallback_only_count == 0  # the one fallback entry was also refused
    assert metrics.fallback_only_rate == 0.0


@patch("src.observability.admin_metrics.read_logs", return_value=[
    {"airline": "indigo", "confidence": 0.6, "refused": False, "fallback_triggered": True, "correlation_id": "c1"},
    {"airline": "indigo", "confidence": 0.9, "refused": False, "fallback_triggered": False, "correlation_id": "c2"},
])
def test_fallback_only_excludes_refused_entries(mock_read, tmp_path, monkeypatch):
    _isolate_feedback(tmp_path, monkeypatch)
    metrics = compute_tenant_metrics("indigo")
    assert metrics.refused_count == 0
    assert metrics.fallback_only_count == 1
    assert metrics.fallback_only_rate == 0.5


@patch("src.observability.admin_metrics.read_logs", return_value=FAKE_LOGS)
def test_likely_false_answer_counts_thumbs_down_on_non_refused_queries(mock_read, tmp_path, monkeypatch):
    _isolate_feedback(tmp_path, monkeypatch)
    from src.feedback import collector

    monkeypatch.setattr(collector, "_lookup_airline", lambda correlation_id: "indigo")
    collector.record_feedback("c1", "down")  # c1 is a non-refused indigo query

    metrics = compute_tenant_metrics("indigo")
    assert metrics.likely_false_answer_count == 1
    # denominator is non-refused queries only (c1, c2) — 1/2, not 1/3
    assert metrics.likely_false_answer_rate == 0.5


@patch("src.observability.admin_metrics.read_logs", return_value=FAKE_LOGS)
def test_likely_false_answer_ignores_thumbs_down_on_refused_query(mock_read, tmp_path, monkeypatch):
    """A passenger downvoting a refusal doesn't imply a false ANSWER —
    there was no answer to be false. Only non-refused queries count."""
    _isolate_feedback(tmp_path, monkeypatch)
    from src.feedback import collector

    monkeypatch.setattr(collector, "_lookup_airline", lambda correlation_id: "indigo")
    collector.record_feedback("c3", "down")  # c3 is the refused indigo query

    metrics = compute_tenant_metrics("indigo")
    assert metrics.likely_false_answer_count == 0


@patch("src.observability.admin_metrics.read_logs", return_value=FAKE_LOGS)
def test_likely_false_answer_rate_is_none_when_all_queries_refused(mock_read, tmp_path, monkeypatch):
    _isolate_feedback(tmp_path, monkeypatch)
    all_refused = [{"airline": "indigo", "confidence": 0.1, "refused": True,
                     "fallback_triggered": True, "correlation_id": "c1"}]
    mock_read.return_value = all_refused
    metrics = compute_tenant_metrics("indigo")
    assert metrics.likely_false_answer_rate is None
