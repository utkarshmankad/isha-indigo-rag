# Retrieval similarity and refusal

The API's existing `confidence` field is retained for compatibility. It is a
retrieval similarity heuristic, not a calibrated probability of answer correctness.
The UI labels it accordingly.

The score is the maximum finite cosine similarity among the selected passages
that fit the final prompt. BM25-normalized scores and RRF ranking scores are not
used as cosine confidence. Blank, absent and oversized passages do not support
confidence. Empty evidence always refuses; the pipeline may still generate a
hypothetical search expansion on retry, which is never returned as an answer.

The existing 0.65 retry and 0.35 refusal thresholds are retained pending a broader
held-out calibration, rather than lowering gates to mask failures. CI still runs
the existing RAGAS evaluation. Similarity on a HyDE retry reflects the expanded
retrieval query; a high score alone does not verify claims, exceptions or policy
freshness. Per-language and per-airline calibration remains part of evaluation.
