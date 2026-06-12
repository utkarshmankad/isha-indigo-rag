# ISHA — IndiGo Smart Helpdesk Assistant

A RAG-based virtual assistant for IndiGo Airlines passenger queries. Built with LangGraph, Qdrant, BM25 hybrid search, and Claude/OpenAI for answer generation.

## Architecture

```
User query
  → Tool selector (keyword routing + DGCA force-include)
  → Hybrid retrieval (BM25 + Qdrant vector, RRF fusion)
  → Confidence gate (re-retrieval if < 0.65)
  → LLM answer (Anthropic claude-opus-4-8 → OpenAI gpt-4o-mini fallback)
  → Structured logging (logs/query_log.jsonl)
```

## Local Setup

```bash
# 1. Clone and install
git clone <repo-url>
cd isha-indigo-rag
uv sync

# 2. Copy and fill credentials
cp .env.example .env
# edit .env with your keys

# 3. Ingest documents into Qdrant (one-time)
uv run python scripts/ingest.py --reset --verify

# 4. Run the app
streamlit run app.py
```

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | For embeddings (text-embedding-3-small) |
| `ANTHROPIC_API_KEY` | For answer generation (claude-opus-4-8) |
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key |

## Deployment

### Streamlit Community Cloud

1. **Push repo to GitHub** (public repository)

2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
   - Select your repo
   - Set main file path: `app.py`

3. **Advanced settings → Secrets** — paste your real credentials:
   ```toml
   OPENAI_API_KEY = "sk-..."
   ANTHROPIC_API_KEY = "sk-ant-..."
   QDRANT_URL = "https://your-cluster.cloud.qdrant.io"
   QDRANT_API_KEY = "your-qdrant-key"
   ```
   (See `.streamlit/secrets.toml.example` for the template.)

4. Click **Deploy**

> **IMPORTANT:** Before first use, run ingestion locally to populate Qdrant Cloud:
> ```bash
> uv run python scripts/ingest.py --reset --verify
> ```
> The deployed app reads from Qdrant Cloud but **never runs ingestion itself** — only `scripts/ingest.py` does. This is a one-time step per Qdrant collection.

### Cost Summary

| Item | Cost |
|---|---|
| Qdrant Cloud (1 GB free tier) | $0 |
| Streamlit Community Cloud | $0 |
| OpenAI embeddings (ingestion, one-time) | ~$0.001 |
| OpenAI embeddings (per query) | ~$0.0000004 |
| Claude Opus 4.8 (per answer) | ~$0.002/query |
| Est. 500 demo queries/month | ~$1–3/month |

## Observability

Query logs written to `logs/query_log.jsonl`. Print a summary:

```bash
uv run python -c "from src.observability.logger import print_summary; print_summary()"
```

## Project Structure

```
app.py                      # Streamlit UI
src/
  agent/graph.py            # LangGraph orchestrator
  retrieval/
    hybrid_search.py        # BM25 + vector RRF fusion
    tool_selector.py        # Keyword-based category routing
    retriever.py            # RetrievalEngine + prompt builder
  embedding/
    embedder.py             # OpenAI text-embedding-3-small
    vector_store.py         # Qdrant client wrapper
  ingestion/chunker.py      # Document chunking
  observability/logger.py   # JSONL query logger
data/indigo_documents.py    # IndiGo policy source documents
scripts/ingest.py           # One-time ingestion script
```
