"""Guided baggage/disruption exception guidance (Weeks 5-8, item 1).

Baggage allowances and disruption entitlements both vary by facts the raw
query often doesn't include: baggage allowance varies by fare class (e.g.
IndiGo's Blue vs 6E Prime), and disruption compensation/rebooking rules
differ for domestic vs international flights (DGCA rules vs Montreal
Convention considerations). Left alone, a single free-text answer to an
under-specified question like "what's my baggage allowance?" either has to
hedge across every fare class at once, or silently pick one and risk being
wrong for the passenger's actual fare — neither surfaces the applicable
exceptions clearly.

This module does NOT block or delay retrieval, and does not ask a
clarifying question before answering — an earlier version of this feature
tried that (short-circuiting straight to a question, skipping retrieval
entirely) and broke the golden eval set and several existing tests, because
extremely common queries like "what is the baggage limit on IndiGo" would
never get answered at all, just re-asked. Instead, `build_exception_guidance`
returns an instruction appended to the generation prompt (same mechanism as
`DGCA_INSTRUCTION` in src/agent/graph.py) telling the LLM to explicitly
enumerate how the answer differs across whatever fare-class/route dimension
the query left unspecified, using only what's in the retrieved context —
one LLM call, same retrieval, same confidence/billing behavior as any other
query.

Scope: this is a small, deterministic keyword-based classifier, not an NLU
model — it only recognizes the specific fare class names and route
keywords listed below.
"""

BAGGAGE_CATEGORIES = {"baggage"}
DISRUPTION_CATEGORIES = {"flight_delays_and_cancellations", "cancellations_and_refunds"}

FARE_CLASS_KEYWORDS: dict[str, list[str]] = {
    "indigo": ["blue flex", "blue", "6e prime", "super6e"],
    "air_india": ["economy lite", "economy flex", "economy", "business"],
    "spicejet": ["spicesaver", "spiceflex", "spicemax"],
}
ROUTE_KEYWORDS = ["international", "domestic", "abroad", "overseas", "within india"]


def _mentions_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


def build_exception_guidance(
    selected_tools: list[str],
    airline: str,
    query_text: str,
) -> str | None:
    """Returns a generation-prompt addendum instructing the LLM to
    enumerate applicable exceptions, or None if not applicable — either
    the query already specifies the relevant fare class/route, the query
    spans multiple/no specific category, or the category has no such
    exception dimension.

    Only applies when exactly one category was confidently selected. A
    query that matched no specific keywords gets every category back
    (see route_query in src/retrieval/tool_selector.py) rather than an
    empty list, so `len(selected_tools) == 1` alone is a reliable signal
    for "one specific category, not a broad/ambiguous query" — no
    separate search_all flag needed here. (Note: AgentState's own
    `search_all` field gets overwritten by retrieve_node for retry
    expansion logic, so it can't be reused for this check by the time
    generate_node runs — selected_tools does not have that problem.)"""
    if len(selected_tools) != 1:
        return None

    category = selected_tools[0]
    has_route = _mentions_any(query_text, ROUTE_KEYWORDS)

    if category in BAGGAGE_CATEGORIES:
        fare_keywords = FARE_CLASS_KEYWORDS.get(airline, [kw for kws in FARE_CLASS_KEYWORDS.values() for kw in kws])
        has_fare = _mentions_any(query_text, fare_keywords)
        if has_fare and has_route:
            return None
        missing = []
        if not has_fare:
            missing.append("fare class")
        if not has_route:
            missing.append("whether the flight is domestic or international")
        return (
            "\n\nIMPORTANT: The passenger did not specify " + " or ".join(missing) + ". "
            "Baggage allowance varies by these — do not silently assume one option. If the "
            "context distinguishes allowances by fare class or route, briefly state each "
            "applicable option and note that the exact allowance depends on " + " and ".join(missing) + "."
        )

    if category in DISRUPTION_CATEGORIES and not has_route:
        return (
            "\n\nIMPORTANT: The passenger did not specify whether this is a domestic or "
            "international flight. Compensation and rebooking entitlements can differ between "
            "the two — if the context distinguishes them, cover both briefly and note that the "
            "exact entitlement depends on route type."
        )

    return None
