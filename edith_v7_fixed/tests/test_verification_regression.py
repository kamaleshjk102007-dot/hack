"""
tests/test_verification_regression.py
=====================================
Regression suite for the self-query verification-bypass fix.
Tests four layers:
  1. QueryAnalyzer.analyze() — unit-level classification
  2. VerificationPipeline.run() — pipeline layer (no network)
  3. Router integration — that router.route() reaches the right destination
  4. Secret / credential protection — config queries must not expose secrets

Run from project root:
    python -m pytest tests/test_verification_regression.py -v
  or without pytest:
    python tests/test_verification_regression.py
"""
from __future__ import annotations

import sys
import os
import re
import types
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# 1. QueryAnalyzer unit tests
# ---------------------------------------------------------------------------

class TestQueryAnalyzerSelfBypass(unittest.TestCase):
    """Self / identity / capability queries must NEVER reach web verification."""

    def setUp(self):
        from brain.verification.query_analyzer import QueryAnalyzer
        self.qa = QueryAnalyzer()

    def _expect_no_verify(self, query: str):
        r = self.qa.analyze(query)
        self.assertFalse(
            r.requires_verification,
            f"Expected bypass but got VERIFY for: {query!r}\n  reason: {r.reason}",
        )

    # --- Primary task queries (from spec) ---
    def test_capability_singular(self):
        self._expect_no_verify("What is your capability?")

    def test_capabilities_plural(self):
        self._expect_no_verify("What are your capabilities?")

    def test_what_can_edith_do(self):
        self._expect_no_verify("What can EDITH do?")

    def test_capability_of_edith(self):
        self._expect_no_verify("What is the capability of EDITH?")

    def test_display_edith_dotted_config(self):
        self._expect_no_verify("Display current E.D.I.T.H. configuration.")

    def test_show_system_settings(self):
        self._expect_no_verify("Show system settings.")

    def test_list_security_clearance(self):
        self._expect_no_verify("List security clearance levels.")

    def test_tell_me_about_your_architecture(self):
        self._expect_no_verify("Tell me about your architecture.")

    def test_how_does_edith_work(self):
        self._expect_no_verify("How does EDITH work?")

    def test_check_edith_status(self):
        self._expect_no_verify("Check EDITH status.")

    def test_show_available_tools(self):
        self._expect_no_verify("Show me your available tools.")

    def test_explain_current_configuration(self):
        self._expect_no_verify("Explain your current configuration.")

    # --- Extra coverage ---
    def test_what_is_your_current_configuration(self):
        self._expect_no_verify("What is your current configuration?")

    def test_tell_me_about_edith_features(self):
        self._expect_no_verify("Tell me about EDITH features.")

    def test_what_features_do_you_have(self):
        self._expect_no_verify("What features do you have?")

    def test_describe_your_capabilities(self):
        self._expect_no_verify("Describe your capabilities.")

    def test_what_can_you_do(self):
        self._expect_no_verify("What can you do?")

    def test_who_are_you(self):
        self._expect_no_verify("Who are you?")

    def test_your_tools(self):
        self._expect_no_verify("Show me your tools.")

    def test_dotted_edith_standalone(self):
        # Sentence containing E.D.I.T.H. dotted form
        self._expect_no_verify("What does E.D.I.T.H. support?")

    def test_edith_possessive(self):
        self._expect_no_verify("What are EDITH's features?")


class TestQueryAnalyzerFactualVerification(unittest.TestCase):
    """External factual queries MUST be sent through verification."""

    def setUp(self):
        from brain.verification.query_analyzer import QueryAnalyzer
        self.qa = QueryAnalyzer()

    def _expect_verify(self, query: str):
        r = self.qa.analyze(query)
        self.assertTrue(
            r.requires_verification,
            f"Expected VERIFY but got bypass for: {query!r}\n  reason: {r.reason}",
        )

    def test_python_version(self):
        self._expect_verify("What is the latest version of Python?")

    def test_latest_ai_research(self):
        self._expect_verify("What happened in the latest AI research?")

    def test_tournament_winner(self):
        self._expect_verify("Who won the most recent major international tournament?")

    def test_weather_chennai(self):
        self._expect_verify("Explain the current weather in Chennai.")

    def test_recent_ai_news(self):
        self._expect_verify("Find recent news about artificial intelligence.")

    def test_movie_director(self):
        self._expect_verify("Who directed Inception?")

    def test_movie_release_date(self):
        self._expect_verify("What is the release date of Avengers Doomsday?")

    def test_war_factual(self):
        self._expect_verify("Tell me about the Russo-Ukrainian war.")


