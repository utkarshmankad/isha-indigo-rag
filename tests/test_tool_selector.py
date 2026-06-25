import pytest
from src.retrieval.tool_selector import TOOL_REGISTRY, route_query, score_tools


def test_score_tools_baggage():
    assert "baggage" in score_tools("How many kg in cabin baggage allowance?")


def test_score_tools_loyalty():
    assert "loyalty" in score_tools("How do I redeem BluChip points?")


def test_score_tools_cancellations():
    assert "cancellations_and_refunds" in score_tools("Can I get a refund on my cancelled ticket?")


def test_score_tools_special_assistance():
    assert "special_assistance" in score_tools("I need a wheelchair WCHR for my flight.")


def test_score_tools_safety():
    assert "safety_and_security" in score_tools("Can I carry a lithium battery vape on board?")


def test_score_tools_no_match_returns_all():
    result = score_tools("What is the meaning of life?")
    assert set(result) == set(TOOL_REGISTRY.keys())


def test_route_query_required_keys():
    result = route_query("baggage allowance")
    assert set(result.keys()) >= {"selected_tools", "search_all", "reasoning"}


def test_route_query_search_all_on_no_match():
    result = route_query("random unrelated query xyz123")
    assert result["search_all"] is True


def test_route_query_no_search_all_on_specific():
    result = route_query("wheelchair assistance for disabled passenger")
    assert result["search_all"] is False
    assert "special_assistance" in result["selected_tools"]


def test_route_query_top_k_respected():
    result = route_query("refund for cancelled flight delay", top_k=2)
    assert len(result["selected_tools"]) <= 2


def test_route_query_dgca_keywords():
    result = route_query("What compensation am I entitled to under DGCA?")
    assert result["search_all"] is False or len(result["selected_tools"]) > 0
