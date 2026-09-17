# Guided baggage/disruption exceptions (Weeks 5-8, item 1)

## Why

Baggage allowance varies by fare class (IndiGo Blue vs 6E Prime, Air
India Economy vs Business, ...), and disruption compensation/rebooking
rules can differ between domestic and international flights (DGCA rules
vs Montreal Convention considerations). A query like "what's my baggage
allowance?" doesn't say which fare class or route the passenger means, so
a single free-text answer either has to hedge across every option at once
or silently pick one and risk being wrong.

## What this does

`src/agent/guided_questions.py`'s `build_exception_guidance(selected_tools,
airline, query_text)` detects when a baggage or disruption query is
missing the fare-class/route information the real answer depends on, and
returns an instruction appended to the generation prompt (same mechanism
`DGCA_INSTRUCTION` already uses in `src/agent/graph.py`) telling the LLM
to enumerate the applicable options from the retrieved context rather than
picking one silently. It only fires when exactly one category was
confidently selected — `len(selected_tools) == 1`, since `route_query`
(`src/retrieval/tool_selector.py`) returns *every* tool, not an empty
list, when nothing category-specific matched, so that length check alone
distinguishes "one specific topic" from "broad/ambiguous query."

## What this deliberately does NOT do

An earlier version of this feature tried a different design: detect the
same missing-slot condition in `select_tools_node`, and short-circuit the
whole graph straight to a clarifying *question*, skipping retrieval and
generation entirely for that turn. That broke 8 existing tests and would
have broken `eval/golden_qa.py`'s RAGAS gate — extremely common queries
like "What is the carry-on baggage weight limit on IndiGo?" would never
get answered, only re-asked, because `state["search_all"]`'s value by the
time it would be checked is not what it looks like either (see the code
comment in `guided_questions.py` — `retrieve_node` overwrites that field
for its own retry-expansion logic partway through the graph). That
approach was reverted. This module only ever appends prompt text; it
never changes retrieval, confidence, refusal, or billing behavior, and it
adds no extra LLM call, no extra state field, and no new graph edge.

Verified by running the real RAGAS gate (`scripts/evaluate.py`) with this
change in place: faithfulness 0.82, answer_relevancy 0.72, context_precision
0.72, context_recall 0.61 — all pass, comparable to or above the
calibrated baseline (0.83/0.81/0.72/0.52).

## Scope and limits

- **Deterministic keyword matching, not NLU.** Only recognizes the exact
  fare-class names and route keywords listed in `FARE_CLASS_KEYWORDS`/
  `ROUTE_KEYWORDS`. A passenger who phrases their fare class or route
  differently (a synonym, a typo, a different language) won't be
  recognized, and the guidance will fire even though the passenger did
  specify something.
- **Baggage and disruption categories only.** No guidance for other
  categories (loyalty, check-in, etc.) — those don't have an established
  fare-class/route exception dimension in the bundled corpus.
- **A guidance instruction, not a guarantee.** It tells the LLM to
  enumerate applicable options *if the retrieved context supports it* —
  if the retrieved chunks don't actually contain a fare-class/route
  breakdown, the LLM has nothing to enumerate.
