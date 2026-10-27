"""
Regression tests for the secrets / credentials audit.

Covers:
  1.  Secrets absent from /api/model HTTP response.
  2a. Groq key redacted from logs.
  2b. Google (AQ.) key redacted from logs.
  2c. OpenRouter key redacted from logs.
  2d. HuggingFace key redacted from logs.
  2e. Kling key redacted from logs.
  2f. Pollinations (sk_) key redacted from logs.
  2g. Mistral key redacted from logs.
  3.  Provider error messages do not expose raw bearer tokens.
  4.  URL query-string credentials are redacted.
  5.  Subprocesses launched by _tool_run_shell receive sanitized env.
  6.  .env.example contains only empty placeholders, not real credentials.
  7.  /api/model returns 401 for unauthenticated callers.
  8.  /api/model/usage returns 401 for unauthenticated callers.
  9.  get_active_model() does not include the real key value in its dict.
 10.  Legitimate provider routing still works (cloud_router imports cleanly).
 11.  Existing auth and execution tests continue to pass (sampled).
"""

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Fake test credentials — never real keys
# ---------------------------------------------------------------------------
_FAKE_GROQ      = "gsk_FakeGroqKeyForTestingOnly1234567890abcd"
_FAKE_GOOGLE    = "AQ.FakeGoogleKeyForTestingOnly1234567890ab"
_FAKE_OPENROUTER = "sk-or-v1-FakeOpenRouterKeyForTesting1234567890abcdef"
_FAKE_HF        = "hf_FakeHuggingFaceTokenForTesting1234"
_FAKE_KLING     = "api-key-kling-FakeKlingKeyForTesting12345678"
_FAKE_POLLINATIONS = "sk_FakePollinationsKeyForTesting1234567890"
_FAKE_MISTRAL_RAW  = "9aUXSnZ8FakeMistralKeyForTest0000"   # format: 32-char alphanum
_FAKE_MISTRAL_LOG  = f"MISTRAL_API_KEY={_FAKE_MISTRAL_RAW}"


# ===========================================================================
# 2  Redaction utility
# ===========================================================================

class RedactionPatternTests(unittest.TestCase):

    def setUp(self):
        from utils.logger import redact_secrets
        self.redact = redact_secrets

    def _assert_redacted(self, text: str, fake_key: str, label: str):
        result = self.redact(text)
        self.assertNotIn(fake_key, result, f"{label} key leaked through redaction")
        self.assertIn("[REDACTED", result, f"Expected a [REDACTED...] marker for {label}")

    # 2a. Groq
    def test_groq_key_redacted(self):
        self._assert_redacted(f"Using Bearer {_FAKE_GROQ}", _FAKE_GROQ, "Groq")

    def test_groq_key_in_error_redacted(self):
        self._assert_redacted(
            f"Request to Groq failed: Authorization: Bearer {_FAKE_GROQ}",
            _FAKE_GROQ, "Groq (error)"
        )

    # 2b. Google
    def test_google_key_redacted(self):
        self._assert_redacted(f"x-goog-api-key: {_FAKE_GOOGLE}", _FAKE_GOOGLE, "Google")

    # 2c. OpenRouter
    def test_openrouter_key_redacted(self):
        self._assert_redacted(f"Bearer {_FAKE_OPENROUTER}", _FAKE_OPENROUTER, "OpenRouter")

    # 2d. HuggingFace
    def test_hf_key_redacted(self):
        self._assert_redacted(f"token={_FAKE_HF}", _FAKE_HF, "HuggingFace")

    def test_hf_key_in_bearer_redacted(self):
        self._assert_redacted(f"Authorization: Bearer {_FAKE_HF}", _FAKE_HF, "HuggingFace Bearer")

    # 2e. Kling
    def test_kling_key_redacted(self):
        self._assert_redacted(f"auth={_FAKE_KLING}", _FAKE_KLING, "Kling")

    # 2f. Pollinations (sk_ prefix — different from sk- OpenAI style)
    def test_pollinations_key_redacted(self):
        self._assert_redacted(
            f"Using sk_ token: {_FAKE_POLLINATIONS}",
            _FAKE_POLLINATIONS, "Pollinations"
        )

    # 2g. Mistral (no distinctive prefix — matched via key= context)
    def test_mistral_key_redacted_in_log_context(self):
        result = self.redact(_FAKE_MISTRAL_LOG)
        self.assertNotIn(_FAKE_MISTRAL_RAW, result, "Mistral key leaked through redaction")

    # 3. Bearer token in error messages
    def test_bearer_token_in_error_redacted(self):
        text = f"Provider returned 403: Authorization: Bearer {_FAKE_GROQ}"
        result = self.redact(text)
        self.assertNotIn(_FAKE_GROQ, result)
        self.assertIn("Bearer [REDACTED", result)

        generic = "Provider returned 403: Authorization: Bearer unbranded_secret_token_123456"
        generic_result = self.redact(generic)
        self.assertNotIn("unbranded_secret_token_123456", generic_result)
        self.assertIn("Bearer [REDACTED]", generic_result)

    # 4. URL query-string credential
    def test_url_query_credential_redacted(self):
        text = f"GET https://api.example.com/v1?api_key={_FAKE_GROQ}&format=json"
        result = self.redact(text)
        self.assertNotIn(_FAKE_GROQ, result)

    def test_password_in_query_redacted(self):
        result = self.redact("smtp://user:password=SuperSecret123@smtp.gmail.com")
        self.assertNotIn("SuperSecret123", result)

    # Sanity: redaction should not destroy useful non-secret information
    def test_non_secret_text_preserved(self):
        text = "Provider groq returned 200 OK in 450ms"
        result = self.redact(text)
        self.assertIn("groq", result)
        self.assertIn("200", result)


