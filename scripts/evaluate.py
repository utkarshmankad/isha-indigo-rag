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
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()


def _patch_ragas_vertexai_import() -> None:
    """ragas==0.4.x eager-imports `langchain_community.chat_models.vertexai`,
    a submodule that package dropped in its 0.4.x line (Vertex AI support
    moved to the standalone `langchain-google-vertexai` package). We never
    use Vertex AI (OpenAI only), so stub the missing shim module with the
    real class from `langchain-google-vertexai` purely to satisfy the import.
    """
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return
    try:
        import langchain_community.chat_models.vertexai  # noqa: F401
        return  # shim already present, nothing to patch
    except ModuleNotFoundError:
        pass

    from langchain_google_vertexai import ChatVertexAI

    stub = types.ModuleType(module_name)
    stub.ChatVertexAI = ChatVertexAI
    sys.modules[module_name] = stub


_patch_ragas_vertexai_import()

# Gate thresholds — below these, the pipeline is regressing and CI should fail.
# Calibrated 2026-08-10 against the real IndiGo corpus + golden set: measured
# baseline was faithfulness=0.83, answer_relevancy=0.81, context_precision=0.72,
# context_recall=0.52. context_recall's gate sits below the other three because
# it's currently the retrieval pipeline's weakest metric (S4+ retrieval work
# should raise it) — set with a small margin under baseline, not aspirationally.
GATE_THRESHOLDS = {
    "faithfulness": 0.70,
    "answer_relevancy": 0.70,
    "context_precision": 0.60,
    "context_recall": 0.45,
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
    from langchain_openai import OpenAIEmbeddings
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
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

    # ragas's default embedding_factory() returns a provider incompatible with
    # the legacy embed_query() interface some metrics (answer_relevancy) still
    # call — pass a LangChain-wrapped embedder explicitly to sidestep that.
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings())

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        embeddings=embeddings,
    )
    scores_df = result.to_pandas()
    metric_names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    return {m: float(scores_df[m].mean()) for m in metric_names if m in scores_df.columns}


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
