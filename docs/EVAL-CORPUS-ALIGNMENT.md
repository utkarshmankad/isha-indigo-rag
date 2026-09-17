# Align evaluation and deployed corpora (hardening backlog)

## The gap

`scripts/evaluate.py` and `scripts/evaluate_hindi.py` each built their
BM25 keyword index from `data.indigo_documents.DOCUMENTS` only, while
connecting to the same production Qdrant collection (`QdrantVectorStore()`
with no override) that `src/api/main.py`'s `init_app_state` and `app.py`'s
`init_pipeline` populate from **all four** document sets — IndiGo, Air
India, SpiceJet, and DGCA.

`eval/golden_qa.py` includes SpiceJet queries (e.g. "What is SpiceJet's
refund policy for cancelled tickets?"). During evaluation, hybrid
search's lexical (BM25) side had zero candidate chunks for any such
query — not degraded, literally empty, because SpiceJet's text was never
in the BM25 corpus the eval script built. Only the dense/vector side
(which reads from the shared production Qdrant collection) had anything
to retrieve. This meant:

- Evaluation results didn't represent what hybrid search actually does in
  production for non-IndiGo queries — a real mismatch between what was
  measured and what was deployed, understating whatever benefit BM25
  contributes for those queries.
- The RAGAS quality gate (`scripts/evaluate.py`, blocking on every PR)
  was silently exercising a narrower, IndiGo-only-BM25 pipeline instead of
  the actual deployed one.

## The fix

Both scripts now build BM25 from all four document sets
(`INDIGO_DOCS + AI_DOCS + SJ_DOCS + DGCA_DOCS`), matching
`init_app_state`/`init_pipeline` exactly.

Re-ran the real RAGAS gate with this change: faithfulness 0.80,
answer_relevancy 0.76, context_precision 0.71, context_recall 0.57 — all
pass, comparable to the calibrated baseline (0.83/0.81/0.72/0.52) and to
the pre-fix run from the previous PR (0.82/0.72/0.72/0.61) — run-to-run
LLM-judge variance of this size is expected and was already visible
between prior runs in this session; this wasn't a regression.

## `HINDI_HINGLISH_QA` wasn't actually affected yet

`eval/hindi_hinglish_qa.py`'s queries are all `airline="indigo"` or
`airline="all"` today — no SpiceJet/Air India-specific query exists there
yet, so `scripts/evaluate_hindi.py`'s own results didn't change measurably
from this fix. It was still corrected for consistency: every eval
entrypoint should build from the same corpus definition as what's
actually deployed, not each pick its own subset that happens to work for
today's query set.

## What this doesn't address

Dev-only manual smoke-test blocks (`if __name__ == "__main__":` sections
in `src/agent/graph.py`, `src/embedding/embedder.py`,
`src/retrieval/hybrid_search.py`) still load IndiGo documents only. Those
are intentionally scoped, ad hoc single-file demos a developer runs
directly for a quick manual check — not something that gates CI or claims
to represent production behavior — so they were left alone rather than
expanding this fix's scope beyond the actual evaluation-vs-deployed
mismatch.
