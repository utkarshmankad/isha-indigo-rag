"""Hindi/Hinglish evaluation set (Weeks 5-8 item 3b).

Mirrors a handful of eval/golden_qa.py's English queries in Devanagari
Hindi and in Hinglish (romanized Hindi), plus one out-of-scope query in
each, so scripts/evaluate_hindi.py can check:

- `script: "devanagari"` entries: the answer should also be in Devanagari
  (see src/evaluation/language_check.py) — a reliable, checkable signal.
- `script: "hinglish"` entries: run through the pipeline and checked only
  for "produced a non-empty answer, retrieval wasn't empty, refusal
  behavior is still correct where expected" — there's no reliable
  script-based way to verify the answer actually came back in Hinglish
  rather than English (see scripts/evaluate_hindi.py's docstring for why
  that isn't attempted here).

`expect_refusal=True` entries are out-of-scope queries that must trigger
refusal in this language too, not a hallucinated answer.
"""

HINDI_HINGLISH_QA = [
    {
        "query": "इंडिगो पर हैंड बैगेज का वज़न सीमा क्या है?",
        "airline": "indigo",
        "script": "devanagari",
        "doc_ids": ["BAG-001"],
    },
    {
        "query": "इंडिगो टिकट रद्द करने पर क्या शुल्क लगता है?",
        "airline": "indigo",
        "script": "devanagari",
        "doc_ids": ["CAN-001"],
    },
    {
        "query": "फ्रांस की राजधानी क्या है?",
        "airline": "all",
        "script": "devanagari",
        "doc_ids": [],
        "expect_refusal": True,
    },
    {
        "query": "IndiGo mein carry-on baggage ka weight limit kitna hai?",
        "airline": "indigo",
        "script": "hinglish",
        "doc_ids": ["BAG-001"],
    },
    {
        "query": "IndiGo ticket cancel karne par kitna charge lagta hai?",
        "airline": "indigo",
        "script": "hinglish",
        "doc_ids": ["CAN-001"],
    },
    {
        "query": "Is saal kaunsa stock accha rahega invest karne ke liye?",
        "airline": "all",
        "script": "hinglish",
        "doc_ids": [],
        "expect_refusal": True,
    },
]
