from src.agent.guided_questions import build_exception_guidance


def test_baggage_query_missing_both_slots_mentions_both():
    guidance = build_exception_guidance(["baggage"], "indigo", "what is my baggage allowance?")
    assert guidance is not None
    assert "fare class" in guidance
    assert "domestic or international" in guidance


def test_baggage_query_with_fare_class_only_mentions_route():
    guidance = build_exception_guidance(["baggage"], "indigo", "6E Prime baggage allowance")
    assert guidance is not None
    assert "depends on whether the flight is domestic or international" in guidance
    assert "depends on fare class" not in guidance


def test_baggage_query_with_route_only_mentions_fare_class():
    guidance = build_exception_guidance(["baggage"], "indigo", "baggage allowance for international flight")
    assert guidance is not None
    assert "depends on fare class" in guidance
    assert "depends on whether the flight is domestic or international" not in guidance


def test_baggage_query_with_both_slots_returns_none():
    guidance = build_exception_guidance(
        ["baggage"], "indigo", "6E Prime baggage allowance for international flights",
    )
    assert guidance is None


def test_disruption_query_missing_route_mentions_it():
    guidance = build_exception_guidance(
        ["flight_delays_and_cancellations"], "indigo", "my flight was cancelled, what am I owed?",
    )
    assert guidance is not None
    assert "domestic or international" in guidance


def test_disruption_query_with_route_returns_none():
    guidance = build_exception_guidance(
        ["cancellations_and_refunds"], "indigo", "my domestic flight was cancelled, what am I owed?",
    )
    assert guidance is None


def test_selected_all_tools_never_triggers_guidance():
    """route_query returns every tool (not an empty list) when nothing
    category-specific matched — len(selected_tools) == 1 is what signals
    a single confident category, so a full/near-full tool list correctly
    yields no guidance."""
    guidance = build_exception_guidance(
        ["baggage", "check_in", "fares_and_ticketing", "cancellations_and_refunds"], "indigo", "help me",
    )
    assert guidance is None


def test_multiple_selected_tools_never_triggers_guidance():
    guidance = build_exception_guidance(["baggage", "check_in"], "indigo", "baggage and check-in help")
    assert guidance is None


def test_unrelated_category_never_triggers_guidance():
    guidance = build_exception_guidance(["loyalty"], "indigo", "how do BluChip points work?")
    assert guidance is None


def test_all_airline_uses_generic_fare_class_keywords_across_airlines():
    guidance = build_exception_guidance(["baggage"], "all", "6E Prime baggage allowance")
    assert guidance is not None
    assert "depends on whether the flight is domestic or international" in guidance
    assert "depends on fare class" not in guidance  # "6E Prime" matched via the combined keyword list


def test_guidance_never_blocks_a_normal_answer():
    """Regression: an earlier version of this feature returned a
    clarifying QUESTION meant to short-circuit retrieval entirely — that
    broke the golden eval set and several tests because common queries
    like "what is the baggage limit" never got answered. This function
    must only ever return prompt text to append, never something that
    could plausibly replace the final answer."""
    guidance = build_exception_guidance(["baggage"], "indigo", "what is my baggage allowance?")
    assert guidance.startswith("\n\nIMPORTANT:")
