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
from collections import defaultdict
from contextlib import asynccontextmanager
from threading import Lock

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agent.graph import run_agent_for_tenant
from src.billing.stripe_usage import record_query_usage
from src.observability.logging_config import get_logger
from src.security.validator import QueryValidator
from src.tenancy.registry import TenantConfig, authenticate_by_key

load_dotenv()

logger = get_logger("api.main")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_app_state()
    yield


app = FastAPI(title="ISHA API", version="0.1.0", lifespan=_lifespan)

# CORS wide open by default so a website widget on any origin can call this
# endpoint — the API key is the actual access control, not same-origin.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["POST", "GET"], allow_headers=["*"],
)

_QPM_LIMIT = 30
_rate_lock = Lock()
_query_times: dict[str, list[float]] = defaultdict(list)

_pipeline: dict = {}


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
    store = QdrantVectorStore()
    if store.stats()["total_vectors"] == 0:
        raise RuntimeError(
            "Qdrant collection is empty. Run: uv run python scripts/ingest.py --reset"
        )
    _pipeline["graph"] = build_graph(chunks, store)


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
    section: int | None = None


class QueryResponse(BaseModel):
    answer: str
    confidence: float
    sources: list[SourceOut]
    correlation_id: str


def _check_rate_limit(tenant_id: str) -> None:
    now = time.time()
    with _rate_lock:
        recent = [t for t in _query_times[tenant_id] if t > now - 60]
        if len(recent) >= _QPM_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
        recent.append(now)
        _query_times[tenant_id] = recent


def get_tenant(x_api_key: str = Header(..., alias="X-API-Key")) -> TenantConfig:
    tenant = authenticate_by_key(x_api_key)
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return tenant


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "pipeline_ready": "graph" in _pipeline}


class AdminMetricsResponse(BaseModel):
    airline: str
    query_count: int
    unanswered_count: int
    unanswered_rate: float
    avg_confidence: float
    estimated_cost_usd: float


@app.get("/v1/admin/metrics", response_model=AdminMetricsResponse)
def admin_metrics(tenant: TenantConfig = Depends(get_tenant)) -> AdminMetricsResponse:
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


@app.post("/v1/query", response_model=QueryResponse)
def query(
    req: QueryRequest, background_tasks: BackgroundTasks, tenant: TenantConfig = Depends(get_tenant),
) -> QueryResponse:
    if "graph" not in _pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not ready.")

    _check_rate_limit(tenant.tenant_id)

    is_valid, reason, _issues = QueryValidator.validate_input(req.query, tenant.airline)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Query rejected: {reason}")

    correlation_id = str(uuid.uuid4())
    logger.info("api query received", tenant=tenant.tenant_id, correlation_id=correlation_id)

    history = [h.model_dump() for h in req.history]
    state = run_agent_for_tenant(
        req.query, _pipeline["graph"], tenant, correlation_id=correlation_id, history=history,
    )

    # Billing is a side effect, reported after the response is prepared —
    # runs after the response is sent (BackgroundTasks), never adds latency
    # to the actual answer and never fails the request on a billing error.
    background_tasks.add_task(record_query_usage, tenant.tenant_id, correlation_id)

    return QueryResponse(
        answer=state["answer"],
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
            )
            for c in state["retrieved_chunks"]
        ],
        correlation_id=correlation_id,
    )
