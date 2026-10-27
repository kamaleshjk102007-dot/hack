from __future__ import annotations

import hashlib
import re

from .models import Evidence, Source


def _sentences(text: str) -> list[str]:
    # Do not split personal-name initials such as "G. V. Prakash Kumar".
    protected = re.sub(r"\b([A-Z])\.(?=\s*[A-Z])", lambda match: match.group(1) + "<DOT>", text)
    parts = re.split(r"(?<=[.!?])\s+|\n+", protected)
    return [part.replace("<DOT>", ".").strip(" \t\r\n•-")
            for part in parts if len(part.strip()) >= 20]


def extract_report_subject(query: str) -> tuple[str, str]:
    """Return (search topic, core entity) for broad factual reports."""
    match = re.search(r"(?:factual\s+)?(?:report|information|details?)\s+(?:about|on)\s+(.+?)[.?!]?$", query.strip(), re.I)
    if not match:
        return "", ""
    topic = match.group(1).strip(" .?!")
    topic = re.sub(r"^(?:the\s+)?(?:summary|overview|profile|details?|information)\s+of\s+", "", topic, flags=re.I).strip()
    entity = re.sub(
        r"^(?:(?:factual|the|a|an|new|upcoming|latest|tamil|movie|film)\s+)+",
        "", topic, flags=re.I,
    ).strip()
    return topic, entity or topic


def entity_pattern(entity: str) -> re.Pattern[str] | None:
    """Match an entity while tolerating punctuation used in official titles.

    For example, ``Avengers Doomsday`` must match ``Avengers: Doomsday``.
    Word boundaries still prevent short names such as ``LIK`` from matching
    inside unrelated longer words.
    """
    tokens = re.findall(r"[A-Za-z0-9]+", entity)
    if not tokens:
        return None
    expression = r"(?<!\w)" + r"[\W_]+".join(re.escape(token) for token in tokens) + r"(?!\w)"
    return re.compile(expression, re.I)


def filter_sources_for_entity(sources: list[Source], entity: str) -> list[Source]:
    if not entity:
        return sources
    pattern = entity_pattern(entity)
    if pattern is None:
        return []
    # Search engines commonly return adjacent franchise/person pages whose body
    # merely mentions the subject.  When subject-titled pages exist, keep those
    # authoritative candidates and discard incidental mentions.
    title_matches = [source for source in sources if pattern.search(source.title)]
    if title_matches:
        return title_matches
    return [source for source in sources if pattern.search(source.text)]


class EvidenceExtractor:
    def extract(self, sources: list[Source]) -> list[Evidence]:
        evidence = []
        for source in sources:
            for sentence in _sentences(source.text)[:5]:
                evidence_id = "ev_" + hashlib.sha256((source.url + sentence).encode()).hexdigest()[:12]
                evidence.append(Evidence(evidence_id, sentence, source.url, source.title, sentence,
                                         source.reliability, source.level))
        return evidence


class ClaimExtractor:
    def from_evidence(self, evidence: list[Evidence]) -> list[str]:
        return list(dict.fromkeys(item.claim for item in evidence))

    def from_user_statement(self, query: str) -> list[str]:
        text = re.sub(
            r"^(?:is it true that|verify(?: whether| that)?|fact[- ]?check|write\s+(?:a\s+)?factual\s+report\s+about\s+[^.?!]+[.?!]?)\s*",
            "", query.strip(), flags=re.I)
        if not text or text.endswith("?"):
            return []
        atomic = []
        for sentence in _sentences(text):
            parts = re.split(
                r",\s*(?=[a-zA-Z])|\s+and\s+(?=(?:is|was|stars?|features?|produced|directed|released|it\b|the\b))",
                sentence)
            atomic.extend(part.strip() for part in parts if len(part.strip()) >= 8)
        return list(dict.fromkeys(atomic))