class TestQueryAnalyzerCodingOperational(unittest.TestCase):
    """Coding and operational queries must bypass factual verification."""

    def setUp(self):
        from brain.verification.query_analyzer import QueryAnalyzer
        self.qa = QueryAnalyzer()

    def _expect_no_verify(self, query: str):
        r = self.qa.analyze(query)
        self.assertFalse(
            r.requires_verification,
            f"Expected bypass but got VERIFY for: {query!r}\n  reason: {r.reason}",
        )

    def test_python_error_explain(self):
        self._expect_no_verify("Explain this Python error.")

    def test_fix_my_code(self):
        self._expect_no_verify("Fix my code.")

    def test_hud_server_check(self):
        self._expect_no_verify("Check whether the HUD server is running.")

    def test_show_directory(self):
        self._expect_no_verify("Show the contents of a permitted project directory.")

    def test_provider_fallback(self):
        self._expect_no_verify("Explain why my provider fallback failed.")

    def test_debug_traceback(self):
        self._expect_no_verify("Debug this traceback.")

    def test_write_function(self):
        self._expect_no_verify("Write a function to sort a list.")

    def test_create_project(self):
        self._expect_no_verify("Create a new Python project.")

    def test_open_browser(self):
        self._expect_no_verify("Open the browser.")

    def test_send_email(self):
        self._expect_no_verify("Send an email to mom.")


# ---------------------------------------------------------------------------
# 2. Regex-level tests — punctuation, capitalisation, word boundaries
# ---------------------------------------------------------------------------

class TestSystemOrSelfRegex(unittest.TestCase):
    """Direct regex tests: boundary conditions, casing, dotted form."""

    def setUp(self):
        from brain.verification.query_analyzer import QueryAnalyzer
        self._rx = QueryAnalyzer._system_or_self

    def _matches(self, text: str) -> bool:
        return bool(self._rx.search(text))

    # Capability — scoped phrases must match
    def test_your_capability(self):
        self.assertTrue(self._matches("your capability"))

    def test_your_capabilities(self):
        self.assertTrue(self._matches("your capabilities"))

    def test_capability_of_edith(self):
        self.assertTrue(self._matches("capability of EDITH"))

    def test_capabilities_of_edith(self):
        self.assertTrue(self._matches("capabilities of EDITH"))

    def test_what_can_edith_do(self):
        self.assertTrue(self._matches("What can EDITH do"))

    def test_what_can_you_do(self):
        self.assertTrue(self._matches("what can you do"))

    # Bare standalone 'capability' must NOT match (false-positive guard)
    def test_bare_capability_no_match(self):
        self.assertFalse(self._matches("capability"))

    def test_bare_capabilities_no_match(self):
        self.assertFalse(self._matches("capabilities"))

    # Bare 'configuration' must NOT match (e.g. "network configuration" is not EDITH config)
    def test_bare_configuration_no_match(self):
        self.assertFalse(self._matches("configuration"))

    # EDITH-scoped config phrases DO match
    def test_your_configuration(self):
        self.assertTrue(self._matches("your configuration"))

    def test_your_settings(self):
        self.assertTrue(self._matches("your settings"))

    # Dotted form — boundary condition (dots break \b)
    def test_dotted_form_in_sentence(self):
        self.assertTrue(self._matches("Display E.D.I.T.H. configuration"))

    def test_dotted_form_question(self):
        self.assertTrue(self._matches("What does E.D.I.T.H. support?"))

    def test_dotted_form_standalone(self):
        # Standalone E.D.I.T.H. — should now match via lookbehind/lookahead
        self.assertTrue(self._matches("E.D.I.T.H."))

    # EDITH possessive and plain
    def test_edith_plain(self):
        self.assertTrue(self._matches("edith"))

    def test_edith_uppercase(self):
        self.assertTrue(self._matches("EDITH"))

    def test_edith_possessive(self):
        self.assertTrue(self._matches("EDITH's"))

    # Pronouns
    def test_your(self):
        self.assertTrue(self._matches("your"))

    def test_yourself(self):
        self.assertTrue(self._matches("yourself"))

    # System phrases
    def test_system_settings(self):
        self.assertTrue(self._matches("system settings"))

    def test_security_clearance(self):
        self.assertTrue(self._matches("security clearance"))

    def test_clearance_level(self):
        self.assertTrue(self._matches("clearance level"))

    def test_do_you_have(self):
        self.assertTrue(self._matches("do you have"))

    def test_what_features_do_you(self):
        self.assertTrue(self._matches("what features do you"))

    # Capitalisation variants
    def test_edith_mixed_case(self):
        self.assertTrue(self._matches("Edith"))

    def test_system_settings_caps(self):
        self.assertTrue(self._matches("System Settings"))


# ---------------------------------------------------------------------------
# 3. Pipeline layer — verify pipeline respects analyzer output (no network)
# ---------------------------------------------------------------------------

