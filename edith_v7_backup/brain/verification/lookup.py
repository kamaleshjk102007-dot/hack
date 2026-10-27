from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .models import ClaimStatus, Evidence, Source, VerifiedClaim
from .claims import _sentences, entity_pattern


RELATION_ALIASES = {
    "lead_actor": ("hero", "lead actor", "main actor", "male lead", "protagonist actor", "star", "plays the lead"),
    "director": ("director", "directed"),
    "producer": ("producer", "produced"),
    "composer": ("music director", "composer", "music by"),
    "cinematographer": ("cinematographer", "cinematography", "dop"),
    "release_date": ("release date", "releasing", "released", "release"),
    "female_lead": ("heroine", "female lead"),
    "cast": ("cast",),
    "budget": ("budget",),
}


@dataclass(frozen=True)
class LookupIntent:
    entity: str
    entity_type: str
    intent: str
    relationship: str
    attribute: str
    expected_value: str = ""


class IntentExtractor:
    def extract(self, query: str) -> LookupIntent | None:
        text = re.sub(r"\s+", " ", query.strip()).strip(" .?!")
        lower = text.lower()
        if "factual report" in lower:
            return None
        # A user may repeat the same lookup in several phrasings. Resolve the
        # first complete question instead of sending the concatenated text to
        # broad retrieval as one impossible search query.
        first_question = re.split(r"(?<=\?)\s+", text, maxsplit=1)[0]
        if first_question != text:
            text, lower = first_question.strip(" .?!"), first_question.lower()
        relationship = next((key for key, aliases in RELATION_ALIASES.items()
                             if any(re.search(r"\b" + re.escape(alias) + r"\b", lower) for alias in aliases)), None)
        if not relationship:
            return None
        attribute = next(alias for alias in RELATION_ALIASES[relationship] if re.search(r"\b" + re.escape(alias) + r"\b", lower))
        entity = expected = ""
        patterns = [
            r"(?:hero|lead actor|main actor|male lead|female lead|heroine|director|producer|composer|cinematographer|dop|cast|budget)\s+of\s+(?:the\s+)?(?:movie|film)?\s*(.+)$",
            r"who\s+(?:is\s+)?(?:directed|directs|produced|produces)\s+(.+)$",
            r"when\s+(?:is|was|will)\s+(.+?)\s+(?:releasing|released|release)$",
            r"(?:who\s+is\s+the\s+)?(?:hero|lead actor|main actor|male lead|female lead|heroine|director|producer|composer|cinematographer|dop|cast|budget)\s+(?:of|for|in)\s+(?:the\s+)?(?:movie|film)?\s*(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                entity = match.group(1).strip(" .?!")
                break
        assertion_patterns = {
            "director": r"(?:is\s+)?(.+?)\s+directed by\s+(.+)$",
            "producer": r"(?:is\s+)?(.+?)\s+produced by\s+(.+)$",
            "lead_actor": r"is\s+(.+?)\s+(?:the\s+)?(?:hero|lead actor|main actor|male lead|star)\s+(?:of|in)\s+(.+)$",
        }
        if relationship in assertion_patterns and (not entity or lower.startswith("is ")):
            match = re.search(assertion_patterns[relationship], text, re.I)
            if match:
                if relationship == "lead_actor":
                    expected, entity = match.group(1), match.group(2)
                else:
                    entity, expected = match.group(1), match.group(2)
        entity = re.sub(r"^(?:movie|film)\s+", "", entity, flags=re.I).strip()
        if not entity or len(entity.split()) > 8:
            return None
        return LookupIntent(entity.title(), "movie", "lookup", relationship, attribute, expected.strip())


class RelationshipEvidenceExtractor:
    _patterns = {
        "lead_actor": [r"(?:stars?|starring|lead actor(?: is)?|lead role(?: is)?)[\s:,-]+([A-Z][A-Za-z.' -]{1,50})",
                       r"([A-Z][A-Za-z.' -]{1,50})\s+(?:plays|portrays|is|as)[^.;]{0,35}\b(?:lead|titular|hero)\b"],
        "director": [r"(?:director|directed by)[\s:,-]+([A-Z][A-Za-z.' -]{1,60})"],
        "producer": [r"(?:producer|produced by)[\s:,-]+([A-Z][A-Za-z.' -]{1,60})"],
        "composer": [r"(?:composer|music(?: director)?|music by)[\s:,-]+([A-Z][A-Za-z.' -]{1,60})"],
        "cinematographer": [r"(?:cinematographer|cinematography|DOP)[\s:,-]+([A-Z][A-Za-z.' -]{1,60})"],
        "release_date": [r"(?:release date|releasing on|released on|scheduled to release(?: in theatres)? on|set to release(?: in theatres)? on)[\s:,-]+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})"],
        "female_lead": [r"(?:female lead|heroine)[\s:,-]+([A-Z][A-Za-z.' -]{1,60})"],
    }

    def extract(self, intent: LookupIntent, sources: list[Source]) -> list[Evidence]:
        found = []
        subject_pattern = entity_pattern(intent.entity)
        if subject_pattern is None:
            return found
        for source in sources:
            if not subject_pattern.search(source.title + " " + source.text):
                continue
            title_match = subject_pattern.match(source.title)
            title_is_entity = bool(title_match and re.match(r"(?:\s*\(|\s*$)", source.title[title_match.end():]))
            if title_is_entity:
                passages = [source.text]
            else:
                passages = [part for part in _sentences(source.text)
                            if subject_pattern.search(part)]
            for passage in passages:
                for pattern in self._patterns.get(intent.relationship, []):
                    for match in re.finditer(pattern, passage, re.I):
                        # A non-entity page can support a relationship only
                        # when subject and predicate occur in the same passage.
                        if not title_is_entity and not subject_pattern.search(passage):
                            continue
                        # Periods may be part of a person's initials (G. V.
                        # Prakash Kumar); do not treat them as value terminators.
                        value = re.split(r"\s+(?:and|alongside|with|who|under|in|for|as)\s+|[;\n]", match.group(1))[0].strip(" ,.-:")
                        if not value:
                            continue
                        excerpt = match.group(0).strip()
                        evidence_id = "ev_" + hashlib.sha256((source.url + excerpt).encode()).hexdigest()[:12]
                        found.append(Evidence(evidence_id, f"{intent.entity}|{intent.relationship}|{value}",
                                              source.url, source.title, excerpt, source.reliability, source.level,
                                              intent.entity, intent.relationship, value))
        return found


class DirectLookup:
    def __init__(self):
        self.intent_extractor = IntentExtractor()
        self.evidence_extractor = RelationshipEvidenceExtractor()

    def queries(self, intent: LookupIntent) -> list[str]:
        relation_terms = {
            "lead_actor": ["lead actor", "starring", "cast", "main actor"],
            "director": ["director", "directed by"], "producer": ["producer", "produced by"],
            "release_date": ["release date", "releasing"], "composer": ["music composer"],
            "cinematographer": ["cinematographer"], "female_lead": ["female lead cast"],
            "cast": ["cast"], "budget": ["budget"],
        }.get(intent.relationship, [intent.relationship.replace("_", " ")])
        base = [intent.entity, f"{intent.entity} movie"] + [f"{intent.entity} {term}" for term in relation_terms]
        return list(dict.fromkeys(base))[:6]

    def verify(self, intent: LookupIntent, evidence: list[Evidence]) -> VerifiedClaim:
        claim_id = "cl_" + hashlib.sha256(f"{intent.entity}|{intent.relationship}|{intent.expected_value}".encode()).hexdigest()[:12]
        reliable = [item for item in evidence if item.reliability >= .75]
        if intent.expected_value:
            supporting = [item for item in reliable if item.value.lower() == intent.expected_value.lower()]
            if supporting:
                return VerifiedClaim(claim_id, self.claim_text(intent, intent.expected_value), ClaimStatus.SUPPORTED,
                                     max(item.reliability for item in supporting), supporting)
            if reliable:
                return VerifiedClaim(claim_id, self.claim_text(intent, intent.expected_value), ClaimStatus.CONTRADICTED,
                                     0.0, reliable, "Reliable evidence identifies a different value.")
            return VerifiedClaim(claim_id, self.claim_text(intent, intent.expected_value), ClaimStatus.UNVERIFIED, 0.0)
        if not reliable:
            return VerifiedClaim(claim_id, self.claim_text(intent, ""), ClaimStatus.UNVERIFIED, 0.0)
        values = {}
        for item in reliable:
            values.setdefault(item.value.lower(), []).append(item)
        best = max(values.values(), key=lambda items: max(item.reliability for item in items))
        value = best[0].value
        return VerifiedClaim(claim_id, self.claim_text(intent, value), ClaimStatus.SUPPORTED,
                             max(item.reliability for item in best), best)

    @staticmethod
    def claim_text(intent: LookupIntent, value: str) -> str:
        labels = {"lead_actor": "lead actor", "director": "director", "producer": "producer",
                  "composer": "composer", "cinematographer": "cinematographer",
                  "release_date": "release date", "female_lead": "female lead", "cast": "cast", "budget": "budget"}
        return f"The {labels[intent.relationship]} of {intent.entity} is {value}." if value else f"The {labels[intent.relationship]} of {intent.entity}."
