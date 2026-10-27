from __future__ import annotations

import re

from .models import ClaimStatus, VerificationResult


UNVERIFIED_MESSAGE = "I could not verify this information from reliable sources."


def build_verified_context(result: VerificationResult) -> dict:
    """Construct the sole context permitted to reach factual generation."""
    supported, qualified, sources = [], [], {}
    for claim in result.claims:
        if not claim.allowed_for_generation:
            continue
        payload = {"id": claim.id, "text": claim.claim, "confidence": claim.confidence,
                   "evidence_ids": [item.id for item in claim.evidence],
                   "source_urls": [item.source_url for item in claim.evidence]}
        (qualified if claim.must_be_qualified else supported).append(payload)
        for item in claim.evidence:
            sources[item.source_url] = item.source_title
    return {"verified_claims": supported, "qualified_claims": qualified, "sources": sources}


class ResponseGenerator:
    """Deterministic generator: it cannot introduce claims outside the gate."""

    def generate(self, result: VerificationResult, context: dict | None = None) -> str:
        if result.contradictions:
            details = " ".join(result.contradictions)
            return f"CONFLICT DETECTED\n\n{details} The information cannot currently be confirmed with sufficient confidence."
        context = context or build_verified_context(result)
        allowed = context["verified_claims"] + context["qualified_claims"]
        if not allowed:
            return UNVERIFIED_MESSAGE
        citation_numbers, citation_rows, lines = {}, [], []
        qualified_ids = {item["id"] for item in context["qualified_claims"]}
        for claim in allowed[:8]:
            url = claim["source_urls"][0]
            if url not in citation_numbers:
                citation_numbers[url] = len(citation_numbers) + 1
                citation_rows.append((citation_numbers[url], context["sources"][url], url))
            prefix = "Partially supported: " if claim["id"] in qualified_ids else ""
            lines.append(f"- {prefix}{claim['text']} [{citation_numbers[url]}]")
        correction = "No.\n\n" if any(claim.status == ClaimStatus.CONTRADICTED for claim in result.claims) else ""
        return (correction + "Verified information:\n\n" + "\n".join(lines) + "\n\nSources:\n" +
                "\n".join(f"[{number}] {title}: {url}" for number, title, url in citation_rows))


class FinalValidator:
    """Actual release gate for factual responses."""

    def validate(self, result: VerificationResult, context: dict | None = None) -> bool:
        if not result.requires_verification:
            return True
        context = context or build_verified_context(result)
        if result.answer == UNVERIFIED_MESSAGE:
            return not (context["verified_claims"] or context["qualified_claims"])
        if result.answer.startswith("CONFLICT DETECTED"):
            return bool(result.contradictions)
        allowed = {item["text"] for item in context["verified_claims"] + context["qualified_claims"]}
        factual_lines = re.findall(r"^- (?:Partially supported: )?(.+?) \[\d+\]$", result.answer, re.M)
        if not factual_lines or any(line not in allowed for line in factual_lines):
            return False
        cited_urls = set(re.findall(r"https?://[^\s]+", result.answer))
        if not cited_urls or not cited_urls.issubset(set(context["sources"])):
            return False
        blocked = {claim.claim for claim in result.claims
                   if claim.status in (ClaimStatus.UNVERIFIED, ClaimStatus.CONTRADICTED)}
        return not any(line in blocked for line in factual_lines)
