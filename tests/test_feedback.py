import pytest

import src.feedback.collector as feedback_collector
from src.feedback.collector import (
    UnknownCorrelationIdError,
    compute_feedback_summary,
    list_recent_feedback,
    record_feedback,
)


@pytest.fixture(autouse=True)
def _isolated_feedback_file(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback_collector, "FEEDBACK_FILE", str(tmp_path / "feedback.jsonl"))


def _log_query(monkeypatch, correlation_id, airline="indigo"):
    monkeypatch.setattr(
        feedback_collector, "read_logs",
        lambda n=10_000: [{"correlation_id": correlation_id, "airline": airline}],
    )


def test_record_feedback_requires_logged_correlation_id(monkeypatch):
    monkeypatch.setattr(feedback_collector, "read_logs", lambda n=10_000: [])
    with pytest.raises(UnknownCorrelationIdError):
        record_feedback("nonexistent-corr", "up")


def test_record_feedback_rejects_invalid_rating(monkeypatch):
    _log_query(monkeypatch, "corr-1")
    with pytest.raises(ValueError):
        record_feedback("corr-1", "sideways")


def test_record_feedback_rejects_oversized_comment(monkeypatch):
    _log_query(monkeypatch, "corr-1")
    with pytest.raises(ValueError):
        record_feedback("corr-1", "up", comment="x" * 2000)


def test_record_feedback_stores_airline_from_query_log_not_caller(monkeypatch):
    """Regression: airline must be looked up server-side, never trusted
    from the client, or a caller could pollute another tenant's feedback
    view just by picking a different correlation_id lookup."""
    _log_query(monkeypatch, "corr-1", airline="spicejet")

    record_feedback("corr-1", "up")

    assert len(list_recent_feedback("spicejet")) == 1
    assert list_recent_feedback("indigo") == []


def test_record_feedback_overwrites_previous_rating_for_same_correlation_id(monkeypatch):
    _log_query(monkeypatch, "corr-1")

    record_feedback("corr-1", "up")
    record_feedback("corr-1", "down")

    entries = list_recent_feedback("indigo")
    assert len(entries) == 1
    assert entries[0]["rating"] == "down"


def test_record_feedback_strips_and_allows_empty_comment(monkeypatch):
    _log_query(monkeypatch, "corr-1")

    record_feedback("corr-1", "up", comment="   ")

    entries = list_recent_feedback("indigo")
    assert entries[0]["comment"] is None


def test_list_recent_feedback_scoped_to_airline(monkeypatch):
    monkeypatch.setattr(
        feedback_collector, "read_logs",
        lambda n=10_000: [
            {"correlation_id": "corr-1", "airline": "indigo"},
            {"correlation_id": "corr-2", "airline": "spicejet"},
        ],
    )
    record_feedback("corr-1", "up")
    record_feedback("corr-2", "down")

    assert len(list_recent_feedback("indigo")) == 1
    assert len(list_recent_feedback("spicejet")) == 1
    assert list_recent_feedback("air_india") == []


def test_compute_feedback_summary_counts_and_satisfaction_rate(monkeypatch):
    monkeypatch.setattr(
        feedback_collector, "read_logs",
        lambda n=10_000: [
            {"correlation_id": "corr-1", "airline": "indigo"},
            {"correlation_id": "corr-2", "airline": "indigo"},
            {"correlation_id": "corr-3", "airline": "indigo"},
        ],
    )
    record_feedback("corr-1", "up")
    record_feedback("corr-2", "up")
    record_feedback("corr-3", "down")

    summary = compute_feedback_summary("indigo")
    assert summary == {"up": 2, "down": 1, "total": 3, "satisfaction_rate": round(2 / 3, 4)}


def test_compute_feedback_summary_no_feedback_yet():
    summary = compute_feedback_summary("indigo")
    assert summary == {"up": 0, "down": 0, "total": 0, "satisfaction_rate": None}
