"""Language-match checks for Hindi/Hinglish evaluation (Weeks 5-8 item 3b).

The system prompt (src/retrieval/retriever.py) instructs the LLM: answer in
Hindi (Devanagari script) if the question was asked in Hindi or Hinglish,
otherwise in English. Nothing had ever verified that instruction actually
holds. This module provides the one check that's reliably script-based —
Devanagari in, Devanagari out — without another LLM call.

Hinglish (romanized Hindi, e.g. "baggage ka weight limit kya hai") has no
equivalent reliable signal: Latin script alone doesn't distinguish English
from Hinglish, and a real check would require language-identification
model or another LLM judge call, which scripts/evaluate_hindi.py
deliberately doesn't add — see its module docstring.
"""
import re

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def contains_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text))


def answer_matches_devanagari_query(query: str, answer: str) -> bool:
    """True if the query wasn't in Devanagari script (check not
    applicable), or if it was and the answer is too."""
    if not contains_devanagari(query):
        return True
    return contains_devanagari(answer)
