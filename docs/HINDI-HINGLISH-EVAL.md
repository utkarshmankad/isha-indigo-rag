# Hindi/Hinglish evaluation (Weeks 5-8, item 3b)

The system prompt (`src/retrieval/retriever.py`) has instructed the LLM
since Sprint 7 to answer in Hindi (Devanagari) when asked in Hindi or
Hinglish. Nothing had ever checked that this instruction actually holds,
or that retrieval/refusal behavior still work for non-English queries
against an English-only bundled corpus (`eval/golden_qa.py` has zero
Hindi/Hinglish coverage).

## What this adds

- `eval/hindi_hinglish_qa.py`: 6 queries mirroring existing golden-set
  topics — 2 in-scope + 1 out-of-scope in Devanagari, the same 2 topics +
  1 out-of-scope in Hinglish (romanized Hindi).
- `src/evaluation/language_check.py`: `contains_devanagari` and
  `answer_matches_devanagari_query` — pure, unit-tested, script-based
  checks with no LLM call.
- `scripts/evaluate_hindi.py`: runs the set through the real pipeline and
  reports three things — Devanagari language match, refusal behavior, and
  non-empty retrieval — writing `eval/hindi_report.json`.

## What this deliberately does not check

**Hinglish answer language.** Hinglish is romanized (Latin script), so
there is no script-based signal distinguishing an English answer from a
Hinglish one. Verifying that reliably would need a language-identification
model or another LLM-as-judge call. This script adds neither — Hinglish
queries are still run and checked for refusal behavior and non-empty
retrieval, just not answer-language correctness. If Hinglish language
match becomes something the team wants measured, that's a real scope
increase (a judge call, ideally batched with the existing RAGAS judge
calls in `scripts/evaluate.py`), not a small addition to this script.

## Why this isn't a CI gate

`scripts/evaluate.py` already runs one full LLM-judged evaluation pass per
PR (RAGAS) and is a blocking quality gate. Adding a second pipeline run
(this script) as a second blocking gate would roughly double eval-related
CI time and OpenAI spend for what is, right now, informational coverage —
6 queries is not enough queries to calibrate a meaningful pass/fail
threshold the way `GATE_THRESHOLDS` in `scripts/evaluate.py` was
calibrated against a real baseline run. Run it manually
(`uv run python scripts/evaluate_hindi.py`) for now; wiring it into CI as
an actual gate is a reasonable follow-up once there's a larger Hindi/
Hinglish set and a calibrated baseline, not something to fake here.

## Live run finding (2026-09-16)

Running `scripts/evaluate_hindi.py` against the live pipeline found a real
issue: both in-scope Devanagari queries were refused (confidence 0.265 and
0.284, below `REFUSAL_FLOOR=0.35` in `src/agent/graph.py`) even though 5
chunks were retrieved for each. The same two questions asked in Hinglish
(romanized) retrieved with confidence 0.783 and 0.673 and answered
correctly. This means the failure isn't the language-instruction in the
system prompt — the LLM never got a chance to apply it, because the
confidence-based refusal path fired first. The likely cause is Devanagari
script text embedding less similarly to the (English-only) bundled corpus
than the same content transliterated to Latin script, dragging the
evidence-similarity score below the refusal floor. `evaluate_hindi.py`
distinguishes this ("mismatch via refusal path") from a genuine wrong-
language LLM answer ("mismatch via wrong language") specifically so this
kind of root cause isn't hidden behind one pass/fail number.

This is a real product gap (Devanagari-script queries are worse-served
than the same questions in Hinglish or English) but fixing embedding/
confidence calibration for cross-script retrieval is separate, larger,
not-yet-authorized scope — this item delivers the tooling that surfaced
it, not the fix.

## Scope

This is evaluation tooling only — it does not change how ISHA answers
Hindi/Hinglish queries, only whether anyone can tell if the existing
instruction is working. User feedback collection (thumbs up/down) is
separate, not yet started.
