import src.observability.logger as query_log


def test_log_query_redacts_pii_in_stored_query(tmp_path, monkeypatch):
    monkeypatch.setattr(query_log, "LOG_FILE", str(tmp_path / "query_log.jsonl"))

    query_log.log_query(
        query="please email me at passenger@example.com about my baggage",
        selected_tools=["baggage"], retrieved_chunks=[], confidence=0.8,
        answer="ok", latency_ms=100, correlation_id="corr-1", airline="indigo",
    )

    entries = query_log.read_logs()
    assert entries[0]["query"] == "please email me at [REDACTED-EMAIL] about my baggage"
    assert "passenger@example.com" not in entries[0]["query"]


def test_log_query_redacts_phone_number(tmp_path, monkeypatch):
    monkeypatch.setattr(query_log, "LOG_FILE", str(tmp_path / "query_log.jsonl"))

    query_log.log_query(
        query="call me on 9876543210 about my refund",
        selected_tools=["cancellations_and_refunds"], retrieved_chunks=[], confidence=0.8,
        answer="ok", latency_ms=100, correlation_id="corr-1", airline="indigo",
    )

    entries = query_log.read_logs()
    assert "9876543210" not in entries[0]["query"]
    assert "[REDACTED-PHONE]" in entries[0]["query"]


def test_log_query_leaves_ordinary_query_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(query_log, "LOG_FILE", str(tmp_path / "query_log.jsonl"))

    query_log.log_query(
        query="what is the baggage allowance for IndiGo?",
        selected_tools=["baggage"], retrieved_chunks=[], confidence=0.8,
        answer="ok", latency_ms=100, correlation_id="corr-1", airline="indigo",
    )

    entries = query_log.read_logs()
    assert entries[0]["query"] == "what is the baggage allowance for IndiGo?"
