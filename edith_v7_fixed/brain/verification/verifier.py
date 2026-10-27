from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from urllib.parse import urlparse

from .models import ClaimStatus, Evidence, VerifiedClaim


def _tokens(text: str) -> set[str]:
    stop = {"the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on", "and", "or", "for", "who", "what"}
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2 and word not in stop}


def _relation(text: str):
    patterns = (
        ("director", r"^(.+?)\s+(?:is|was)?\s*directed by\s+(.+)$"),
        ("producer", r"^(.+?)\s+(?:is|was)?\s*produced by\s+(.+)$"),
        ("release", r"^(.+?)\s+(?:is|was)?\s*(?:released|releases?)\s+(?:on\s+)?(.+)$"),
        ("identity", r"^(.+?)\s+(?:is|was)\s+(.+)$"),
    )
    clean = text.strip().rstrip(".!?")
    for name, pattern in patterns:
        match = re.match(pattern, clean, re.I)
        if match:
            return name, _tokens(match.group(1)), _tokens(match.group(2))
    return None


class ClaimVerifier:
    def __init__(self, supported_threshold=0.75, weak_threshold=0.50):
        self.supported_threshold = supported_threshold
        self.weak_threshold = weak_threshold

    def verify(self, claims: list[str], evidence: list[Evidence]) -> list[VerifiedClaim]:
        results = []
        for claim in claims:
            wanted = _tokens(claim)
            relation = _relation(claim)
            contradiction = None
            if relation:
                relation_name, subject, value = relation
                for item in evidence:
                    other = _relation(item.excerpt)
                    if not other or other[0] != relation_name or item.reliability < self.supported_threshold:
                        continue
                    same_subject = len(subject & other[1]) / max(1, len(subject)) >= .6
                    if same_subject and value and other[2] and not (value & other[2]):
                        contradiction = item
                        break
            if contradiction:
                claim_id = "cl_" + hashlib.sha256(claim.encode()).hexdigest()[:12]
                results.append(VerifiedClaim(claim_id, claim, ClaimStatus.CONTRADICTED, 0.0,
                                             [contradiction], "A reliable source gives a conflicting value."))
                continue
            matches = []
            for item in evidence:
                overlap = len(wanted & _tokens(item.excerpt)) / max(1, len(wanted))
                if overlap >= 0.45:
                    matches.append((overlap, item))
            if not matches:
                claim_id = "cl_" + hashlib.sha256(claim.encode()).hexdigest()[:12]
                results.append(VerifiedClaim(claim_id, claim, ClaimStatus.UNVERIFIED, 0.0,
                                             reason="No supporting evidence found."))
                continue
            matches.sort(key=lambda pair: pair[0] * pair[1].reliability, reverse=True)
            selected = [pair[1] for pair in matches[:4]]
            independent = len({urlparse(item.source_url).netloc for item in selected})
            best_overlap = matches[0][0]
            best_reliability = matches[0][1].reliability
            confidence = min(1.0, best_reliability * best_overlap + min(0.14, max(0, independent - 1) * 0.07))
            status = ClaimStatus.SUPPORTED if confidence >= self.supported_threshold else (
                ClaimStatus.PARTIALLY_SUPPORTED if confidence >= self.weak_threshold else ClaimStatus.UNVERIFIED)
            claim_id = "cl_" + hashlib.sha256(claim.encode()).hexdigest()[:12]
            results.append(VerifiedClaim(claim_id, claim, status, round(confidence, 3), selected,
                                         f"Matched {independent} independent source domain(s)."))
        return results


class ContradictionDetector:
    _structured = (
        ("director", re.compile(r"^(.+?)\s+(?:is|was)?\s*directed by\s+(.+)$", re.I)),
        ("producer", re.compile(r"^(.+?)\s+(?:is|was)?\s*produced by\s+(.+)$", re.I)),
        ("release", re.compile(r"^(.+?)\s+(?:is|was)?\s*(?:released|releases?)\s+(?:on\s+)?(.+)$", re.I)),
    )

    def detect(self, claims: list[VerifiedClaim]) -> list[str]:
        groups = defaultdict(set)
        seen_evidence = set()
        for verified in claims:
            for item in verified.evidence:
                if item.reliability < .75 or item.id in seen_evidence:
                    continue
                seen_evidence.add(item.id)
                clean = item.excerpt.strip().rstrip(".!?")
                for name, pattern in self._structured:
                    match = pattern.match(clean)
                    if not match:
                        continue
                    subject = frozenset(_tokens(match.group(1)))
                    # Keep one-character differentiators in names/test data;
                    # the general claim matcher intentionally drops them.
                    value = " ".join(re.findall(r"[a-z0-9]+", match.group(2).lower()))
                    if subject and value:
                        groups[(name, subject)].add(value)
                    break
        conflicts = []
        for (name, subject), values in groups.items():
            if len(values) > 1:
                conflicts.append(
                    f"Reliable evidence disagrees about the {name} of {' '.join(sorted(subject))}."
                )
        return conflicts
