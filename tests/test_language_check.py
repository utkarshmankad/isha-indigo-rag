from src.evaluation.language_check import answer_matches_devanagari_query, contains_devanagari


def test_contains_devanagari_true_for_hindi_text():
    assert contains_devanagari("इंडिगो पर बैगेज की सीमा क्या है?") is True


def test_contains_devanagari_false_for_english_text():
    assert contains_devanagari("What is the baggage limit on IndiGo?") is False


def test_contains_devanagari_false_for_hinglish_romanized_text():
    """Hinglish is Latin script — no Devanagari signal to detect, by design."""
    assert contains_devanagari("IndiGo mein baggage ka weight limit kitna hai?") is False


def test_contains_devanagari_true_for_mixed_script():
    assert contains_devanagari("IndiGo baggage सीमा kitni hai?") is True


def test_answer_matches_devanagari_query_not_applicable_for_english_query():
    """Check is a no-op (True) when the query itself wasn't Devanagari —
    it only asserts something about Devanagari-in/Devanagari-out."""
    assert answer_matches_devanagari_query("What is the baggage limit?", "7 kg.") is True


def test_answer_matches_devanagari_query_not_applicable_for_hinglish_query():
    assert answer_matches_devanagari_query(
        "IndiGo baggage ka weight limit kitna hai?", "The limit is 7 kg.",
    ) is True


def test_answer_matches_devanagari_query_true_when_both_devanagari():
    assert answer_matches_devanagari_query(
        "इंडिगो पर बैगेज की सीमा क्या है?", "सीमा 7 किलोग्राम है।",
    ) is True


def test_answer_matches_devanagari_query_false_when_answer_is_english():
    assert answer_matches_devanagari_query(
        "इंडिगो पर बैगेज की सीमा क्या है?", "The limit is 7 kg.",
    ) is False
