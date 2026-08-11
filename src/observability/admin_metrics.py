"""Admin dashboard metrics (S5-T2).

Reads the existing query log (src/observability/logger.py) and aggregates
it per tenant. Cost/query is a flat estimate, not measured spend — ragas and
the OpenAI SDK responses here don't return token usage today, so a real
figure needs token-usage capture added to generate_answer() first. Flagging
that honestly rather than presenting a fabricated precise number.
"""
from dataclasses import dataclass

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


def compute_tenant_metrics(airline: str, limit: int = 10_000) -> TenantMetrics:
    entries = [e for e in read_logs(n=limit) if e.get("airline") == airline]
    total = len(entries)
    if total == 0:
        return TenantMetrics(airline, 0, 0, 0.0, 0.0, 0.0)

    unanswered = sum(1 for e in entries if e.get("refused") or e.get("fallback_triggered"))
    avg_conf = sum(e.get("confidence", 0.0) for e in entries) / total

    return TenantMetrics(
        airline=airline,
        query_count=total,
        unanswered_count=unanswered,
        unanswered_rate=round(unanswered / total, 4),
        avg_confidence=round(avg_conf, 4),
        estimated_cost_usd=round(total * ESTIMATED_COST_PER_QUERY_USD, 4),
    )
