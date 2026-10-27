import unittest
from types import SimpleNamespace
from unittest.mock import patch

from plugins.all_phases import _pdf_topic, _safe_document_content


class ArtifactGroundingTests(unittest.TestCase):
    def test_pdf_topic_removes_factual_movie_request_qualifiers(self):
        self.assertEqual(
            _pdf_topic("create a pdf about factual the movie Avengers Doomsday"),
            "Avengers Doomsday",
        )

    def test_factual_pdf_content_uses_verified_pipeline_not_raw_llm(self):
        verified = SimpleNamespace(answer="Verified fact [1]\nSource: https://example.gov/fact",
                                   valid=True, claims=[1], sources=[1])
        pipeline = SimpleNamespace(run=lambda query: verified)
        with patch("brain.verification.get_pipeline", return_value=pipeline), \
             patch("brain.ai_engine.query") as raw_llm:
            content = _safe_document_content(
                "create a pdf about a real movie", "a real movie", "creative prompt")
        self.assertEqual(content, verified.answer)
        raw_llm.assert_not_called()

    def test_explicit_fiction_can_still_use_creative_generation(self):
        with patch("brain.ai_engine.query", return_value="Imaginary story") as raw_llm:
            content = _safe_document_content(
                "create a fictional story pdf", "fictional story", "creative prompt")
        self.assertEqual(content, "Imaginary story")
        raw_llm.assert_called_once()
