"""Hindi/Hinglish evaluation (Weeks 5-8 item 3b).

The system prompt (src/retrieval/retriever.py) instructs the LLM to answer
in Hindi (Devanagari) when asked in Hindi or Hinglish. Nothing had ever
checked that this instruction actually holds, or that retrieval and
refusal behavior still work correctly for non-English queries against an
English-only bundled corpus.

Checks, run against eval/hindi_hinglish_qa.py:
1. Devanagari-script queries get a Devanagari-script answer
   (src/evaluation/language_check.py — a reliable script-based check).
2. Out-of-scope queries (in either script) still trigger refusal, not a
   hallucinated answer.
3. In-scope queries still retrieve at least one chunk (sanity check that
   embedding-based retrieval isn't silently failing on non-English text).

Hinglish answer-language is NOT checked — Latin script alone can't
distinguish an English answer from a Hinglish one, and verifying that
reliably would need a language-identification model or another LLM judge
call. This script deliberately doesn't add either; Hinglish queries are
still run and checked for #2 and #3 above, just not #1.

This is NOT wired into the CI quality gate (scripts/evaluate.py, which
RAGAS-scores and blocks merges). It hits real OpenAI + Qdrant a second
time; running it as a blocking gate on every PR was judged not worth the
added CI time/cost for what is currently informational-only coverage. Run
manually, or wire into CI separately if this is to become a blocking gate.

Usage: uv run python scripts/evaluate_hindi.py [--out eval/hindi_report.json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()


def run_pipeline_over_hindi_set() -> list[dict]:
    # Full bundled corpus, matching src/api/main.py's init_app_state and
    # scripts/evaluate.py — see docs/EVAL-CORPUS-ALIGNMENT.md. HINDI_HINGLISH_QA
    # is IndiGo-scoped today, so this had no visible effect on this script's
    # own results yet, but keeps every eval entrypoint consistent with what's
    # actually deployed rather than each one picking its own subset.
    from data.air_india_documents import DOCUMENTS as AI_DOCS
    from data.dgca_documents import DOCUMENTS as DGCA_DOCS
    from data.indigo_documents import DOCUMENTS as INDIGO_DOCS
    from data.spicejet_documents import DOCUMENTS as SJ_DOCS
    from eval.hindi_hinglish_qa import HINDI_HINGLISH_QA
    from src.agent.graph import build_graph, run_agent
    from src.embedding.vector_store import QdrantVectorStore
    from src.ingestion.chunker import ingest_all

    all_docs = INDIGO_DOCS + AI_DOCS + SJ_DOCS + DGCA_DOCS
    chunks = ingest_all(all_docs)
    store = QdrantVectorStore()
    graph = build_graph(chunks, store)

    records = []
    for item in HINDI_HINGLISH_QA:
        state = run_agent(item["query"], graph, airline=item["airline"])
        records.append({
            "query": item["query"],
            "script": item["script"],
            "airline": item["airline"],
            "expect_refusal": item.get("expect_refusal", False),
            "answer": state["answer"],
            "refused": state.get("refused", False),
            "confidence": state["confidence"],
            "retrieved_chunk_count": len(state["retrieved_chunks"]),
        })
    return records


def score(records: list[dict]) -> dict:
    from src.evaluation.language_check import answer_matches_devanagari_query

    devanagari_records = [r for r in records if r["script"] == "devanagari" and not r["expect_refusal"]]
    language_match_correct = sum(
        1 for r in devanagari_records if answer_matches_devanagari_query(r["query"], r["answer"])
    )
    # A language mismatch can happen two different ways worth telling
    # apart: the confidence-based refusal path fired (a fixed English
    # message, unrelated to the LLM's own language choice), or the LLM
    # itself generated an answer in the wrong language. The former points
    # at retrieval/confidence calibration for this script, the latter at
    # the system prompt's language instruction — different fixes.
    devanagari_mismatches = [
        r for r in devanagari_records if not answer_matches_devanagari_query(r["query"], r["answer"])
    ]
    devanagari_mismatches_via_refusal = sum(1 for r in devanagari_mismatches if r.get("refused"))

    expected_refusals = [r for r in records if r["expect_refusal"]]
    refusal_correct = sum(1 for r in expected_refusals if "could not find this" in r["answer"].lower())

    in_scope = [r for r in records if not r["expect_refusal"]]
    retrieval_nonempty = sum(1 for r in in_scope if r["retrieved_chunk_count"] > 0)

    return {
        "devanagari_language_match": {"correct": language_match_correct, "total": len(devanagari_records)},
        "devanagari_mismatches_via_refusal_path": devanagari_mismatches_via_refusal,
        "devanagari_mismatches_via_wrong_language": len(devanagari_mismatches) - devanagari_mismatches_via_refusal,
        "refusal_behavior": {"correct": refusal_correct, "total": len(expected_refusals)},
        "retrieval_nonempty": {"correct": retrieval_nonempty, "total": len(in_scope)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="eval/hindi_report.json")
    args = parser.parse_args()

    print("Running Hindi/Hinglish set through the agent pipeline...")
    records = run_pipeline_over_hindi_set()
    results = score(records)

    report = {"results": results, "records": records}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport written to {args.out}")

    print("\n--- Hindi/Hinglish evaluation ---")
    failed = []
    gated_checks = ("devanagari_language_match", "refusal_behavior", "retrieval_nonempty")
    for name in gated_checks:
        r = results[name]
        status = "PASS" if r["correct"] == r["total"] else "FAIL"
        if status == "FAIL":
            failed.append(name)
        print(f"  {name:<28} {r['correct']}/{r['total']}  [{status}]")

    if results["devanagari_language_match"]["correct"] < results["devanagari_language_match"]["total"]:
        print(
            f"    of which via refusal path: {results['devanagari_mismatches_via_refusal_path']}  "
            f"(low retrieval/routing confidence, not a language-instruction failure)"
        )
        print(
            f"    of which wrong-language answer: {results['devanagari_mismatches_via_wrong_language']}  "
            f"(the LLM answered but not in Devanagari)"
        )

    if failed:
        print(f"\nSome checks failed: {', '.join(failed)} (informational — not a CI gate)")
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