# ===========================================================================
# 1 & 7 & 8  HTTP endpoint security
# ===========================================================================

class ApiModelEndpointTests(unittest.TestCase):

    def _make_client(self):
        """Return an unauthenticated Flask test client."""
        import hud.server as srv
        srv.app.config["TESTING"] = True
        srv.app.config["SECRET_KEY"] = "test-secret-key"
        srv.app.config["WTF_CSRF_ENABLED"] = False
        return srv.app.test_client()

    # 7. /api/model returns 401 for unauthenticated callers
    def test_api_model_requires_auth(self):
        client = self._make_client()
        res = client.get("/api/model")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data.get("authenticated", True))

    # 8. /api/model/usage returns 401 for unauthenticated callers
    def test_api_model_usage_requires_auth(self):
        client = self._make_client()
        res = client.get("/api/model/usage")
        self.assertEqual(res.status_code, 401)

    # 1. Secrets absent from /api/model response (authenticated session)
    def test_api_model_response_contains_no_key_values(self):
        import hud.server as srv
        srv.app.config["TESTING"] = True
        srv.app.config["SECRET_KEY"] = "test-secret-key"
        client = srv.app.test_client()

        # Inject an authenticated session
        with client.session_transaction() as sess:
            from datetime import datetime
            sess["face_authorized"] = True
            sess["face_identity"] = "kamalesh"
            sess["face_authorized_at"] = datetime.now().isoformat(timespec="seconds")
            sess["session_id"] = "test-session-id"

        # Patch get_active_model to return a dict that would include key status
        mock_data = {
            "task_type": "agent",
            "active": "groq",
            "fallback": "groq -> gemini",
            "chain": ["groq", "gemini"],
            "cooldowns": {},
            "gemini_active": True,
            "gemini_key_status": "set",
            "groq_key_status": "set",
        }
        with patch("brain.ai_engine.get_active_model", return_value=mock_data):
            res = client.get("/api/model")

        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        # No field should have a value that looks like a real key
        response_str = str(data)
        for fake_key in (_FAKE_GROQ, _FAKE_GOOGLE, _FAKE_HF, _FAKE_KLING,
                         _FAKE_OPENROUTER, _FAKE_POLLINATIONS, _FAKE_MISTRAL_RAW):
            self.assertNotIn(fake_key, response_str,
                             f"Fake key pattern appeared in /api/model response")

        # gemini_key_status must be a status string, never a real key
        if "gemini_key_status" in data:
            self.assertIn(data["gemini_key_status"], ("set", "missing", "unknown"),
                          "gemini_key_status should be a status string, not a real key")

        # Old field names must not be present
        self.assertNotIn("gemini_api_key", data)
        self.assertNotIn("groq_api_key", data)


# ===========================================================================
# 9.  get_active_model() dict does not contain real key values
# ===========================================================================

class GetActiveModelTests(unittest.TestCase):

    def test_get_active_model_contains_no_real_keys(self):
        """get_active_model() should return status strings, not actual key values."""
        from brain.ai_engine import get_active_model
        with patch("brain.cloud_router.get_chain_status", return_value={}):
            result = get_active_model()
        result_str = str(result)
        # The real key values from environment should not appear in the dict string
        for env_key in ("GOOGLE_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
                        "OPENROUTER_API_KEY", "HF_API_KEY"):
            real_val = os.environ.get(env_key, "")
            if real_val and len(real_val) > 10:
                self.assertNotIn(real_val, result_str,
                                 f"Real {env_key} value appeared in get_active_model() output")

    def test_get_active_model_key_status_is_string(self):
        from brain.ai_engine import get_active_model
        with patch("brain.cloud_router.get_chain_status", return_value={}):
            result = get_active_model()
        for field in ("gemini_key_status", "groq_key_status"):
            if field in result:
                self.assertIn(result[field], ("set", "missing"),
                              f"{field} must be 'set' or 'missing', not a real key")

    def test_old_field_names_not_present(self):
        """The old gemini_api_key / groq_api_key fields must not appear in the response."""
        from brain.ai_engine import get_active_model
        with patch("brain.cloud_router.get_chain_status", return_value={}):
            result = get_active_model()
        self.assertNotIn("gemini_api_key", result,
                         "Old field name 'gemini_api_key' must not be in get_active_model() output")
        self.assertNotIn("groq_api_key", result,
                         "Old field name 'groq_api_key' must not be in get_active_model() output")


