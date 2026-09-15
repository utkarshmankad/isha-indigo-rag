import src.escalation.queue as escalation_queue
from src.escalation.queue import (
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
