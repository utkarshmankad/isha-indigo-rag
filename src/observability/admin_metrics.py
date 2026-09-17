"""Admin dashboard metrics (S5-T2, extended hardening backlog with
refused/fallback/likely-false-answer separation).

Reads the existing query log (src/observability/logger.py) and aggregates
it per tenant. Cost/query is a flat estimate, not measured spend — ragas and
the OpenAI SDK responses here don't return token usage today, so a real
figure needs token-usage capture added to generate_answer() first. Flagging
that honestly rather than presenting a fabricated precise number.

`unanswered_rate` used to conflate two very different outcomes: a
confidence-gated refusal (ISHA correctly declined — see REFUSAL_FLOOR in
src/agent/graph.py) and a "fallback" answer (search was expanded or a
stage degraded, but an answer was still given). Those need different
responses from an admin — a high refusal rate might mean the corpus is
missing content; a high fallback rate might mean retrieval quality needs
work on answers that ARE being delivered. `refused_rate` and
`fallback_only_rate` split them out; `unanswered_rate` is kept, unchanged
in meaning, for backward compatibility.

Neither of those, nor confidence, measures a "false answer" — a
confidently-given, non-refused answer that was simply wrong. ISHA has no
ground truth at runtime to detect that itself. `likely_false_answer_rate`
uses the one real signal available: passenger feedback (thumbs down,
src/feedback/collector.py) on a query that was NOT refused — i.e. ISHA
answered with apparent confidence and the passenger said it wasn't right.
This is a proxy, not a verified false-answer count: a thumbs-down can mean
"wrong," "unhelpful," "not what I meant," or "correct but I'm just
frustrated" — there's no way to distinguish those from a rating alone.
"""
from dataclasses import dataclass

from src.feedback.collector import list_recent_feedback
from src.observability.logger import read_logs

# gpt-4o-mini list price ballpark for a typical ISHA prompt+completion —
# NOT measured per-call usage. Replace with real usage tracking before this
# number is used for billing.
ESTIMATED_COST_PER_QUERY_USD = 0.0015


@dataclass
class TenantMetrics:
    airline: str
    query_count: int
    unanswered_count: int
    unanswered_rate: float
    avg_confidence: float
    estimated_cost_usd: float
    refused_count: int = 0
    refused_rate: float = 0.0
    fallback_only_count: int = 0
    fallback_only_rate: float = 0.0
    likely_false_answer_count: int = 0
    # None (not 0.0) when there are no non-refused queries to rate at all —
    # distinct from "measured and found to be zero."
    likely_false_answer_rate: float | None = None


def compute_tenant_metrics(airline: str, limit: int = 10_000) -> TenantMetrics:
    entries = [e for e in read_logs(n=limit) if e.get("airline") == airline]
    total = len(entries)
    if total == 0:
        return TenantMetrics(airline, 0, 0, 0.0, 0.0, 0.0)

    refused = [e for e in entries if e.get("refused")]
    fallback_only = [e for e in entries if e.get("fallback_triggered") and not e.get("refused")]
    unanswered = len(refused) + len(fallback_only)
    avg_conf = sum(e.get("confidence", 0.0) for e in entries) / total

    down_correlation_ids = {
        f["correlation_id"] for f in list_recent_feedback(airline, limit=limit) if f.get("rating") == "down"
    }
    non_refused = [e for e in entries if not e.get("refused")]
    likely_false_answers = [e for e in non_refused if e.get("correlation_id") in down_correlation_ids]
    likely_false_rate = round(len(likely_false_answers) / len(non_refused), 4) if non_refused else None

    return TenantMetrics(
        airline=airline,
        query_count=total,
        unanswered_count=unanswered,
        unanswered_rate=round(unanswered / total, 4),
        avg_confidence=round(avg_conf, 4),
        estimated_cost_usd=round(total * ESTIMATED_COST_PER_QUERY_USD, 4),
        refused_count=len(refused),
        refused_rate=round(len(refused) / total, 4),
        fallback_only_count=len(fallback_only),
        fallback_only_rate=round(len(fallback_only) / total, 4),
        likely_false_answer_count=len(likely_false_answers),
        likely_false_answer_rate=likely_false_rate,
    )
