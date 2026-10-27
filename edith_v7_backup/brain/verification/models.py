from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ClaimStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class Source:
    url: str
    title: str
    text: str
    reliability: float
    level: int
    retrieved_at: str
    query: str = ""


@dataclass(frozen=True)
class Evidence:
    id: str
    claim: str
    source_url: str
    source_title: str
    excerpt: str
    reliability: float
    level: int
    entity: str = ""
    relationship: str = ""
    value: str = ""


@dataclass
class VerifiedClaim:
    id: str
    claim: str
    status: ClaimStatus
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)
    reason: str = ""

    @property
    def allowed_for_generation(self) -> bool:
        return self.status in (ClaimStatus.SUPPORTED, ClaimStatus.PARTIALLY_SUPPORTED) and bool(self.evidence)

    @property
    def must_be_qualified(self) -> bool:
        return self.status == ClaimStatus.PARTIALLY_SUPPORTED


@dataclass
class VerificationResult:
    query: str
    requires_verification: bool
    reason: str
    fresh_retrieval_required: bool = False
    search_queries: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    claims: list[VerifiedClaim] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    answer: str = ""
    valid: bool = False
    lookup: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for index, claim in enumerate(value["claims"]):
            original = self.claims[index]
            claim["status"] = original.status.value
            claim["allowed_for_generation"] = original.allowed_for_generation
            claim["must_be_qualified"] = original.must_be_qualified
            claim["evidence_ids"] = [item.id for item in original.evidence]
            claim["source_ids"] = [item.source_url for item in original.evidence]
        value["validator_result"] = self.valid
        return value
