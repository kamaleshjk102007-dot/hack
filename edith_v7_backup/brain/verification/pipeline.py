from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from threading import Lock

from utils.logger import get_logger

from .claims import ClaimExtractor, EvidenceExtractor, extract_report_subject, filter_sources_for_entity
from .models import ClaimStatus, VerificationResult
from .lookup import DirectLookup
from .query_analyzer import QueryAnalyzer
from .response import FinalValidator, ResponseGenerator, UNVERIFIED_MESSAGE, build_verified_context
from .retriever import Retriever
from .verifier import ClaimVerifier, ContradictionDetector

log = get_logger("verification")


class VerificationPipeline:
    def __init__(self, retriever=None, log_file="verification_audit.jsonl"):
        self.analyzer = QueryAnalyzer()
        self.retriever = retriever or Retriever()
        self.evidence_extractor = EvidenceExtractor()
        self.claim_extractor = ClaimExtractor()
        self.verifier = ClaimVerifier()
        self.contradiction_detector = ContradictionDetector()
        self.response_generator = ResponseGenerator()
        self.final_validator = FinalValidator()
        self.direct_lookup = DirectLookup()
        self.log_file = Path(log_file)
        self._log_lock = Lock()

    def run(self, query: str) -> VerificationResult:
        analysis = self.analyzer.analyze(query)
        result = VerificationResult(query, analysis.requires_verification, analysis.reason,
                                    analysis.fresh_retrieval_required)
        if not analysis.requires_verification:
            result.valid = True
            return result
        intent = self.direct_lookup.intent_extractor.extract(query)
        if intent:
            result.lookup = {"normalized_query": " ".join(query.lower().split()),
                             "intent": intent.intent, "entity": intent.entity,
                             "entity_type": intent.entity_type, "relationship": intent.relationship,
                             "attribute": intent.attribute, "expected_value": intent.expected_value}
            result.search_queries = self.direct_lookup.queries(intent)
            result.sources = self.retriever.retrieve(result.search_queries)
            relationship_evidence = self.direct_lookup.evidence_extractor.extract(intent, result.sources)
            # Resolve and confirm candidate values with a second targeted pass.
            candidate_values = list(dict.fromkeys(item.value for item in relationship_evidence))[:2]
            confirmation_queries = [f"{intent.entity} {value}" for value in candidate_values]
            if confirmation_queries:
                result.search_queries.extend(confirmation_queries)
                more_sources = self.retriever.retrieve(confirmation_queries)
                result.sources = list({source.url: source for source in result.sources + more_sources}.values())
                relationship_evidence = self.direct_lookup.evidence_extractor.extract(intent, result.sources)
            target = self.direct_lookup.verify(intent, relationship_evidence)
            result.claims = [target]
            if target.status == ClaimStatus.CONTRADICTED and relationship_evidence:
                actual = self.direct_lookup.verify(replace(intent, expected_value=""), relationship_evidence)
                if actual.allowed_for_generation:
                    result.claims.append(actual)
            verified_context = build_verified_context(result)
            result.answer = self.response_generator.generate(result, verified_context)
            result.valid = self.final_validator.validate(result, verified_context)
            if not result.valid:
                result.answer = UNVERIFIED_MESSAGE
            self._audit(result)
            return result
        report_topic, report_entity = extract_report_subject(query)
        search_input = report_topic or query
        result.search_queries = self.retriever.build_queries(search_input, analysis.fresh_retrieval_required)
        result.sources = self.retriever.retrieve(result.search_queries)
        if report_entity:
            before = len(result.sources)
            result.sources = filter_sources_for_entity(result.sources, report_entity)
            result.lookup = {"intent": "factual_report", "entity": report_entity,
                             "retrieved_sources": before, "relevant_sources": len(result.sources)}
        evidence = self.evidence_extractor.extract(result.sources)
        # User assertions are verified but never passed directly to generation.
        # Evidence-derived claims provide the only eligible factual content.
        user_claims = self.claim_extractor.from_user_statement(query)
        evidence_claims = self.claim_extractor.from_evidence(evidence)
        claims = list(dict.fromkeys(user_claims + evidence_claims))
        result.claims = self.verifier.verify(claims, evidence)
        result.contradictions = self.contradiction_detector.detect(result.claims)
        verified_context = build_verified_context(result)
        result.answer = self.response_generator.generate(result, verified_context)
        result.valid = self.final_validator.validate(result, verified_context)
        if not result.valid:
            result.answer = self.response_generator.generate(result, verified_context)
            result.valid = self.final_validator.validate(result, verified_context)
            if not result.valid:
                result.answer = UNVERIFIED_MESSAGE
        self._audit(result)
        return result

    def _audit(self, result: VerificationResult):
        try:
            entry = result.to_dict()
            # Audit evidence and decisions, never hidden model reasoning.
            with self._log_lock:
                with self.log_file.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            log.warning(f"Verification audit write failed: {exc}")


_pipeline = None


def get_pipeline() -> VerificationPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = VerificationPipeline()
    return _pipeline


def verify_factual_query(query: str) -> str | None:
    result = get_pipeline().run(query)
    return result.answer if result.requires_verification else None
