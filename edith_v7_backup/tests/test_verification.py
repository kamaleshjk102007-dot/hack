import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from brain.verification.models import ClaimStatus, Source
from brain.verification.pipeline import VerificationPipeline
from brain.verification.query_analyzer import QueryAnalyzer
from brain.verification.verifier import ClaimVerifier, ContradictionDetector
from brain.verification.claims import EvidenceExtractor
from brain.verification.response import build_verified_context
from utils.memory import Memory


NOW = datetime.now(timezone.utc).isoformat()


class FakeRetriever:
    def __init__(self, sources):
        self.sources = sources

    def build_queries(self, query, fresh=False):
        return [query, query + " official"] if fresh else [query]

    def retrieve(self, queries):
        return self.sources


def source(url, text, reliability=.95, level=1):
    return Source(url, "Retrieved source", text, reliability, level, NOW, "test")


class VerificationPipelineTests(unittest.TestCase):
    def pipeline(self, sources):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return VerificationPipeline(FakeRetriever(sources), Path(temp.name) / "audit.jsonl")

    def test_a_correct_information_is_supported(self):
        result = self.pipeline([source("https://example.gov/item", "Project Atlas was launched in 2024.")]).run(
            "When was Project Atlas launched?"
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.claims[0].status, ClaimStatus.SUPPORTED)
        self.assertIn("https://example.gov/item", result.answer)

    def test_b_fabricated_information_is_unverified(self):
        result = self.pipeline([]).run("Who invented the fictional Zorbulator 9000?")
        self.assertEqual(result.answer, "I could not verify this information from reliable sources.")

    def test_c_partial_information_is_marked_partial(self):
        evidence = EvidenceExtractor().extract([source("https://reference.example/x", "Mandaadi is a Tamil film.", .58, 3)])
        claim = ClaimVerifier().verify(["Mandaadi is a Tamil film released in 2026."], evidence)[0]
        self.assertIn(claim.status, (ClaimStatus.PARTIALLY_SUPPORTED, ClaimStatus.UNVERIFIED))

    def test_d_conflicting_sources_are_exposed(self):
        evidence = EvidenceExtractor().extract([
            source("https://one.gov/movie", "Mandaadi is directed by Person A."),
            source("https://two.gov/movie", "Mandaadi is directed by Person B."),
        ])
        claims = ClaimVerifier().verify([item.claim for item in evidence], evidence)
        conflicts = ContradictionDetector().detect(claims)
        self.assertTrue(conflicts)

    def test_compatible_report_descriptions_are_not_false_conflicts(self):
        evidence = EvidenceExtractor().extract([source(
            "https://www.marvel.com/movies/avengers-doomsday",
            "Avengers: Doomsday is an upcoming superhero film. Produced by Marvel Studios and distributed by Disney, it is a sequel to Avengers: Endgame.",
        )])
        claims = ClaimVerifier().verify([item.claim for item in evidence], evidence)
        self.assertEqual(ContradictionDetector().detect(claims), [])

    def test_e_current_information_requires_fresh_retrieval(self):
        analysis = QueryAnalyzer().analyze("Who is the current CEO of Example Corp?")
        self.assertTrue(analysis.requires_verification)
        self.assertTrue(analysis.fresh_retrieval_required)

    def test_f_missing_information_uses_required_message(self):
        result = self.pipeline([]).run("What happened at the unknown event in 2025?")
        self.assertIn("could not verify", result.answer)

    def test_g_guess_request_does_not_guess(self):
        result = self.pipeline([]).run("Guess who directed the film Mandaadi?")
        self.assertEqual(result.answer, "I could not verify this information from reliable sources.")

    def test_supported_claim_is_allowed_for_generation(self):
        evidence = EvidenceExtractor().extract([source("https://film.gov/title", "Mandaadi is directed by Pugazhendhi Mathimaran.")])
        claim = ClaimVerifier().verify([evidence[0].claim], evidence)[0]
        self.assertEqual(claim.status, ClaimStatus.SUPPORTED)
        self.assertTrue(claim.allowed_for_generation)
        self.assertTrue(claim.evidence[0].id.startswith("ev_"))

    def test_unverified_and_contradicted_claims_are_blocked(self):
        evidence = EvidenceExtractor().extract([source("https://film.gov/title", "Mandaadi is directed by Pugazhendhi Mathimaran.")])
        claims = ClaimVerifier().verify([
            "Sunburst Studios produced Mandaadi.",
            "Mandaadi is directed by Arjun Kumar.",
        ], evidence)
        self.assertEqual(claims[0].status, ClaimStatus.UNVERIFIED)
        self.assertEqual(claims[1].status, ClaimStatus.CONTRADICTED)
        self.assertTrue(all(not claim.allowed_for_generation for claim in claims))

    def test_mandaadi_hallucinations_never_reach_final_answer(self):
        prompt = (
            "Write a factual report about Mandaadi.\n\n"
            "Mandaadi is directed by Arjun Kumar, produced by Sunburst Studios, "
            "and stars Vijay Sethupathi and Nithya Menen. It is about a software "
            "engineer named Ravi who returns to his village and fights illegal sand mining. "
            "The film releases on February 22, 2025."
        )
        pipeline = self.pipeline([source(
            "https://film.gov/mandaadi",
            "Mandaadi is directed by Pugazhendhi Mathimaran.",
        )])
        result = pipeline.run(prompt)
        blocked = ["Arjun Kumar", "Sunburst Studios", "Vijay Sethupathi", "Nithya Menen",
                   "software engineer", "illegal sand mining", "February 22, 2025"]
        self.assertTrue(result.requires_verification)
        self.assertTrue(all(value not in result.answer for value in blocked))
        self.assertIn("Pugazhendhi Mathimaran", result.answer)
        self.assertTrue(all(claim.status in (ClaimStatus.SUPPORTED, ClaimStatus.PARTIALLY_SUPPORTED)
                            for claim in result.claims if claim.claim in result.answer))

    def test_fake_citation_fails_the_release_gate(self):
        result = self.pipeline([source("https://film.gov/title", "Mandaadi is directed by Pugazhendhi Mathimaran.")]).run(
            "Who directed Mandaadi?"
        )
        result.answer = result.answer.replace("https://film.gov/title", "https://fabricated.invalid/source")
        context = build_verified_context(result)
        self.assertFalse(self.pipeline([]).final_validator.validate(result, context))

    def test_user_claim_is_not_promoted_in_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = Memory()
            memory._file = str(Path(directory) / "memory.json")
            memory._data = []
            memory.save("user", "Arjun Kumar directed Mandaadi.",
                        origin="USER_PROVIDED", verification_status="UNVERIFIED")
            saved = memory.get_history()[0]
            self.assertEqual(saved["origin"], "USER_PROVIDED")
            self.assertNotEqual(saved["verification_status"], "VERIFIED")

    def test_verified_memory_requires_source_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = Memory()
            memory._file = str(Path(directory) / "memory.json")
            memory._data = []
            memory.save("assistant", "Unsupported fact", verification_status="VERIFIED")
            self.assertEqual(memory.get_history()[0]["verification_status"], "UNVERIFIED")

    def mandaadi_sources(self):
        return [
            source("https://www.imdb.com/title/tt36596965/",
                   "Mandaadi is directed by Pugazhendhi Mathimaran. Mandaadi, starring Soori as the lead actor."),
            source("https://www.rottentomatoes.com/m/mandaadi",
                   "Mandaadi is produced by Elred Kumar. Mandaadi, starring Soori in the titular role.", .86, 2),
            source("https://in.bookmyshow.com/movies/mandaadi/ET00442702",
                   "Mandaadi releasing on 10 September 2026. Mandaadi starring Soori.", .86, 2),
        ]

    def test_lookup_hero_semantically_resolves_to_lead_actor(self):
        result = self.pipeline(self.mandaadi_sources()).run("hero of movie mandaadi")
        self.assertEqual(result.lookup["relationship"], "lead_actor")
        self.assertIn("Soori", result.answer)
        self.assertEqual(result.claims[0].status, ClaimStatus.SUPPORTED)

    def test_repeated_lookup_phrasings_resolve_as_one_entity_question(self):
        query = ("Who is the hero of Mandaadi? Who plays the lead in Mandaadi? "
                 "Who is the male lead in Mandaadi?")
        result = self.pipeline(self.mandaadi_sources()).run(query)
        self.assertEqual(result.lookup["entity"], "Mandaadi")
        self.assertIn("Soori", result.answer)

    def test_report_rejects_unrelated_retrieval_results(self):
        sources = [
            source("https://en.wikipedia.org/wiki/Shreya_Ghoshal",
                   "Shreya Ghoshal is an Indian singer. She began learning music at age four.", .76, 3),
            source("https://film.gov/immortal",
                   "Immortal is a Tamil fantasy thriller directed by Mariyappan Chinna."),
        ]
        result = self.pipeline(sources).run("Write a factual report about the new Tamil movie Immortal.")
        self.assertEqual(result.lookup["entity"], "Immortal")
        self.assertEqual(result.lookup["relevant_sources"], 1)
        self.assertIn("Immortal", result.answer)
        self.assertNotIn("Shreya Ghoshal", result.answer)

    def test_report_with_only_unrelated_sources_fails_closed(self):
        result = self.pipeline([source(
            "https://en.wikipedia.org/wiki/Shreya_Ghoshal",
            "Shreya Ghoshal is an Indian singer.", .76, 3,
        )]).run("Write a factual report about the new Tamil movie Immortal.")
        self.assertEqual(result.lookup["relevant_sources"], 0)
        self.assertEqual(result.answer, "I could not verify this information from reliable sources.")

    def test_summary_prefix_and_short_movie_initialism_are_resolved(self):
        sources = [
            source("https://reference.example/singer", "A singer has released several Tamil songs.", .86, 2),
            source("https://film.gov/lik",
                   "Love Insurance Kompany, also known by the initialism LIK, is a Tamil science fiction romantic comedy film directed by Vignesh Shivan."),
        ]
        result = self.pipeline(sources).run(
            "Write a factual report about the summary of the Tamil movie LIK."
        )
        self.assertEqual(result.lookup["entity"], "LIK")
        self.assertEqual(result.lookup["relevant_sources"], 1)
        self.assertIn("Love Insurance Kompany", result.answer)
        self.assertNotIn("singer", result.answer.lower())

    def test_report_title_matching_tolerates_official_punctuation(self):
        result = self.pipeline([source(
            "https://www.marvel.com/movies/avengers-doomsday",
            "Avengers: Doomsday is an upcoming Marvel Studios film.",
        )]).run("Write a factual report about the movie Avengers Doomsday.")
        self.assertEqual(result.lookup["entity"], "Avengers Doomsday")
        self.assertEqual(result.lookup["relevant_sources"], 1)
        self.assertIn("Avengers: Doomsday", result.answer)

    def test_factual_qualifier_is_not_treated_as_part_of_entity_name(self):
        result = self.pipeline([source(
            "https://www.marvel.com/movies/avengers-doomsday",
            "Avengers: Doomsday is an upcoming Marvel Studios film.",
        )]).run("Write a factual report about factual the movie Avengers Doomsday.")
        self.assertEqual(result.lookup["entity"], "Avengers Doomsday")
        self.assertEqual(result.lookup["relevant_sources"], 1)
        self.assertIn("Avengers: Doomsday", result.answer)

    def test_report_prefers_subject_titles_over_incidental_franchise_mentions(self):
        result = self.pipeline([
            Source("https://reference.example/doomsday", "Avengers: Doomsday",
                   "Avengers: Doomsday is an upcoming superhero film.", .95, 1, NOW, "test"),
            Source("https://reference.example/endgame", "Avengers: Endgame",
                   "A later film titled Avengers: Doomsday was announced.", .95, 1, NOW, "test"),
        ]).run("Write a factual report about the movie Avengers Doomsday.")
        self.assertEqual(result.lookup["relevant_sources"], 1)
        self.assertNotIn("Avengers: Endgame", result.answer)

    def test_direct_lookup_entity_matching_tolerates_title_punctuation(self):
        result = self.pipeline([source(
            "https://www.marvel.com/movies/avengers-doomsday",
            "Avengers: Doomsday is directed by Anthony Russo and Joe Russo.",
        )]).run("Who directed Avengers Doomsday?")
        self.assertEqual(result.claims[0].status, ClaimStatus.SUPPORTED)
        self.assertIn("Anthony Russo", result.answer)

    def test_person_initials_are_not_split_into_false_sentence_fragments(self):
        result = self.pipeline([source(
            "https://film.gov/immortal",
            "Immortal stars G. V. Prakash Kumar and Kayadu Lohar in the lead roles.",
        )]).run("Write a factual report about the Tamil movie Immortal.")
        self.assertIn("G. V. Prakash Kumar", result.answer)
        self.assertNotIn("\n- Prakash Kumar", result.answer)

    def test_lookup_preserves_initials_in_lead_actor_name(self):
        result = self.pipeline([source(
            "https://film.gov/immortal",
            "Immortal stars G. V. Prakash Kumar and Kayadu Lohar in the lead roles.",
        )]).run("Who is the hero of Immortal?")
        self.assertEqual(result.claims[0].status, ClaimStatus.SUPPORTED)
        self.assertIn("G. V. Prakash Kumar", result.answer)

    def test_lookup_does_not_join_entity_and_relationship_across_sentences(self):
        sources = [
            source("https://reference.example/person",
                   "The actor appeared in a documentary titled Immortal. He stars in a limited series portraying Johnnie.", .86, 2),
            source("https://film.gov/immortal",
                   "Immortal stars G. V. Prakash Kumar and Kayadu Lohar in the lead roles."),
        ]
        result = self.pipeline(sources).run("Who is the hero of Immortal?")
        self.assertIn("G. V. Prakash Kumar", result.answer)
        self.assertNotIn("Johnnie", result.answer)

    def test_lookup_director_producer_and_release_date(self):
        cases = [
            ("who directed Mandaadi?", "Pugazhendhi Mathimaran", "director"),
            ("who produced Mandaadi?", "Elred Kumar", "producer"),
            ("when is Mandaadi releasing?", "10 September 2026", "release_date"),
        ]
        for query, expected, relation in cases:
            with self.subTest(query=query):
                result = self.pipeline(self.mandaadi_sources()).run(query)
                self.assertEqual(result.lookup["relationship"], relation)
                self.assertEqual(result.claims[0].status, ClaimStatus.SUPPORTED)
                self.assertIn(expected, result.answer)

    def test_lookup_rejects_false_director_and_hero(self):
        for query, blocked, actual in [
            ("Is Mandaadi directed by Arjun Kumar?", "Arjun Kumar", "Pugazhendhi Mathimaran"),
            ("Is Vijay Sethupathi the hero of Mandaadi?", "Vijay Sethupathi", "Soori"),
        ]:
            with self.subTest(query=query):
                result = self.pipeline(self.mandaadi_sources()).run(query)
                self.assertEqual(result.claims[0].status, ClaimStatus.CONTRADICTED)
                self.assertFalse(result.claims[0].allowed_for_generation)
                self.assertTrue(result.answer.startswith("No."))
                self.assertNotIn(blocked, result.answer)
                self.assertIn(actual, result.answer)

    def test_lookup_unknown_budget_stays_unverified(self):
        result = self.pipeline(self.mandaadi_sources()).run("Tell me the budget of Mandaadi")
        self.assertEqual(result.claims[0].status, ClaimStatus.UNVERIFIED)
        self.assertEqual(result.answer, "I could not verify this information from reliable sources.")


if __name__ == "__main__":
    unittest.main()
