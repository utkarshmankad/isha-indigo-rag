import pytest

import src.escalation.queue as escalation_queue
from src.escalation.queue import (
    attach_contact_info,
    claim_escalation,
    enqueue_escalation,
    list_pending_escalations,
    resolve_escalation,
)


def test_enqueue_and_list_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))

    escalation_id = enqueue_escalation("what is the baggage limit", "indigo", 0.2, "corr-1")

    pending = list_pending_escalations("indigo")
    assert len(pending) == 1
    assert pending[0]["escalation_id"] == escalation_id
    assert pending[0]["status"] == "pending"
    assert pending[0]["confidence"] == 0.2


def test_enqueue_escalation_redacts_pii_in_query(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))

    enqueue_escalation("email me at passenger@example.com about this", "indigo", 0.2, "corr-1")

    pending = list_pending_escalations("indigo")
    assert "passenger@example.com" not in pending[0]["query"]
    assert "[REDACTED-EMAIL]" in pending[0]["query"]


def test_list_pending_scoped_to_airline(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))

    enqueue_escalation("q1", "indigo", 0.1, "corr-1")
    enqueue_escalation("q2", "spicejet", 0.1, "corr-2")

    assert len(list_pending_escalations("indigo")) == 1
    assert len(list_pending_escalations("spicejet")) == 1
    assert len(list_pending_escalations("air-india")) == 0


def test_resolve_escalation_marks_resolved(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))

    escalation_id = enqueue_escalation("q1", "indigo", 0.1, "corr-1")

    assert resolve_escalation(escalation_id, "indigo") is True
    assert list_pending_escalations("indigo") == []


def test_resolve_escalation_rejects_wrong_airline(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))

    escalation_id = enqueue_escalation("q1", "indigo", 0.1, "corr-1")

    assert resolve_escalation(escalation_id, "spicejet") is False
    assert len(list_pending_escalations("indigo")) == 1


def test_resolve_escalation_unknown_id_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))

    assert resolve_escalation("nonexistent-id", "indigo") is False


def test_enqueue_defaults_new_fields_to_none(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))

    enqueue_escalation("q1", "indigo", 0.1, "corr-1")

    entry = list_pending_escalations("indigo")[0]
    assert entry["contact_channel"] is None
    assert entry["contact_value"] is None
    assert entry["owner"] is None
    assert entry["response"] is None
    assert entry["responded_at"] is None


def test_attach_contact_info_updates_pending_entry_by_correlation_id(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    enqueue_escalation("q1", "indigo", 0.1, "corr-1")

    assert attach_contact_info("corr-1", "email", "passenger@example.com") is True

    entry = list_pending_escalations("indigo")[0]
    assert entry["contact_channel"] == "email"
    assert entry["contact_value"] == "passenger@example.com"


def test_attach_contact_info_unknown_correlation_id_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    assert attach_contact_info("nonexistent-corr", "email", "x@example.com") is False


def test_attach_contact_info_rejects_invalid_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    enqueue_escalation("q1", "indigo", 0.1, "corr-1")
    with pytest.raises(ValueError):
        attach_contact_info("corr-1", "carrier-pigeon", "x@example.com")


def test_attach_contact_info_rejects_empty_value(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    enqueue_escalation("q1", "indigo", 0.1, "corr-1")
    with pytest.raises(ValueError):
        attach_contact_info("corr-1", "email", "   ")


def test_attach_contact_info_ignores_already_resolved_escalation(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    escalation_id = enqueue_escalation("q1", "indigo", 0.1, "corr-1")
    resolve_escalation(escalation_id, "indigo")

    assert attach_contact_info("corr-1", "email", "x@example.com") is False


def test_claim_escalation_sets_owner_scoped_to_airline(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    escalation_id = enqueue_escalation("q1", "indigo", 0.1, "corr-1")

    assert claim_escalation(escalation_id, "indigo", "agent-priya") is True
    assert list_pending_escalations("indigo")[0]["owner"] == "agent-priya"


def test_claim_escalation_rejects_wrong_airline(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    escalation_id = enqueue_escalation("q1", "indigo", 0.1, "corr-1")

    assert claim_escalation(escalation_id, "spicejet", "agent-priya") is False
    assert list_pending_escalations("indigo")[0]["owner"] is None


def test_resolve_escalation_records_response_and_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    escalation_id = enqueue_escalation("q1", "indigo", 0.1, "corr-1")

    assert resolve_escalation(escalation_id, "indigo", response="Called passenger, resolved via phone.") is True

    entries = escalation_queue._read_all()
    entry = next(e for e in entries if e["escalation_id"] == escalation_id)
    assert entry["status"] == "resolved"
    assert entry["response"] == "Called passenger, resolved via phone."
    assert entry["responded_at"] is not None


def test_resolve_escalation_without_response_leaves_response_none(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    escalation_id = enqueue_escalation("q1", "indigo", 0.1, "corr-1")

    resolve_escalation(escalation_id, "indigo")

    entries = escalation_queue._read_all()
    entry = next(e for e in entries if e["escalation_id"] == escalation_id)
    assert entry["response"] is None


def test_resolve_escalation_rejects_oversized_response(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(tmp_path / "escalations.jsonl"))
    escalation_id = enqueue_escalation("q1", "indigo", 0.1, "corr-1")
    with pytest.raises(ValueError):
        resolve_escalation(escalation_id, "indigo", response="x" * 5000)


def test_failed_atomic_replace_preserves_pending_records(tmp_path, monkeypatch):
    path = tmp_path / "escalations.jsonl"
    monkeypatch.setattr(escalation_queue, "ESCALATION_FILE", str(path))
    escalation_id = enqueue_escalation("q1", "indigo", 0.1, "corr-1")
    original = path.read_bytes()
    def fail_replace(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(escalation_queue.os, "replace", fail_replace)
    assert resolve_escalation(escalation_id, "indigo") is False
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
