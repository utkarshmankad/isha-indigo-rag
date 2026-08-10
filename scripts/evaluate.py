"""RAGAS evaluation harness (S3-T2).

Runs the golden Q&A set (eval/golden_qa.py) through the real agent pipeline
and scores it with RAGAS: faithfulness, answer_relevancy, context_precision,
context_recall. Writes a JSON report and exits non-zero if any metric drops
below its gate threshold, so this doubles as the CI quality gate (S3-T5).

Usage:
    uv run python scripts/evaluate.py [--out eval/report.json]

Requires OPENAI_API_KEY and a reachable Qdrant instance (RAGAS itself also
calls an LLM as judge, so this hits real APIs — not run in unit tests).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

# Gate thresholds — below these, the pipeline is regressing and CI should fail.
GATE_THRESHOLDS = {
    "faithfulness": 0.70,
    "answer_relevancy": 0.70,
    "context_precision": 0.60,
    "context_recall": 0.60,
}


def run_pipeline_over_golden_set():
    from data.indigo_documents import DOCUMENTS
    from src.agent.graph import build_graph, run_agent
    from src.embedding.vector_store import QdrantVectorStore
    from src.ingestion.chunker import ingest_all
    from eval.golden_qa import GOLDEN_QA

    chunks = ingest_all(DOCUMENTS)
    store = QdrantVectorStore()
    graph = build_graph(chunks, store)

    records = []
    for item in GOLDEN_QA:
        state = run_agent(item["query"], graph, airline=item["airline"])
        contexts = [c["text"] for c in state["retrieved_chunks"]] or [""]
        records.append({
            "query": item["query"],
            "airline": item["airline"],
            "expect_refusal": item.get("expect_refusal", False),
            "confidence": state["confidence"],
            "answer": state["answer"],
            "contexts": contexts,
            "reference": item["reference"],
        })
    return records


def score_with_ragas(records: list[dict]) -> dict:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    dataset = Dataset.from_list([
        {
            "question": r["query"],
            "answer": r["answer"],
            "contexts": r["contexts"],
            "ground_truth": r["reference"],
        }
        for r in records
    ])

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )
    return {k: float(v) for k, v in result.items() if isinstance(v, (int, float))}


def check_refusal_behavior(records: list[dict]) -> tuple[int, int]:
    """Sanity check independent of RAGAS: out-of-scope queries must refuse."""
    expected = [r for r in records if r["expect_refusal"]]
    correct = sum(1 for r in expected if "could not find this" in r["answer"].lower())
    return correct, len(expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eval/report.json")
    args = parser.parse_args()

    print("Running golden Q&A set through the agent pipeline...")
    records = run_pipeline_over_golden_set()

    refusal_correct, refusal_total = check_refusal_behavior(records)
    print(f"Refusal behavior: {refusal_correct}/{refusal_total} out-of-scope queries correctly refused")

    print("Scoring with RAGAS (this calls the LLM judge, may take a minute)...")
    scores = score_with_ragas(records)

    report = {
        "scores": scores,
        "gate_thresholds": GATE_THRESHOLDS,
        "refusal_correct": refusal_correct,
        "refusal_total": refusal_total,
        "n_queries": len(records),
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nReport written to {args.out}")

    print("\n--- RAGAS scores ---")
    failed = []
    for metric, threshold in GATE_THRESHOLDS.items():
        value = scores.get(metric)
        status = "PASS" if value is not None and value >= threshold else "FAIL"
        if status == "FAIL":
            failed.append(metric)
        print(f"  {metric:<20} {value if value is not None else 'n/a':<10} (gate: >= {threshold})  [{status}]")

    if refusal_correct < refusal_total:
        failed.append("refusal_behavior")
        print(f"  refusal_behavior     {refusal_correct}/{refusal_total}  [FAIL]")

    if failed:
        print(f"\nGATE FAILED: {', '.join(failed)}")
        sys.exit(1)

    print("\nGATE PASSED")


if __name__ == "__main__":
    main()
