# Liveness, readiness and recovery

FastAPI `/live` reports that the process is serving requests. `/health` is a
readiness endpoint: it returns 503 until the configured Qdrant collection is
healthy/nonempty, the OpenAI key is configured and the graph is initialized.
Checking key presence is not a live OpenAI availability or billing check.

Startup failures leave the API available for health checks. Later health/query
requests retry initialization at most once every five seconds, with one initializer
per process. Existing graphs reconnect through ordinary HTTP requests after a
Qdrant restart. Retrieval/embedding/generation failures return 503 with Retry-After
instead of a successful policy refusal. Unanswerable policy questions remain a
normal response, distinct from infrastructure failures.

The Qdrant client uses 10-second request timeouts. Readiness performs two small
reads, so the total is not a 10-second end-to-end deadline. Startup may perform
additional bounded reads and build the local lexical index. No ingestion or
collection creation happens during application recovery. For missing data,
follow the recovery runbook; do not automatically reset/re-ingest.

Both the API and Streamlit honor QDRANT_COLLECTION (default airline_kb). A failed
Streamlit initialization shows a Retry connection button; cached startup status
is not a substitute for the dedicated readiness endpoint. The standalone
health_server uses the same Qdrant probe, but cannot certify another process's
graph readiness.
