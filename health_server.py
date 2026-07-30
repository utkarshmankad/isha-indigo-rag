"""
Standalone health check HTTP server for ISHA.

Streamlit doesn't expose custom routes, so this small FastAPI app runs
alongside it to give infra (load balancers, uptime checks, k8s probes)
a real /health endpoint.

Run: uv run uvicorn health_server:app --host 0.0.0.0 --port 8000
"""

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

load_dotenv()

from src.observability.health import run_health_checks

app = FastAPI(title="ISHA Health API")


@app.get("/health")
def health() -> JSONResponse:
    result = run_health_checks()
    status_code = 200 if result["status"] == "ok" else 503
    return JSONResponse(content=result, status_code=status_code)
