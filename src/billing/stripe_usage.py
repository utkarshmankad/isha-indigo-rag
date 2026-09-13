"""Stripe usage-based billing (S8-T1).

Reports one Stripe meter event per answered query, keyed by tenant, using
Stripe's Billing Meters API (meter events → usage-based prices → invoice
line items). This module never blocks or fails a query on a billing error —
billing is a side effect, not a gate; a Stripe outage must never stop ISHA
from answering.

**Not live-verified**: no Stripe test account/API key is available in this
environment, so this has never been run against real Stripe. Every call
path is covered by mocked unit tests (see tests/test_billing.py) exercising
the actual request shape sent to the SDK, and the module degrades to a
no-op with a logged warning when STRIPE_API_KEY isn't set — same fallback
pattern as embed_batch()'s mock-embeddings path when OPENAI_API_KEY is
missing. Whoever wires up a real Stripe account should do one live smoke
test against Stripe's test mode before trusting this in production.
"""
import os
import time

from src.observability.logging_config import get_logger

logger = get_logger("billing.stripe_usage")

# Stripe meter event_name — must match a Meter configured in the Stripe
# dashboard (Billing > Meters) with this exact identifier.
METER_EVENT_NAME = "isha_query"


def _stripe_configured() -> bool:
    return bool(os.environ.get("STRIPE_API_KEY"))


def record_query_usage(tenant_id: str, correlation_id: str) -> bool:
    """Report one query as billable usage for `tenant_id`. Returns True if
    the SDK call succeeded, False if configuration was missing or reporting failed — callers should log and move on, never raise.
    """
    if not _stripe_configured():
        logger.warning(
            "STRIPE_API_KEY not set, skipping usage report",
            tenant=tenant_id, correlation_id=correlation_id,
        )
        return False

    customer_id = os.environ.get(f"STRIPE_CUSTOMER_ID_{tenant_id.upper()}", "")
    if not customer_id.startswith("cus_"):
        logger.warning("Stripe customer mapping missing; skipping usage report", tenant=tenant_id)
        return False

    try:
        import stripe
        stripe.api_key = os.environ["STRIPE_API_KEY"]
        stripe.billing.MeterEvent.create(
            event_name=METER_EVENT_NAME,
            payload={"stripe_customer_id": customer_id, "value": "1"},
            timestamp=int(time.time()),
            identifier=correlation_id,  # idempotency: same query never double-billed
        )
        logger.info("usage reported to stripe", tenant=tenant_id, correlation_id=correlation_id)
        return True
    except Exception:
        # Billing must never be allowed to break the actual product.
        logger.error(
            "stripe usage reporting failed, query still served normally",
            tenant=tenant_id, correlation_id=correlation_id, exc_info=True,
        )
        return False
