from eval.hindi_hinglish_qa import HINDI_HINGLISH_QA
from scripts.evaluate_hindi import score


def test_hindi_hinglish_qa_entries_have_required_fields():
    for item in HINDI_HINGLISH_QA:
        assert item["query"]
        assert item["airline"]
        assert item["script"] in ("devanagari", "hinglish")
        assert "doc_ids" in item


def test_hindi_hinglish_qa_includes_both_scripts_and_a_refusal_case():
    scripts_present = {item["script"] for item in HINDI_HINGLISH_QA}
    assert scripts_present == {"devanagari", "hinglish"}
    assert any(item.get("expect_refusal") for item in HINDI_HINGLISH_QA)


def test_score_counts_language_match_only_for_in_scope_devanagari():
    records = [
        {"query": "देवनागरी प्रश्न", "script": "devanagari", "expect_refusal": False,
         "answer": "देवनागरी उत्तर", "retrieved_chunk_count": 2},
        {"query": "hinglish query", "script": "hinglish", "expect_refusal": False,
         "answer": "answer in english", "retrieved_chunk_count": 1},
    ]
    results = score(records)
    assert results["devanagari_language_match"] == {"correct": 1, "total": 1}
    assert results["retrieval_nonempty"] == {"correct": 2, "total": 2}


def test_score_flags_devanagari_answer_in_english_as_mismatch():
    records = [
        {"query": "देवनागरी प्रश्न", "script": "devanagari", "expect_refusal": False,
         "answer": "answer in english", "retrieved_chunk_count": 1},
    ]
    results = score(records)
    assert results["devanagari_language_match"] == {"correct": 0, "total": 1}


def test_score_distinguishes_refusal_path_mismatch_from_wrong_language_answer():
    records = [
        {"query": "देवनागरी प्रश्न 1", "script": "devanagari", "expect_refusal": False,
         "answer": "I could not find this in the policy documents.", "refused": True,
         "retrieved_chunk_count": 5},
        {"query": "देवनागरी प्रश्न 2", "script": "devanagari", "expect_refusal": False,
         "answer": "The answer is in English, not Hindi.", "refused": False,
         "retrieved_chunk_count": 5},
    ]
    results = score(records)
    assert results["devanagari_language_match"] == {"correct": 0, "total": 2}
    assert results["devanagari_mismatches_via_refusal_path"] == 1
    assert results["devanagari_mismatches_via_wrong_language"] == 1


def test_score_counts_refusal_behavior_across_scripts():
    records = [
        {"query": "फ्रांस की राजधानी क्या है?", "script": "devanagari", "expect_refusal": True,
         "answer": "I could not find this in the policy documents.", "retrieved_chunk_count": 0},
        {"query": "kaunsa stock accha hai?", "script": "hinglish", "expect_refusal": True,
         "answer": "made up stock advice", "retrieved_chunk_count": 0},
    ]
    results = score(records)
    assert results["refusal_behavior"] == {"correct": 1, "total": 2}


def test_score_excludes_expected_refusals_from_retrieval_check():
    records = [
        {"query": "out of scope", "script": "devanagari", "expect_refusal": True,
         "answer": "I could not find this in the policy documents.", "retrieved_chunk_count": 0},
    ]
    results = score(records)
    assert results["retrieval_nonempty"] == {"correct": 0, "total": 0}
