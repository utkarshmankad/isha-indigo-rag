# Sprint 7: Intelligence Upgrades — Completion Checklist

**Status**: ✅ **COMPLETED**

---

## ✅ Task Execution Summary

### S7-T1: HyDE Query Rewriting

**Modified**: `src/agent/graph.py`

- On the retry pass only (confidence stayed below `CONFIDENCE_THRESHOLD`
  on the first attempt, iteration > 1): generate a short hypothetical
  policy-style passage via the LLM and embed *that* instead of the raw
  query. Hypothetical answers land closer to real policy text in embedding
  space than short/vague questions do.
- Scoped to the retry pass deliberately — the first attempt already
  succeeds most of the time (Sprint 3's measured baseline: faithfulness
  0.83, answer_relevancy 0.81), so paying an extra LLM call on every query
  isn't worth the latency/cost. It's spent only when the pipeline already
  needed a second attempt.
- BM25 keyword search is unaffected — it still searches the raw query
  text; only the vector-search embedding changes.
- Falls back to the raw (context-enriched, see S7-T2) query if the HyDE
  LLM call itself fails — doesn't crash the request.

### S7-T2: Conversation Memory

**Modified**: `src/agent/graph.py`, `src/retrieval/retriever.py`, `app.py`,
`src/api/main.py`

- `AgentState` gained a `history` field (list of `{role, content}` turns).
  `run_agent()` / `run_agent_for_tenant()` accept an optional `history`
  param; `RetrievalEngine.build_prompt()` folds the last
  `MAX_HISTORY_TURNS=4` turns into the prompt as a "PRIOR CONVERSATION"
  block, so a follow-up like "what about for international flights?" gets
  a coherent answer instead of a cold restart.
- Wired into `app.py`'s sidebar (last messages from `st.session_state`,
  excluding the just-submitted current turn) and into
  `src/api/main.py`'s `QueryRequest` (`history: list[HistoryTurn]`, capped
  at 10 turns) for API-side parity.

### S7-T3: Multilingual Support (Hindi)

**Modified**: `src/retrieval/retriever.py`

- One rule added to the existing system prompt: respond in the same
  language the question was written in (Hindi/Devanagari or Hinglish →
  Hindi, otherwise English), keeping policy terms untranslated.
- Deliberately did **not** build a separate translation pipeline —
  `gpt-4o-mini` already generates fluent Hindi natively; the gap was an
  instruction gap, not a capability gap. Live-verified (see Testing)
  rather than assumed.

---

## Testing

- Full `pytest` suite: **93 tests pass** (85 prior + 8 new in
  `tests/test_intelligence_upgrades.py`, plus one existing test in
  `tests/test_refusal.py` updated — see Bug Found below).
- New tests cover: HyDE not used on the first pass (no wasted LLM call),
  HyDE used and correctly changes the embedded text on retry, HyDE failure
  degrades to the raw query rather than crashing, `build_prompt` correctly
  includes/omits/caps the history block, the system prompt instructs
  language-matching, and the S7-T2/T1 interaction fix below.
- Live-verified against real Qdrant/OpenAI:
  - Hindi query ("IndiGo mein carry-on baggage ki weight limit kya hai?")
    → fluent, correct Hindi/Hinglish answer, confidence 0.80.
  - Conversation follow-up ("what about for international flights?" after
    a baggage-allowance turn) → correctly found and answered with
    international baggage rates, after the bug fix below (first attempt
    without the fix incorrectly refused).

## Bug Found & Fixed

Conversation memory as first implemented only reached the *generation*
prompt (`build_prompt`'s history block) — tool routing
(`select_tools_node`) and retrieval embedding (`retrieve_node`) still only
saw the raw current-turn query. Live-tested the follow-up scenario this
feature is meant to support and it failed: "what about for international
flights?" has no baggage-related keywords of its own, so tool routing fell
back to a full-corpus search and the embedding scored too low to find the
international baggage document, refusing outright. Conversation memory
had a display-only illusion of working (the LLM would have used the prior
turn's context if it ever got relevant chunks) without actually helping
retrieval find anything.

Fixed by folding the most recent user turn into both tool-routing input
and the retrieval embedding text (`_last_user_turn()` +
`query_with_context` in `graph.py`) — BM25 keyword search still uses the
untouched raw query, only the vector-search side and DGCA-keyword/tool
routing get the context boost. Re-ran the live follow-up test after the
fix: correctly returned international baggage rates by route/region.

## Security Review

- `history` accepted from API callers is capped at 10 turns × 2000 chars
  each (`QueryRequest.history`) — bounds prompt size and embedding cost
  regardless of what a caller sends.
- No new secrets or credential handling.
- HyDE-generated text is never shown to the user and never persisted
  beyond the single retrieval call — only real, grounded chunks feed the
  final answer.

## Carried Over / Next Steps

- Hindi support is English/Hindi only per the original roadmap's "at
  minimum" bar — Tamil/Telugu not attempted.
- History is currently client-supplied per request (Streamlit session
  state, or an API caller's own tracking) — no server-side conversation
  storage. Fine for the current single-process deployment; would need a
  session store for anything stateful across API replicas.
- HyDE's cost/latency tradeoff (only on retry) hasn't been measured
  against the Sprint 3 golden set — worth re-running `scripts/evaluate.py`
  to see if `context_recall` (the pipeline's known weak metric, 0.52
  baseline) improved.

**Next Sprint**: Sprint 8 — Monetization & GTM
