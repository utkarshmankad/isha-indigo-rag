"""FastAPI wrapper around the LangGraph pipeline (S6-T1).

Lets ISHA be embedded anywhere that can make an HTTP call — a website
widget, a Slack app, a WhatsApp webhook — instead of only being usable
through the Streamlit demo. One endpoint, tenant-authenticated the same
way as the Sprint 4/5 sidebar: an API key resolves to a tenant, and the
tenant's airline is the only one that request can ever be scoped to.

Run with: uv run uvicorn src.api.main:app --port 8080
"""
import time
import uuid
from contextlib import asynccontextmanager
from threading import Lock

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from src.observability.health import check_openai_key, check_qdrant
from pydantic import BaseModel, Field

from src.agent.graph import run_agent, run_agent_for_tenant
from src.api import rate_limiter
from src.billing.stripe_usage import record_query_usage
from src.escalation.queue import (
    VALID_CONTACT_CHANNELS,
    attach_contact_info,
    claim_escalation,
    list_pending_escalations,
    resolve_escalation,
)
from src.feedback.collector import (
    VALID_RATINGS,
    UnknownCorrelationIdError,
    compute_feedback_summary,
    list_recent_feedback,
    record_feedback,
)
from src.observability.logging_config import get_logger
from src.security.validator import QueryValidator
from src.tenancy.registry import TenantConfig, authenticate_by_key, authenticate_admin_by_key

load_dotenv()

logger = get_logger("api.main")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await run_in_threadpool(ensure_pipeline)
    yield


app = FastAPI(title="ISHA API", version="0.1.0", lifespan=_lifespan)

# Public chat is browser-accessible; administrator authorization is separate.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["POST", "GET"], allow_headers=["*"],
)

_QPM_LIMIT = 30

_pipeline: dict = {}
_init_lock = Lock()
_last_init_attempt = float('-inf')


def ensure_pipeline() -> bool:
    """Retry failed startup on later requests, with a cooldown and one builder."""
    global _last_init_attempt
    if 'graph' in _pipeline:
        return True
    if not _init_lock.acquire(blocking=False):
        return False
    try:
        if 'graph' in _pipeline:
            return True
        now = time.monotonic()
        if now - _last_init_attempt < 5:
            return False
        _last_init_attempt = now
        try:
            init_app_state()
        except Exception:
            logger.warning('pipeline unavailable; will retry initialization')
            return False
        return 'graph' in _pipeline
    finally:
        _init_lock.release()



def init_app_state() -> None:
    """Build the graph once. Called at startup and by tests with a fake store."""
    from data.air_india_documents import DOCUMENTS as AI_DOCS
    from data.dgca_documents import DOCUMENTS as DGCA_DOCS
    from data.indigo_documents import DOCUMENTS as INDIGO_DOCS
    from data.spicejet_documents import DOCUMENTS as SJ_DOCS
    from src.agent.graph import build_graph
    from src.embedding.vector_store import QdrantVectorStore
    from src.ingestion.chunker import ingest_all

    all_docs = INDIGO_DOCS + AI_DOCS + SJ_DOCS + DGCA_DOCS
    chunks = ingest_all(all_docs)
    store = QdrantVectorStore(create_if_missing=False)
    try:
        if store.stats()["total_vectors"] == 0:
            raise RuntimeError("Qdrant collection is empty. Follow docs/RECOVERY.md; do not reset during an outage.")
        _pipeline["graph"] = build_graph(chunks, store)
    except Exception:
        store.client.close()
        raise


class HistoryTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=2000)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=10)


class SourceOut(BaseModel):
    title: str
    category: str
    score: float
    source_doc_id: str
    section: int | None = Field(default=None, description="1-based chunk position, not an official policy section")
    source_url: str | None = Field(
        default=None,
        description="Authoritative source URL, when the document has one on record — not verified by ISHA itself",
    )


class QueryResponse(BaseModel):
    refused: bool = False
    answer: str
    confidence: float = Field(description="Retrieval similarity of selected evidence; not answer accuracy probability")
    sources: list[SourceOut]
    correlation_id: str


def _check_rate_limit(tenant_id: str) -> None:
    if not rate_limiter.check_and_record(tenant_id, _QPM_LIMIT):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")


def reset_rate_limits() -> None:
    """Test-only: wipe all recorded rate-limit state."""
    rate_limiter.reset()


def get_tenant(x_api_key: str = Header(..., alias="X-API-Key")) -> TenantConfig:
    tenant = authenticate_by_key(x_api_key)
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return tenant


@app.get("/live")
def live() -> dict:
    return {"status": "ok"}


@app.get("/health")
def health() -> JSONResponse:
    checks = {"qdrant": check_qdrant(), "openai": check_openai_key()}
    dependencies_ok = all(c["status"] == "ok" for c in checks.values())
    ready = ensure_pipeline() if dependencies_ok else False
    healthy = dependencies_ok and ready
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "pipeline_ready": ready, "checks": checks},
        status_code=200 if healthy else 503,
    )


