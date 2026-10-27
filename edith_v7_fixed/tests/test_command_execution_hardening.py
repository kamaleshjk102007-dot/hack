"""
Regression tests for command execution hardening and process lifecycle safety.
Verifies:
1. Allowed commands execute correctly.
2. Disallowed commands are rejected.
3. Shell metacharacters and command chaining cannot bypass validation.
4. Path traversal outside approved roots is rejected.
5. Timeouts terminate long-running subprocesses appropriately.
6. Client-supplied approval flags cannot authorize dangerous operations.
7. Modified commands cannot reuse approval for a different operation.
8. Commands cannot bypass restrictions through alternate agent tools.
9. Existing legitimate project workflows continue to work.
10. Error messages and output do not expose secrets.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from brain.agent import (
    _tool_run_shell,
    _tool_run_python,
    _tool_read_file,
    _tool_write_file,
    _tool_list_dir,
    _is_sensitive_path,
    _sanitize_subprocess_env
)
from plugins import universal_control as control
from brain import project_agent
from utils.logger import redact_secrets


class CommandExecutionHardeningTests(unittest.TestCase):

    # -------------------------------------------------------------------------
    # 1. Allowed commands execute correctly
    # -------------------------------------------------------------------------
    def test_allowed_python_inline_command_executes(self):
        result = _tool_run_shell("python -c \"print('edith_verification_ok')\"")
        self.assertIn("edith_verification_ok", result)

    def test_allowed_echo_command_executes(self):
        result = _tool_run_shell("echo safe_allowlist_output")
        self.assertIn("safe_allowlist_output", result)

    def test_allowed_git_version_command_executes(self):
        result = _tool_run_shell("git --version")
        self.assertIn("git version", result.lower())

    # -------------------------------------------------------------------------
    # 2. Disallowed commands are rejected
    # -------------------------------------------------------------------------
    def test_unallowlisted_binary_rejected(self):
        result = _tool_run_shell("powershell -Command Write-Host evil")
        self.assertTrue(result.startswith("BLOCKED:"))

    def test_arbitrary_executable_rejected(self):
        result = _tool_run_shell("netcat -l -p 4444")
        self.assertIn("is not in the safe command allowlist", result)

    def test_destructive_commands_rejected(self):
        for cmd in [
            "del /f /q C:\\important.dat",
            "rmdir /s /q C:\\Users",
            "format E:",
            "shutdown -s -t 0",
            "reg delete HKLM\\Software",
            "net user guest password123",
            "chmod 777 /etc/shadow"
        ]:
            res = _tool_run_shell(cmd)
            self.assertTrue(res.startswith("BLOCKED:"), f"Failed to block: {cmd}")

    # -------------------------------------------------------------------------
    # 3. Shell metacharacters and command chaining cannot bypass validation
    # -------------------------------------------------------------------------
    def test_single_ampersand_chaining_blocked(self):
        result = _tool_run_shell("echo hello & echo injected")
        self.assertIn("BLOCKED:", result)

    def test_pipe_chaining_blocked(self):
        result = _tool_run_shell("dir | findstr secret")
        self.assertIn("BLOCKED:", result)

    def test_redirection_blocked(self):
        result = _tool_run_shell("echo evil > output.txt")
        self.assertIn("BLOCKED:", result)

    def test_semicolon_chaining_blocked(self):
        result = _tool_run_shell("python -c \"print('a')\" ; whoami")
        self.assertIn("BLOCKED:", result)

    def test_newline_chaining_blocked(self):
        result = _tool_run_shell("echo 1\necho 2")
        self.assertIn("BLOCKED:", result)

    def test_command_substitution_blocked(self):
        res1 = _tool_run_shell("echo `whoami`")
        self.assertIn("BLOCKED:", res1)
        res2 = _tool_run_shell("echo $(whoami)")
        self.assertIn("BLOCKED:", res2)

    # -------------------------------------------------------------------------
    # 4. Path traversal outside approved roots is rejected
    # -------------------------------------------------------------------------
    def test_read_file_path_traversal_blocked(self):
        res = _tool_read_file("../../secret_keys.txt")
        self.assertIn("BLOCKED: Path traversal", res)

    def test_write_file_path_traversal_blocked(self):
        res = _tool_write_file("../../../evil.bat", "@echo off")
        self.assertIn("BLOCKED: Path traversal", res)

    def test_list_dir_path_traversal_blocked(self):
        res = _tool_list_dir("../../../")
        self.assertIn("BLOCKED: Path traversal", res)

    def test_sensitive_system_directories_blocked(self):
        self.assertTrue(_is_sensitive_path("C:/Windows/System32/cmd.exe"))
        self.assertTrue(_is_sensitive_path("C:/Windows/SysWOW64"))
        self.assertTrue(_is_sensitive_path("/etc/passwd"))
        self.assertTrue(_is_sensitive_path("/etc/shadow"))
        self.assertTrue(_is_sensitive_path("~/.ssh/id_rsa"))
        self.assertTrue(_is_sensitive_path(".env"))

        res_read = _tool_read_file("C:/Windows/System32/drivers/etc/hosts")
        self.assertIn("BLOCKED:", res_read)

    def test_project_agent_scaffold_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "safe_project"
            blueprint = {
                "folders": ["../../escaped_dir"],
                "files": [
                    {"path": "../escape.py", "description": "Escape attempt"},
                    {"path": "safe.py", "description": "Legitimate file"}
                ]
            }
            project_agent._scaffold(project_dir, blueprint, notify_fn=None)
            escaped_file = Path(tmpdir) / "escape.py"
            self.assertFalse(escaped_file.exists(), "Traversal file was created outside project root!")
            self.assertTrue((project_dir / "safe.py").exists(), "Legitimate file was not created")

    # -------------------------------------------------------------------------
    # 5. Timeouts terminate long-running subprocesses appropriately
    # -------------------------------------------------------------------------
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=15))
    def test_shell_timeout_terminates_and_reports_error(self, mock_run):
        result = _tool_run_shell("pytest")
        self.assertIn("ERROR: Command timed out (15s limit)", result)

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=15))
    def test_python_tool_timeout_terminates_and_reports_error(self, mock_run):
        result = _tool_run_python("import time\ntime.sleep(30)")
        self.assertIn("ERROR: Code execution timed out (15s limit)", result)

    # -------------------------------------------------------------------------
    # 6. Client-supplied approval flags cannot authorize dangerous operations
    # -------------------------------------------------------------------------
    def test_client_supplied_confirmed_flag_cannot_bypass_approval(self):
        # Passing confirmed=True directly MUST NOT execute; must return CONFIRMATION_REQUIRED
        result = control.control("close_app", target="notepad", confirmed=True)
        self.assertIn("CONFIRMATION_REQUIRED", result)

    def test_client_supplied_confirmed_flag_for_high_impact_text(self):
        result = control.control("type_text", text="transfer 50000 dollars now", confirmed=True)
        self.assertIn("CONFIRMATION_REQUIRED", result)

    # -------------------------------------------------------------------------
    # 7. Modified commands cannot reuse approval for a different operation
    # -------------------------------------------------------------------------
    @patch("plugins.universal_control._execute", return_value="SUCCESS: executed")
    def test_modified_command_cannot_reuse_token(self, mock_exec):
        # Generate token for closing notepad
        req = control.control("close_app", target="notepad")
        token = req.split("[")[1].split("]")[0]

        # confirm() executes the bound action and args
        res = control.confirm(token)
        self.assertEqual(res, "SUCCESS: executed")
        mock_exec.assert_called_once_with("close_app", target="notepad", text="", keys=None)

        # Re-using the same token fails
        res_reuse = control.confirm(token)
        self.assertIn("ERROR:", res_reuse)

        # A forged or unknown token fails
        res_fake = control.confirm("DEADBEEF")
        self.assertIn("ERROR:", res_fake)

    # -------------------------------------------------------------------------
    # 8. Commands cannot bypass restrictions through alternate agent tools
    # -------------------------------------------------------------------------
    def test_python_tool_blocks_process_and_shell_calls(self):
        dangerous_snippets = [
            "import os\nos.system('calc')",
            "import subprocess\nsubprocess.run(['notepad'])",
            "import shutil\nshutil.rmtree('/tmp')",
            "import os\nos.remove('/tmp/file')",
            "__import__('os').system('calc')"
        ]
        for snippet in dangerous_snippets:
            res = _tool_run_python(snippet)
            self.assertIn("BLOCKED:", res, f"Failed to block in run_python: {snippet}")

    def test_shell_python_c_blocks_dangerous_subcalls(self):
        # Bypassing run_python by calling `python -c` from run_shell MUST be blocked
        res1 = _tool_run_shell("python -c \"import os; os.system('calc')\"")
        self.assertIn("BLOCKED:", res1)

        res2 = _tool_run_shell("python -c \"import subprocess; subprocess.Popen(['calc'])\"")
        self.assertIn("BLOCKED:", res2)

    def test_shell_node_e_blocks_child_process(self):
        res = _tool_run_shell("node -e \"require('child_process').execSync('calc')\"")
        self.assertIn("BLOCKED:", res)

    # -------------------------------------------------------------------------
    # 9. Existing legitimate project workflows continue to work
    # -------------------------------------------------------------------------
    def test_legitimate_requirements_analysis_workflow(self):
        req = "Build a personal portfolio HTML website with about me, projects, and contact page"
        res = project_agent.run_requirements(req, notify_fn=None)
        text = res[0] if isinstance(res, tuple) else str(res)
        self.assertIn("PORTFOLIO", text.upper())
        self.assertTrue(any(tech in text.upper() for tech in ["HTML", "REACT", "CSS", "FRONTEND"]))

    def test_legitimate_python_math_execution(self):
        res = _tool_run_python("total = sum([x * 2 for x in range(10)])\nprint(f'TOTAL={total}')")
        self.assertIn("TOTAL=90", res)

    # -------------------------------------------------------------------------
    # 10. Error messages and child process outputs do not expose secrets
    # -------------------------------------------------------------------------
    def test_clean_env_strips_api_keys_and_tokens(self):
        os.environ["DUMMY_API_KEY"] = "secret_api_key_12345"
        os.environ["MOCK_TOKEN"] = "secret_token_abcde"
        try:
            clean = _sanitize_subprocess_env()
            self.assertNotIn("DUMMY_API_KEY", clean)
            self.assertNotIn("MOCK_TOKEN", clean)
        finally:
            os.environ.pop("DUMMY_API_KEY", None)
            os.environ.pop("MOCK_TOKEN", None)

    def test_output_and_errors_redact_sensitive_patterns(self):
        raw_error = "Failed with gsk_abcdef1234567890abcdef1234567890 and sk-or-v1-abcdef0123456789abcdef"
        redacted = redact_secrets(raw_error)
        self.assertNotIn("gsk_abcdef1234567890abcdef1234567890", redacted)
        self.assertNotIn("sk-or-v1-abcdef0123456789abcdef", redacted)
        self.assertIn("[REDACTED_GROQ_KEY]", redacted)
        self.assertIn("[REDACTED_OPENROUTER_KEY]", redacted)


if __name__ == "__main__":
    unittest.main()
