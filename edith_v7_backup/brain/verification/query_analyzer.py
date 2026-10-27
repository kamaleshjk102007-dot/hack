from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryAnalysis:
    requires_verification: bool
    reason: str
    fresh_retrieval_required: bool = False


class QueryAnalyzer:
    _creative = re.compile(r"\b(write|compose|invent|brainstorm|create)\b.*\b(poem|story|fiction|idea|lyrics)\b", re.I)
    _action = re.compile(r"^(open|launch|start|close|type|click|create|make|build|generate|download|send)\b", re.I)
    _factual = re.compile(
        r"\b(who|what|when|where|why|how|tell me about|information about|biography|is this true|fact|director|cast|release|"
        r"price|cost|statistics?|population|company|scientific|medical|legal|history|"
        r"movie|film|person|people|location|date|budget|sports?|news|current|latest|today)\b", re.I)
    _fresh = re.compile(r"\b(current|currently|latest|today|now|recent|news|price|weather|score|ceo|president)\b", re.I)

    def analyze(self, query: str) -> QueryAnalysis:
        text = (query or "").strip()
        if not text or self._creative.search(text):
            return QueryAnalysis(False, "The request is creative and does not require factual verification.")
        explicit_fact = bool(re.search(
            r"\b(factual|fact[- ]?check|verify|report about|biography|current|latest|news|"
            r"director|producer|stars?|released?|release date|statistics?|price)\b", text, re.I))
        # Operational commands are verified by their tool result, not web evidence.
        if self._action.search(text) and not explicit_fact and not re.search(r"\b(is this true|who|when)\b", text, re.I):
            return QueryAnalysis(False, "The request is an action rather than a factual question.")
        factual = bool(explicit_fact or self._factual.search(text) or re.search(r"\b\d{4}\b|\?$", text))
        return QueryAnalysis(
            factual,
            "The query contains factual claims that should be verified." if factual else "No factual verification trigger was detected.",
            bool(self._fresh.search(text)),
        )