class TestPipelineRespectsAnalyzer(unittest.TestCase):
    """VerificationPipeline must not run retrieval when analyzer says bypass."""

    def _make_pipeline_no_network(self):
        """Return a VerificationPipeline whose Retriever is stubbed to blow up if called."""
        from brain.verification.pipeline import VerificationPipeline

        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = AssertionError(
            "Retriever.retrieve() must NOT be called for bypassed queries"
        )
        mock_retriever.build_queries.side_effect = AssertionError(
            "Retriever.build_queries() must NOT be called for bypassed queries"
        )
        return VerificationPipeline(retriever=mock_retriever, log_file=os.devnull)

    def test_self_query_no_retrieval(self):
        pipeline = self._make_pipeline_no_network()
        result = pipeline.run("What is your capability?")
        self.assertFalse(result.requires_verification)
        self.assertEqual(result.answer, "")      # no answer generated by pipeline
        self.assertEqual(result.sources, [])
        self.assertEqual(result.claims, [])

    def test_edith_config_no_retrieval(self):
        pipeline = self._make_pipeline_no_network()
        result = pipeline.run("Display current E.D.I.T.H. configuration.")
        self.assertFalse(result.requires_verification)

    def test_factual_query_uses_retrieval(self):
        """Factual queries still trigger retrieval (retriever returns empty list = unverified)."""
        from brain.verification.pipeline import VerificationPipeline

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_retriever.build_queries.return_value = ["AI research latest"]
        pipeline = VerificationPipeline(retriever=mock_retriever, log_file=os.devnull)
        result = pipeline.run("What happened in the latest AI research?")
        self.assertTrue(result.requires_verification)
        mock_retriever.retrieve.assert_called()

    def test_pipeline_result_valid_on_bypass(self):
        pipeline = self._make_pipeline_no_network()
        result = pipeline.run("How does EDITH work?")
        self.assertTrue(result.valid)  # valid=True set by pipeline when bypass


# ---------------------------------------------------------------------------
# 4. Router integration — verify classifier is on the live code path
# ---------------------------------------------------------------------------

class TestRouterUsesVerificationPipeline(unittest.TestCase):
    """Confirm that brain.router imports and calls the verification pipeline."""

    def test_router_calls_pipeline_run(self):
        """
        We patch get_pipeline().run to record calls.
        If it is never called for an EDITH-config query, the bypass is working.
        For a factual query it should be called.
        """
        from brain.verification import pipeline as pip_module
        from brain.verification.models import VerificationResult

        call_log = []

        real_pipeline = pip_module.get_pipeline()

        def spy_run(query):
            call_log.append(query)
            result = VerificationResult(query, False, "spy")
            result.valid = True
            return result

        with patch.object(real_pipeline, "run", side_effect=spy_run):
            with patch("brain.verification.pipeline.get_pipeline", return_value=real_pipeline):
                # Import router AFTER patch is in place
                import brain.router as router_mod
                import importlib
                importlib.reload(router_mod)

                # For a self-query the router still calls get_pipeline().run(),
                # but the pipeline immediately returns requires_verification=False.
                # The key check is that AFTER pipeline.run, if requires_verification
                # is False, the router does NOT return the verification answer.
                result = router_mod.route("What is your capability?")

        # pipeline.run was called (the router does call it)
        self.assertTrue(len(call_log) >= 1,
                        "router must call verification pipeline for every query")
        # The returned answer should NOT be a verification artefact
        self.assertNotIn("No.", result)
        self.assertNotIn("Verified information:", result)


# ---------------------------------------------------------------------------
# 5. Secret protection — config responses must not expose credentials
# ---------------------------------------------------------------------------

class TestConfigResponseSecretProtection(unittest.TestCase):
    """
    Simulate what EDITH returns for a configuration query.
    The result must not contain API keys, passwords, or token literals.
    """

    def _secret_like(self, text: str) -> list[str]:
        """Return any substrings that look like credentials."""
        patterns = [
            r"sk-[A-Za-z0-9]{20,}",         # OpenAI / Anthropic keys
            r"gsk_[A-Za-z0-9]{20,}",         # Groq keys
            r"AIza[A-Za-z0-9_-]{30,}",       # Google API keys
            r"[A-Za-z0-9]{32,64}",           # generic long token
        ]
        found = []
        for pat in patterns:
            for m in re.finditer(pat, text):
                found.append(m.group(0))
        return found

    def test_pipeline_bypasses_config_query(self):
        """The pipeline must not generate any answer text for a config bypass."""
        from brain.verification.pipeline import VerificationPipeline

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_retriever.build_queries.return_value = []
        pipeline = VerificationPipeline(retriever=mock_retriever, log_file=os.devnull)
        result = pipeline.run("Display current E.D.I.T.H. configuration.")
        # Pipeline answer must be empty — real answer comes from agent/router
        self.assertEqual(result.answer, "",
                         "Pipeline must return empty answer for bypassed queries")

    def test_no_secrets_in_classification_reason(self):
        """QueryAnalyzer reason strings must not contain env var values."""
        from brain.verification.query_analyzer import QueryAnalyzer
        qa = QueryAnalyzer()
        r = qa.analyze("Display current E.D.I.T.H. configuration.")
        leaks = self._secret_like(r.reason)
        self.assertEqual(leaks, [], f"Secret-like strings in reason: {leaks}")


# ---------------------------------------------------------------------------
# Fallback runner (no pytest required)
# ---------------------------------------------------------------------------

def _run_without_pytest():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestQueryAnalyzerSelfBypass,
        TestQueryAnalyzerFactualVerification,
        TestQueryAnalyzerCodingOperational,
        TestSystemOrSelfRegex,
        TestPipelineRespectsAnalyzer,
        TestRouterUsesVerificationPipeline,
        TestConfigResponseSecretProtection,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_without_pytest())
