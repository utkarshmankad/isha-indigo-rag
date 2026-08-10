# Sprint 3: Trust Layer — Evaluation & Citations — Completion Checklist

**Status**: ✅ **COMPLETED** (eval harness untested against live APIs — see Testing)

---

## ✅ Task Execution Summary

### S3-T1: Golden Q&A Set

**New file**: `eval/golden_qa.py`

- 23 hand-curated queries against the real IndiGo doc set (`data/indigo_documents.py`),
  covering all 8 categories (baggage, check-in, fares, cancellations, delays,
  loyalty, special assistance) plus reference answers and source `doc_id`s.
- 2 cross-airline queries (Air India, SpiceJet) to check the pipeline doesn't
  break outside IndiGo.
- 3 deliberately out-of-scope queries (`expect_refusal=True`) — capital of
  France, stock tips, weather — to verify the refusal path (S3-T3) instead
  of hallucination.

### S3-T2: RAGAS Evaluation Harness

**New file**: `scripts/evaluate.py`

- Runs the golden set through the real `build_graph`/`run_agent` pipeline,
  collects `(question, answer, contexts, ground_truth)` per query.
- Scores with RAGAS: `faithfulness`, `answer_relevancy`, `context_precision`,
  `context_recall`.
- Independently checks refusal behavior (string match on the refusal
  message) since RAGAS metrics don't directly capture "correctly declined
  to answer."
- Writes `eval/report.json`, exits non-zero if any metric misses its gate
  threshold (`faithfulness`/`answer_relevancy` ≥ 0.70, `context_precision`/
  `context_recall` ≥ 0.60) or any out-of-scope query isn't refused.
- Requires `OPENAI_API_KEY` + reachable Qdrant — not run in the unit test
  suite, run manually or via CI: `uv run python scripts/evaluate.py`.

### S3-T3: Confidence-Based Refusal

**Modified**: `src/agent/graph.py`

- New `REFUSAL_FLOOR = 0.35` (matches `MIN_SCORE_REAL` in `retriever.py` —
  the same score below which individual chunks are already discarded as
  noise).
- `generate_node` now checks `confidence < REFUSAL_FLOOR` *before* calling
  the LLM: if retrieval found nothing usable, return the existing
  "I could not find this in the policy documents" message directly, skip
  the OpenAI call entirely (also cuts cost on unanswerable queries), and
  still log the query for observability.
- `should_continue` unaffected — retrieval still gets up to `MAX_ITERATIONS`
  attempts before generation is reached, refusal only fires if all attempts
  stay below the floor.

### S3-T4: Citation Surfacing

**Modified**: `app.py`

- `render_sources()` now also shows the source `doc_id` (e.g. `BAG-001`)
  alongside title and relevance score, so a support agent can trace an
  answer back to the exact policy document.
- **Scope note**: the source documents (`data/*.py`) are flat per-policy
  text blocks, not paginated PDFs — there's no page/section number to cite.
  True page-level citation needs the documents re-ingested from paginated
  source PDFs; doc-level citation is the honest ceiling on the current
  corpus. The system prompt already instructs the LLM to cite documents by
  name inline (pre-existing Sprint 1 behavior).

### S3-T5: CI Eval Gate

**New file**: `.github/workflows/eval-gate.yml`

- Runs `scripts/evaluate.py` on PRs to `main` (and manual dispatch), uploads
  `eval/report.json` as an artifact.
- **Not yet enforced**: needs `OPENAI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`
  added as repo secrets before it can actually run in CI — wiring is done,
  activation is a repo-settings step outside this sprint's file changes.

---

## Testing

- Full `pytest` suite: **51 tests pass** (50 prior + 1 new).
- New `tests/test_refusal.py`: mocks retrieval to force `confidence=0.0`,
  asserts the LLM (`generate_answer`) is never called and the refusal
  message is returned — verifies the cost-saving short-circuit without
  needing a live OpenAI key.
- `scripts/evaluate.py` **not** run end-to-end in this session — it needs a
  live `OPENAI_API_KEY` and Qdrant instance populated with the IndiGo
  corpus. Structurally verified (imports, dataset construction) but the
  actual RAGAS scores are unknown until someone runs it with real
  credentials.

## Security Review

- No new secrets introduced; CI workflow reads credentials only from GitHub
  Actions secrets, never inline.
- `.github/workflows/eval-gate.yml` uses no untrusted `github.event.*`
  input in any `run:` step — no injection surface.
- Refusal path logs queries the same way successful ones do (existing
  redaction filter from Sprint 2 already covers this log path).

## Carried Over / Next Steps

- Activate the CI gate: add `OPENAI_API_KEY`/`QDRANT_URL`/`QDRANT_API_KEY`
  as repo secrets, run `scripts/evaluate.py` once for real to get baseline
  scores, adjust `GATE_THRESHOLDS` if the real numbers land differently
  than the placeholder thresholds.
- Rate limiting still not wired into `app.py` for the RAGAS eval script
  itself if run against a shared Qdrant instance — not a concern for CI.

**Next Sprint**: Sprint 4 — Multi-Tenancy Core
