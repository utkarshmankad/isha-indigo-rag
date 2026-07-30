import json
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.observability.logging_config import get_logger

logger = get_logger("observability.query_log")

LOG_FILE = "logs/query_log.jsonl"

_lock = threading.Lock()


def log_query(
    query: str,
    selected_tools: list[str],
    retrieved_chunks: list[dict],
    confidence: float,
    answer: str,
    latency_ms: int,
    dgca_query: bool = False,
    correlation_id: str = "",
    expanded_search: bool = False,
    stage_error: str = "",
) -> None:
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    sources = [
        {
            "title": c["metadata"].get("title", ""),
            "category": c["metadata"].get("category", ""),
            "score": round(c.get("score", 0.0), 3),
        }
        for c in retrieved_chunks
    ]
    relevance_scores = [c.get("score", 0.0) for c in retrieved_chunks]
    avg_relevance = round(sum(relevance_scores) / len(relevance_scores), 3) if relevance_scores else 0.0
    fallback_triggered = expanded_search or bool(stage_error) or not retrieved_chunks

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "query": query,
        "selected_tools": selected_tools,
        "confidence": round(confidence, 2),
        "latency_ms": int(latency_ms),
        "answer_length": len(answer),
        "dgca_query": dgca_query,
        "sources": sources,
        "avg_relevance_score": avg_relevance,
        "expanded_search": expanded_search,
        "stage_error": stage_error,
        "fallback_triggered": fallback_triggered,
    }
    with _lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    logger.info(
        "query logged",
        correlation_id=correlation_id,
        confidence=round(confidence, 2), latency_ms=int(latency_ms), selected_tools=selected_tools,
    )


def read_logs(n: int = 50) -> list[dict]:
    p = Path(LOG_FILE)
    if not p.exists():
        return []
    with _lock:
        lines = p.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries[-n:]


def print_summary() -> None:
    entries = read_logs(n=10_000)
    total = len(entries)
    if total == 0:
        print("No queries logged yet.")
        return

    confidences = [e["confidence"] for e in entries]
    latencies = [e["latency_ms"] for e in entries]
    avg_conf = sum(confidences) / total
    avg_lat = sum(latencies) / total

    cat_counter: Counter = Counter()
    for e in entries:
        for src in e.get("sources", []):
            cat = src.get("category", "unknown")
            if cat:
                cat_counter[cat] += 1

    dgca_count = sum(1 for e in entries if e.get("dgca_query"))
    dgca_pct = dgca_count / total * 100

    relevance_scores = [e["avg_relevance_score"] for e in entries if "avg_relevance_score" in e]
    avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0

    fallback_count = sum(1 for e in entries if e.get("fallback_triggered"))
    fallback_pct = fallback_count / total * 100

    stage_error_counter: Counter = Counter(
        e["stage_error"] for e in entries if e.get("stage_error")
    )

    low_conf = [e for e in entries if e["confidence"] < 0.40]

    print("=" * 60)
    print("ISHA QUERY LOG SUMMARY")
    print("=" * 60)
    print(f"Total queries      : {total}")
    print(f"Avg confidence     : {avg_conf:.3f}")
    print(f"Avg relevance      : {avg_relevance:.3f}")
    print(f"Avg latency        : {avg_lat:.0f} ms")
    print(f"Fallback rate      : {fallback_count}/{total} ({fallback_pct:.1f}%)")
    if stage_error_counter:
        print("  Stage failures:")
        for stage, count in stage_error_counter.most_common():
            print(f"    {stage:<20} {count:>4}")
    print()
    print("Top categories queried:")
    for cat, count in cat_counter.most_common():
        print(f"  {cat:<35} {count:>4} hits")
    print()
    print(f"DGCA queries       : {dgca_count} ({dgca_pct:.1f}%)")
    print()
    if low_conf:
        print(f"⚠  Low-confidence queries (< 0.40) — potential knowledge gaps:")
        for e in low_conf:
            print(f"  conf={e['confidence']:.2f}  tools={e['selected_tools']}")
            print(f"    Q: {e['query'][:100]}")
    else:
        print("✅ No low-confidence queries (all ≥ 0.40)")
    print("=" * 60)
