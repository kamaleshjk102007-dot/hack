from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryAnalysis:
    requires_verification: bool
    reason: str
    fresh_retrieval_required: bool = False


class QueryAnalyzer:
    _creative = re.compile(
        r"\b(write|compose|invent|brainstorm|create)\b.*\b(poem|story|fiction|idea|lyrics)\b", re.I)

    # Operational action commands at the START of a command — these are directives,
    # not factual lookup requests. Deliberately excludes "tell" (handled separately
    # via _tell_factual) and "explain" (context-dependent; handled by _coding_technical
    # or falls through to factual detection).
    _action = re.compile(
        r"^(open|launch|start|close|type|click|create|make|build|generate|download|send|"
        r"show|display|list|run|execute|enable|disable|toggle|set|reset|check)\b", re.I)

    # "Tell me about X" is factual when X is a world topic, but NOT factual when X is
    # EDITH/assistant-related.  This is checked inside _system_or_self below.
    # Standalone "tell" at line-start is too broad as an action verb bypass.

    # Queries about EDITH itself, its identity, config, capabilities, or settings.
    # ABSOLUTE bypass — the verification pipeline must never handle these.
    # Fixes applied:
    #   - capabilit(?:y|ies): matches both singular and plural
    #   - E.D.I.T.H. dotted form: matched via lookahead instead of \b (dots break word boundaries)
    #   - Removed over-broad terms ("status", "feature", "you", "config") that
    #     previously matched unrelated queries like "HTTP status code" or "feature film".
    #     Kept them only in more specific phrases.
    _system_or_self = re.compile(
        r"(?:"
        # Dotted form — word boundary does not work around dots, use lookahead/lookbehind
        r"(?<![A-Za-z0-9])e\.d\.i\.t\.h\.(?![A-Za-z0-9])"
        # Plain EDITH (word-bounded)
        r"|\bedith(?:'s)?\b"
        # Personal pronouns directed at the assistant
        r"|\byour(?:self|s)?\b"
        # Assistant identity
        r"|\bassistant\b"
        # System-level phrases (specific, not bare "config" or "status")
        r"|\bmy\s+(?:configuration|config|settings?)\b"
        r"|\bsystem\s+settings?\b"
        r"|\bsecurity\s+clearance\b"
        r"|\bclearance\s+level\b"
        r"|\byour\s+(?:configuration|config|settings?|status|features?|tools?|architecture|capabilities?|capability|setup|mode)\b"
        # Capability — both forms, bounded to EDITH context via "of EDITH" or "your"
        r"|\bcapabilit(?:y|ies)\s+of\s+(?:edith|you|the\s+assistant)\b"
        r"|\byour\s+capabilit(?:y|ies)\b"
        r"|\bwhat\s+(?:can|does|is|are)\s+(?:edith|you)\b"
        r"|\bwhat\s+(?:is|are)\s+(?:the\s+)?capabilit(?:y|ies)\s+of\s+(?:edith|you)\b"
        r"|\bhow\s+(?:do\s+you|does\s+edith)\b"
        r"|\bwho\s+are\s+you\b"
        r"|\bwhat\s+can\s+you\s+do\b"
        r"|\bwhat\s+is\s+your\b"
        r"|\bwhat\s+are\s+your\b"
        r"|\btell\s+me\s+about\s+(?:your|edith)\b"
        r"|\bdescribe\s+your\b"
        r"|\bexplain\s+your\b"
        r"|\bdo\s+you\s+have\b"       # "what features do you have?"
        r"|\byou\s+have\b"              # "what tools do you have"
        r"|\bwhat\s+(?:tools|features|functions)\s+do\s+you\b"
        r")", re.I)

    # Technical/coding queries — go to the code agent, not web evidence.
    # Note: "python" alone would mis-classify "What is the latest version of Python?"
    # which IS a factual web query.  We require at least one code-specific structural
    # indicator beyond the mere mention of a language name.
    _coding_technical = re.compile(
        r"\b(code|coding|debug(?:ging)?|error|exception|traceback|syntax\s+error|"
        r"fix\s+(?:my|this|the)\s+(?:code|bug|error|script)|"
        r"write\s+(?:a\s+)?(?:function|class|script|module)|"
        r"why\s+(?:is|does|did)\s+(?:my|this|the)\s+(?:code|script|function|loop|error|exception|bug)|"
        r"explain\s+(?:this|my|the)\s+(?:error|exception|traceback|code|bug|warning)|"
        r"provider\s+fallback|fallback\s+(?:chain|failed|error)|"
        r"javascript|typescript|c\+\+|rust|html|css|sql|"
        r"algorithm|regex|def\s|class\s|import\s|package\b|module\b|compile|compiler)\b", re.I)

    _conversational = re.compile(
        r"^(hi|hello|hey|yo|greetings|how\s+are\s+you|what'?s\s+up|thank\s+you|thanks|"
        r"good\s+(morning|evening|afternoon))[\s!?.]*$", re.I)

    _factual = re.compile(
        r"\b(who|what|when|where|why|how|tell\s+me\s+about|information\s+about|biography|"
        r"is\s+this\s+true|fact|director|cast|release|"
        r"price|cost|statistics?|population|company|scientific|medical|legal|history|"
        r"movie|film|person|people|location|date|budget|sports?|news|current|latest|today)\b", re.I)

    _fresh = re.compile(
        r"\b(current|currently|latest|today|now|recent|news|price|weather|score|ceo|president)\b", re.I)

    def analyze(self, query: str) -> QueryAnalysis:
        text = (query or "").strip()
        if not text:
            return QueryAnalysis(False, "Empty query.")

        # 1. Creative requests — no factual verification needed
        if self._creative.search(text):
            return QueryAnalysis(False, "The request is creative and does not require factual verification.")

        # 2. Greetings / pure conversational pleasantries
        if self._conversational.search(text):
            return QueryAnalysis(False, "The request is conversational and does not require factual verification.")

        # 3. Narrow explicit fact-check trigger (e.g. "fact-check …", "biography of …",
        #    "who directed …", "release date of …").  These can pull certain queries
        #    BACK into verification even if they would otherwise be bypassed.
        explicit_fact = bool(re.search(
            r"\b(factual|fact[- ]?check|verify|report\s+about|biography|"
            r"is\s+this\s+true|is\s+it\s+true\s+that|"
            r"director|producer|stars?\s+of|release\s+date|statistics?|price)\b", text, re.I))

        # 4. ABSOLUTE BYPASS: queries about EDITH / the assistant / its own capabilities,
        #    config, or settings must NEVER go through the web-evidence verification path.
        #    The agent handles these from its system prompt and real-time tool results.
        #    explicit_fact is NOT checked here — even "fact-check EDITH's capabilities"
        #    is still about the assistant, not a verifiable world fact.
        if self._system_or_self.search(text):
            return QueryAnalysis(False, "The query asks about assistant identity, capabilities, or configuration.")

        # 5. Coding / debugging requests go to the dev agent, not web evidence
        if not explicit_fact and self._coding_technical.search(text):
            return QueryAnalysis(False, "The query is a technical or coding question, handled by the development agent.")

        # 6. Operational action commands are verified by tool execution, not web evidence.
        #    Guard: do not absorb factual questions that start with "Who" / "When" / "Where".
        if (self._action.search(text)
                and not explicit_fact
                and not re.search(r"^\s*(who|when|where)\b", text, re.I)):
            return QueryAnalysis(False, "The request is an action rather than a factual question.")

        factual = bool(explicit_fact or self._factual.search(text) or re.search(r"\b\d{4}\b|\?$", text))
        return QueryAnalysis(
            factual,
            "The query contains factual claims that should be verified." if factual
            else "No factual verification trigger was detected.",
            bool(self._fresh.search(text)),
        )