class AdminMetricsResponse(BaseModel):
    airline: str
    query_count: int
    unanswered_count: int
    unanswered_rate: float
    avg_confidence: float
    estimated_cost_usd: float


def get_admin_tenant(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> TenantConfig:
    tenant = authenticate_admin_by_key(x_admin_key or "")
    if tenant is None:
        raise HTTPException(status_code=401, detail="Administrator credentials required.")
    return tenant


@app.get("/v1/admin/metrics", response_model=AdminMetricsResponse)
def admin_metrics(tenant: TenantConfig = Depends(get_admin_tenant)) -> AdminMetricsResponse:
    """API-side counterpart to the Streamlit sidebar's admin dashboard
    (Sprint 5) — an API-only tenant (website widget, Slack app, anything
    that only ever talks to this service, never opens the Streamlit app)
    had no way to see its own usage metrics until this endpoint existed.
    """
    from src.observability.admin_metrics import compute_tenant_metrics

    m = compute_tenant_metrics(tenant.airline)
    return AdminMetricsResponse(
        airline=m.airline,
        query_count=m.query_count,
        unanswered_count=m.unanswered_count,
        unanswered_rate=m.unanswered_rate,
        avg_confidence=m.avg_confidence,
        estimated_cost_usd=m.estimated_cost_usd,
    )


class EscalationOut(BaseModel):
    escalation_id: str
    correlation_id: str
    timestamp: str
    query: str
    confidence: float
    status: str
    contact_channel: str | None = None
    contact_value: str | None = None
    owner: str | None = None
    response: str | None = None
    responded_at: str | None = None


@app.get("/v1/admin/escalations", response_model=list[EscalationOut])
def admin_escalations(tenant: TenantConfig = Depends(get_admin_tenant)) -> list[EscalationOut]:
    """Pending human-review queue for the calling tenant only — a low-
    confidence/refused query never surfaces here for another airline."""
    entries = list_pending_escalations(tenant.airline)
    return [
        EscalationOut(
            escalation_id=e["escalation_id"],
            correlation_id=e["correlation_id"],
            timestamp=e["timestamp"],
            query=e["query"],
            confidence=e["confidence"],
            status=e["status"],
            contact_channel=e.get("contact_channel"),
            contact_value=e.get("contact_value"),
            owner=e.get("owner"),
            response=e.get("response"),
            responded_at=e.get("responded_at"),
        )
        for e in entries
    ]


class ClaimEscalationRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=100)


@app.post("/v1/admin/escalations/{escalation_id}/claim")
def admin_claim_escalation(
    escalation_id: str, req: ClaimEscalationRequest, tenant: TenantConfig = Depends(get_admin_tenant),
) -> dict:
    """Mark this escalation as one a named agent is working — a "who's on
    it" marker so two agents don't duplicate the same follow-up, not a
    lock. `owner` is a free-text agent name/id; admin auth here is
    airline-level, not per-staff, so there is no verified identity to use
    instead."""
    claimed = claim_escalation(escalation_id, tenant.airline, req.owner)
    if not claimed:
        raise HTTPException(status_code=404, detail="Escalation not found for this tenant.")
    return {"escalation_id": escalation_id, "owner": req.owner}


class ResolveEscalationRequest(BaseModel):
    response: str | None = Field(default=None, max_length=4000)


@app.post("/v1/admin/escalations/{escalation_id}/resolve")
def admin_resolve_escalation(
    escalation_id: str, req: ResolveEscalationRequest = ResolveEscalationRequest(),
    tenant: TenantConfig = Depends(get_admin_tenant),
) -> dict:
    """Resolve an escalation, optionally recording the human agent's
    written response. Recording a response here does not send it to the
    passenger — there is no outbound email/SMS integration in this
    environment (see src/escalation/queue.py); an airline's own follow-up
    process must actually reach out using the contact info attached via
    the public contact-info endpoint below."""
    resolved = resolve_escalation(escalation_id, tenant.airline, response=req.response)
    if not resolved:
        raise HTTPException(status_code=404, detail="Escalation not found for this tenant.")
    return {"escalation_id": escalation_id, "status": "resolved"}


class ContactInfoRequest(BaseModel):
    channel: str = Field(..., description=f"One of {VALID_CONTACT_CHANNELS}")
    value: str = Field(..., min_length=1, max_length=200)