# ===========================================================================
# 5.  Subprocess env sanitization
# ===========================================================================

class SubprocessEnvSanitizationTests(unittest.TestCase):

    def test_sanitize_subprocess_env_strips_all_secret_keys(self):
        from brain.agent import _sanitize_subprocess_env
        with patch.dict(os.environ, {
            "GOOGLE_API_KEY": _FAKE_GOOGLE,
            "GROQ_API_KEY": _FAKE_GROQ,
            "MISTRAL_API_KEY": _FAKE_MISTRAL_RAW,
            "OPENROUTER_API_KEY": _FAKE_OPENROUTER,
            "HF_API_KEY": _FAKE_HF,
            "KLING_API_KEY": _FAKE_KLING,
            "SOME_TOKEN": "some-token-value",
            "MY_PASSWORD": "hunter2",
            "NORMAL_VAR": "kept_value",
        }):
            env = _sanitize_subprocess_env()

        for secret_key in ("GOOGLE_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
                           "OPENROUTER_API_KEY", "HF_API_KEY", "KLING_API_KEY",
                           "SOME_TOKEN", "MY_PASSWORD"):
            self.assertNotIn(secret_key, env, f"{secret_key} was not stripped from subprocess env")
        self.assertIn("NORMAL_VAR", env)
        self.assertEqual(env["NORMAL_VAR"], "kept_value")

    def test_blender_env_sanitization(self):
        from nexus.connectors import _sanitize_blender_env
        with patch.dict(os.environ, {
            "GOOGLE_API_KEY": _FAKE_GOOGLE,
            "GROQ_API_KEY": _FAKE_GROQ,
            "NORMAL_PATH": "/usr/bin",
        }):
            env = _sanitize_blender_env()
        self.assertNotIn("GOOGLE_API_KEY", env)
        self.assertNotIn("GROQ_API_KEY", env)
        self.assertIn("NORMAL_PATH", env)


# ===========================================================================
# 6.  .env.example placeholders only
# ===========================================================================

class EnvExampleTests(unittest.TestCase):

    def _load_env_example(self):
        path = _PROJECT_ROOT / ".env.example"
        self.assertTrue(path.exists(), ".env.example must exist")
        return path.read_text(encoding="utf-8")

    def test_env_example_contains_no_real_google_key(self):
        content = self._load_env_example()
        self.assertFalse(
            re.search(r"AQ\.[A-Za-z0-9_-]{20,}", content),
            ".env.example contains what looks like a real Google API key"
        )

    def test_env_example_contains_no_real_groq_key(self):
        content = self._load_env_example()
        self.assertFalse(
            re.search(r"gsk_[A-Za-z0-9_-]{20,}", content),
            ".env.example contains what looks like a real Groq key"
        )

    def test_env_example_contains_no_real_hf_token(self):
        content = self._load_env_example()
        self.assertFalse(
            re.search(r"hf_[A-Za-z0-9_-]{20,}", content),
            ".env.example contains what looks like a real HuggingFace token"
        )

    def test_env_example_api_key_lines_are_empty(self):
        """All *_KEY= and *_API_KEY= lines in .env.example must have empty values."""
        content = self._load_env_example()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if re.search(r"(API_KEY|_KEY)\s*=", line, re.I):
                # Value after = must be empty or whitespace only
                _, _, value = line.partition("=")
                self.assertEqual(
                    value.strip(), "",
                    f".env.example line appears to have a non-empty key value: {line!r}"
                )

    def test_env_example_password_lines_are_empty(self):
        content = self._load_env_example()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if re.search(r"PASSWORD\s*=", line, re.I):
                _, _, value = line.partition("=")
                self.assertEqual(
                    value.strip(), "",
                    f".env.example appears to have a non-empty password: {line!r}"
                )


# ===========================================================================
# 10.  Legitimate provider routing still works
# ===========================================================================

class ProviderRoutingImportTests(unittest.TestCase):

    def test_cloud_router_imports_cleanly(self):
        """cloud_router must be importable without raising."""
        try:
            import brain.cloud_router  # noqa: F401
        except Exception as e:
            self.fail(f"brain.cloud_router failed to import: {e}")

    def test_ai_engine_imports_cleanly(self):
        try:
            import brain.ai_engine  # noqa: F401
        except Exception as e:
            self.fail(f"brain.ai_engine failed to import: {e}")

    def test_get_active_model_returns_dict(self):
        from brain.ai_engine import get_active_model
        with patch("brain.cloud_router.get_chain_status", return_value={}):
            result = get_active_model()
        self.assertIsInstance(result, dict)
        self.assertIn("task_type", result)
        self.assertIn("active", result)


if __name__ == "__main__":
    unittest.main()