@app.post("/v1/public/escalations/{correlation_id}/contact")
def public_attach_contact_info(
    correlation_id: str, req: ContactInfoRequest, request: Request,
) -> dict:
    """Let a passenger whose query was refused/escalated leave contact info
    for human follow-up, identified only by the correlation_id their own
    query response already carried — the same random, server-generated,
    per-request id, never an escalation_id they were never given. Public
    and unauthenticated by design, matching /v1/public/query; rate-limited
    the same way."""
    _check_rate_limit("public:global")
    _check_rate_limit("public:" + (request.client.host if request.client else "unknown"))
    if req.channel not in VALID_CONTACT_CHANNELS:
        raise HTTPException(status_code=400, detail=f"channel must be one of {VALID_CONTACT_CHANNELS}")
    try:
        attached = attach_contact_info(correlation_id, req.channel, req.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not attached:
        raise HTTPException(
            status_code=404,
            detail="No pending escalation found for this correlation_id — it may not have been refused, "
                   "or has already been resolved.",
        )
    return {"correlation_id": correlation_id, "status": "contact info recorded"}


class FeedbackRequest(BaseModel):
    rating: str = Field(..., description=f"One of {VALID_RATINGS}")
    comment: str | None = Field(default=None, max_length=1000)


@app.post("/v1/public/feedback/{correlation_id}")
def public_submit_feedback(
    correlation_id: str, req: FeedbackRequest, request: Request,
) -> dict:
    """Let whoever made a query rate the answer thumbs up/down, identified
    only by the correlation_id their own query response already carried —
    same trust model as the contact-info endpoint above. The airline this
    feedback counts toward is looked up server-side from the query log,
    never taken from the request, so a caller can't attribute feedback to
    another tenant. Public and unauthenticated by design, matching
    /v1/public/query; rate-limited the same way. A second submission for
    the same correlation_id replaces the first."""
    _check_rate_limit("public:global")
    _check_rate_limit("public:" + (request.client.host if request.client else "unknown"))
    if req.rating not in VALID_RATINGS:
        raise HTTPException(status_code=400, detail=f"rating must be one of {VALID_RATINGS}")
    try:
        record_feedback(correlation_id, req.rating, req.comment)
    except UnknownCorrelationIdError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"correlation_id": correlation_id, "status": "feedback recorded"}


@app.get("/v1/admin/feedback")
def admin_feedback(tenant: TenantConfig = Depends(get_admin_tenant)) -> dict:
    """Recent feedback and an aggregate summary for the calling tenant
    only — never another airline's."""
    return {
        "summary": compute_feedback_summary(tenant.airline),
        "recent": list_recent_feedback(tenant.airline),
    }


@app.post("/v1/query", response_model=QueryResponse)
def query(
    req: QueryRequest, background_tasks: BackgroundTasks, tenant: TenantConfig = Depends(get_tenant),
) -> QueryResponse:
    _check_rate_limit(tenant.tenant_id)
    response = answer_query(req, tenant)
    if not response.refused:
        background_tasks.add_task(record_query_usage, tenant.tenant_id, response.correlation_id)
    return response


@app.post("/v1/public/query", response_model=QueryResponse)
def public_query(req: QueryRequest, request: Request) -> QueryResponse:
    # Limit aggregate spend as well as per-client use. Never trust a client-
    # supplied forwarding header to select a rate-limit identity.
    _check_rate_limit("public:global")
    _check_rate_limit("public:" + (request.client.host if request.client else "unknown"))
    return answer_query(req)


def answer_query(req: QueryRequest, tenant: TenantConfig | None = None) -> QueryResponse:
    if not ensure_pipeline():
        raise HTTPException(status_code=503, detail="Service temporarily unavailable. Try again shortly.",
                            headers={"Retry-After": "5"})


    airline = tenant.airline if tenant else "all"
    is_valid, reason, _issues = QueryValidator.validate_input(req.query, airline)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Query rejected: {reason}")

    correlation_id = str(uuid.uuid4())
    logger.info("api query received", tenant=tenant.tenant_id if tenant else "public", correlation_id=correlation_id)

    history = [h.model_dump() for h in req.history]
    if tenant:
        state = run_agent_for_tenant(
            req.query, _pipeline["graph"], tenant, correlation_id=correlation_id, history=history,
        )
    else:
        state = run_agent(req.query, _pipeline["graph"], airline="all",
                          correlation_id=correlation_id, history=history)

    if state.get("stage_error") in {"embedding", "retrieval", "generation"}:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable. Try again shortly.",
                            headers={"Retry-After": "5"})

    return QueryResponse(
        answer=state["answer"],
        refused=state.get("refused", False),
        confidence=state["confidence"],
        sources=[
            SourceOut(
                title=c["metadata"].get("title", ""),
                category=c["metadata"].get("category", ""),
                score=round(c.get("score", 0.0), 3),
                source_doc_id=c["metadata"].get("source_doc_id", ""),
                section=c["metadata"]["chunk_index"] + 1
                if isinstance(c["metadata"].get("chunk_index"), int)
                else None,
                source_url=c["metadata"].get("source_url"),
            )
            for c in state["retrieved_chunks"]
        ],
        correlation_id=correlation_id,
    )
