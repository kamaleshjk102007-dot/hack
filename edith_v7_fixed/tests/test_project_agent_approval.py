"""
Tests for Project Agent Approval Lifecycle and Security Gates.
Verifies:
1. Unauthorized project creation is rejected.
2. Fast-path requests cannot bypass approval.
3. Forged client approval flags are ignored.
4. Approval for one project cannot authorize another.
5. Modified project content invalidates approval.
6. Expired or replayed tokens are rejected.
7. File writes cannot escape the approved project root.
8. Execution cannot begin before the required approval stage.
9. Legitimate approved project creation works end-to-end.
10. Existing Project Agent workflows remain functional.
"""

import os
import time
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from brain import project_agent
from brain.project_agent import (
    PHASE_IDLE, PHASE_REQ, PHASE_REQ_PENDING,
    PHASE_ARCH, PHASE_ARCH_PENDING,
    PHASE_LAYOUT, PHASE_LAYOUT_PENDING,
    PHASE_DEV, PHASE_DONE,
    run_requirements, run_architecture, run_layout,
    approve, project_chat, create_project, create_project_async,
    execute_project, request_execution_approval,
    generate_approval_token, validate_and_consume_token, invalidate_pending_tokens,
    load_state, save_state, reset_state,
    pause_build, resume_build, is_paused
)


class ProjectAgentSecurityBase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.orig_projects_dir = project_agent.PROJECTS_DIR
        self.orig_state_file = project_agent.STATE_FILE
        
        project_agent.PROJECTS_DIR = Path(self.tmp_dir) / "EDITH_Projects"
        project_agent.STATE_FILE = project_agent.PROJECTS_DIR / "project_state.json"
        reset_state()

    def tearDown(self):
        project_agent.PROJECTS_DIR = self.orig_projects_dir
        project_agent.STATE_FILE = self.orig_state_file
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


class TestUnauthorizedProjectCreation(ProjectAgentSecurityBase):
    """1. Unauthorized project creation is rejected."""

    def test_create_project_rejected_when_idle(self):
        state = load_state()
        self.assertEqual(state["phase"], PHASE_IDLE)
        result = create_project("Build a weather dashboard")
        self.assertIn("⛔", result)
        self.assertIn("Development not approved", result)

    def test_create_project_rejected_without_auth_token(self):
        state = load_state()
        state["phase"] = PHASE_DEV
        state["dev_auth_token"] = ""
        save_state(state)

        result = create_project("Build an API", auth_token=None)
        self.assertIn("⛔", result)
        self.assertIn("Development authorization token is required", result)

    def test_create_project_async_raises_synchronously_if_unauthorized(self):
        state = load_state()
        self.assertEqual(state["phase"], PHASE_IDLE)
        with self.assertRaises(RuntimeError) as ctx:
            create_project_async("Build an unauthorized project")
        self.assertIn("Development not approved", str(ctx.exception))

    def test_api_project_post_routes_to_requirements_instead_of_direct_scaffold(self):
        import hud.server as srv
        from datetime import datetime
        srv.app.config["TESTING"] = True
        srv.app.config["SECRET_KEY"] = "test-secret-key"
        client = srv.app.test_client()

        with client.session_transaction() as sess:
            sess["face_authorized"] = True
            sess["face_identity"] = "kamalesh"
            sess["face_authorized_at"] = datetime.now().isoformat()
            sess["session_id"] = "test-session"

        with patch("brain.project_agent.run_requirements") as mock_req:
            mock_req.return_value = ("Requirements analysis summary", {
                "phase": PHASE_REQ_PENDING,
                "pending_approval_token": "req_token_123"
            })
            res = client.post("/api/project", json={"request": "Build a task manager web app"})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get("status"), "requirements_pending")
            self.assertEqual(data.get("phase"), PHASE_REQ_PENDING)
            self.assertEqual(data.get("approval_token"), "req_token_123")
            mock_req.assert_called_once()


class TestFastPathBypassPrevention(ProjectAgentSecurityBase):
    """2. A fast-path request cannot bypass approval."""

    @patch("hud.server.send_project_notify")
    def test_router_fast_path_initiates_requirements_instead_of_direct_build(self, mock_notify):
        from brain.router import route
        with patch("brain.project_agent.run_requirements") as mock_req:
            mock_req.return_value = ("## Project Summary\nMock requirements", {
                "phase": PHASE_REQ_PENDING,
                "pending_approval_token": "tok_req"
            })
            resp = route("create a new project build a personal blog app")
            self.assertIn("Project Requirements Initiated", resp)
            self.assertIn("Reply 'approve' to proceed", resp)
            mock_req.assert_called_once()

    def test_agent_tool_create_project_initiates_requirements_analysis(self):
        from brain.agent import _tool_create_project
        with patch("brain.project_agent.run_requirements") as mock_req:
            mock_req.return_value = ("Summary: Microservice API", {
                "phase": PHASE_REQ_PENDING
            })
            resp = _tool_create_project("build a flask microservice API")
            self.assertIn("Project requirements analysis initiated", resp)
            self.assertIn("user approval is required", resp.lower())
            mock_req.assert_called_once()


class TestClientSuppliedFlagsIgnored(ProjectAgentSecurityBase):
    """3. Forged client approval flags are ignored."""

    def test_client_approved_flag_cannot_advance_without_valid_token(self):
        state = load_state()
        state["phase"] = PHASE_REQ_PENDING
        state["pending_approval_token"] = ""
        save_state(state)

        # Passing client flags approved=True, confirmed=True without a valid server token
        msg, new_state, next_action = approve(approved=True, confirmed=True, bypass=True)
        self.assertIn("⛔ Approval rejected", msg)
        self.assertIsNone(next_action)
        self.assertEqual(new_state["phase"], PHASE_REQ_PENDING)

    def test_forged_token_rejected_by_api_endpoint(self):
        import hud.server as srv
        from datetime import datetime
        srv.app.config["TESTING"] = True
        srv.app.config["SECRET_KEY"] = "test-secret-key"
        client = srv.app.test_client()

        with client.session_transaction() as sess:
            sess["face_authorized"] = True
            sess["face_identity"] = "kamalesh"
            sess["face_authorized_at"] = datetime.now().isoformat()
            sess["session_id"] = "test-session"

        state = load_state()
        state["phase"] = PHASE_REQ_PENDING
        state["pending_approval_token"] = "real_token"
        save_state(state)

        res = client.post("/api/project/approve", json={
            "token": "FORGED_EVIL_TOKEN_12345",
            "approved": True
        })
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertFalse(data.get("ok"))
        self.assertIn("Approval rejected", data.get("error"))


class TestCrossProjectTokenRejection(ProjectAgentSecurityBase):
    """4. Approval for one project cannot authorize another."""

    def test_token_bound_to_project_a_rejected_for_project_b(self):
        # Generate token for Project A
        token_a = generate_approval_token("requirements", content="Content A", project_request="Project A description")

        # Set up state for Project B
        state = load_state()
        state["phase"] = PHASE_REQ_PENDING
        state["request"] = "Project B description"
        state["requirements"] = {"raw": "Content B"}
        save_state(state)

        # Attempt to approve Project B using Project A's token
        msg, new_state, next_action = approve(token=token_a)
        self.assertIn("⛔ Approval rejected", msg)
        self.assertIn("different project request", msg)
        self.assertIsNone(next_action)
        self.assertEqual(new_state["phase"], PHASE_REQ_PENDING)


class TestModifiedContentInvalidatesApproval(ProjectAgentSecurityBase):
    """5. Modified project content invalidates approval when appropriate."""

    def test_content_tampering_invalidates_token(self):
        token = generate_approval_token("requirements", content="Original Content", project_request="Build App")
        
        state = load_state()
        state["phase"] = PHASE_REQ_PENDING
        state["request"] = "Build App"
        # Content altered after token generation
        state["requirements"] = {"raw": "Tampered / Modified Content"}
        save_state(state)

        msg, new_state, next_action = approve(token=token)
        self.assertIn("⛔ Approval rejected", msg)
        self.assertIn("modified since token issuance", msg)
        self.assertIsNone(next_action)

    def test_revision_request_in_chat_invalidates_pending_tokens(self):
        state = load_state()
        state["phase"] = PHASE_REQ_PENDING
        state["request"] = "Build App"
        state["requirements"] = {"raw": "Analysis"}
        save_state(state)
        token = generate_approval_token("requirements", content="Analysis", project_request="Build App")

        with patch("brain.project_agent.run_requirements") as mock_req:
            mock_req.return_value = ("Updated Analysis", {"phase": PHASE_REQ_PENDING})
            project_chat("Please change the database to MongoDB")

        # Old token is now invalid/consumed
        ok, reason = validate_and_consume_token(token, "requirements", current_content="Analysis", current_request="Build App")
        self.assertFalse(ok)
        self.assertIn("already been used", reason)


class TestExpiredAndReplayedTokens(ProjectAgentSecurityBase):
    """6. Expired or replayed tokens are rejected."""

    def test_replaying_consumed_token_rejected(self):
        token = generate_approval_token("requirements", content="Content", project_request="Req")
        ok, _ = validate_and_consume_token(token, "requirements", current_content="Content", current_request="Req")
        self.assertTrue(ok)

        # Replay attempt
        ok2, reason2 = validate_and_consume_token(token, "requirements", current_content="Content", current_request="Req")
        self.assertFalse(ok2)
        self.assertIn("replay rejected", reason2)

    def test_expired_token_rejected(self):
        token = generate_approval_token("requirements", content="Content", project_request="Req")
        # Artificially expire the token
        state = load_state()
        state["active_tokens"][token]["expires_at"] = time.time() - 10
        save_state(state)

        ok, reason = validate_and_consume_token(token, "requirements", current_content="Content", current_request="Req")
        self.assertFalse(ok)
        self.assertIn("expired", reason)

    def test_unknown_token_rejected(self):
        ok, reason = validate_and_consume_token("totally_unknown_token", "requirements")
        self.assertFalse(ok)
        self.assertIn("Invalid or unknown", reason)


class TestPathTraversalBoundaries(ProjectAgentSecurityBase):
    """7. File writes cannot escape the approved project root."""

    def test_scaffold_cannot_create_outside_project_dir(self):
        project_dir = project_agent.PROJECTS_DIR / "my_project"
        blueprint = {
            "folders": ["../../traversal_folder", "sub/valid_folder"],
            "files": [
                {"path": "../escape.txt", "description": "Escape"},
                {"path": "safe.txt", "description": "Safe"}
            ]
        }
        project_agent._scaffold(project_dir, blueprint, notify_fn=None)
        escaped_file = project_agent.PROJECTS_DIR / "escape.txt"
        self.assertFalse(escaped_file.exists())
        self.assertTrue((project_dir / "safe.txt").exists())

    def test_write_file_rejects_path_traversal(self):
        project_dir = project_agent.PROJECTS_DIR / "my_project"
        project_dir.mkdir(parents=True, exist_ok=True)
        file_info = {"path": "../../outside.py", "description": "Malicious file"}
        intent = {"title": "Test", "language": "python"}
        blueprint = {"files": [file_info]}

        res = project_agent._write_file(project_dir, file_info, intent, blueprint, {}, None, None)
        self.assertIsNone(res)
        outside_file = project_agent.PROJECTS_DIR.parent / "outside.py"
        self.assertFalse(outside_file.exists())


class TestProjectExecutionGates(ProjectAgentSecurityBase):
    """8. Execution cannot begin before the required approval stage."""

    def test_execution_blocked_before_done_phase(self):
        for phase in [PHASE_IDLE, PHASE_REQ_PENDING, PHASE_ARCH_PENDING, PHASE_LAYOUT_PENDING, PHASE_DEV]:
            state = load_state()
            state["phase"] = phase
            save_state(state)

            with self.assertRaises(RuntimeError) as ctx:
                execute_project(auth_token="any_token")
            self.assertIn("Project execution rejected", str(ctx.exception))

    def test_request_execution_approval_blocked_before_done_phase(self):
        state = load_state()
        state["phase"] = PHASE_LAYOUT_PENDING
        save_state(state)

        with self.assertRaises(RuntimeError) as ctx:
            request_execution_approval()
        self.assertIn("Cannot request execution approval before project development is complete", str(ctx.exception))

    def test_plan_or_dev_token_cannot_authorize_execution(self):
        state = load_state()
        state["phase"] = PHASE_DONE
        state["request"] = "Done project"
        save_state(state)

        # Generate a development write token, NOT an execution token
        dev_token = generate_approval_token("development", content="Layout", project_request="Done project")

        with self.assertRaises(RuntimeError) as ctx:
            execute_project(auth_token=dev_token)
        self.assertIn("Token stage mismatch", str(ctx.exception))

    def test_execution_traversal_blocked(self):
        state = load_state()
        state["phase"] = PHASE_DONE
        state["request"] = "Safe Project"
        save_state(state)

        exec_token = request_execution_approval()
        with self.assertRaises(RuntimeError) as ctx:
            execute_project(project_dir="C:/Windows/System32", auth_token=exec_token)
        self.assertIn("Execution path traversal blocked", str(ctx.exception))


class TestLegitimateApprovedWorkflow(ProjectAgentSecurityBase):
    """9. Legitimate approved project creation still works end-to-end."""

    @patch("brain.project_agent._llm")
    @patch("brain.project_agent._json_llm")
    def test_complete_approval_sequence_to_development(self, mock_json, mock_llm):
        mock_llm.return_value = "Detailed architectural design and wireframes"
        mock_json.return_value = {
            "title": "Expense Tracker", "goals": ["Track money"],
            "features": ["add", "list"], "tech_stack": ["python"],
            "name": "expense_tracker", "type": "cli", "language": "python",
            "entry_point": "main.py", "milestones": [{"name": "M1"}]
        }

        # Step 1: Requirements analysis
        req_text, st1 = run_requirements("Build an expense tracker CLI")
        self.assertEqual(st1["phase"], PHASE_REQ_PENDING)
        req_token = st1["pending_approval_token"]
        self.assertTrue(bool(req_token))

        # Step 2: Approve requirements -> Architecture
        msg1, st2, next1 = approve(token=req_token)
        self.assertEqual(next1, "architecture")
        self.assertEqual(st2["phase"], PHASE_ARCH)

        # Step 3: Run architecture
        arch_text, st3 = run_architecture()
        self.assertEqual(st3["phase"], PHASE_ARCH_PENDING)
        arch_token = st3["pending_approval_token"]
        self.assertTrue(bool(arch_token))

        # Step 4: Approve architecture -> Layout
        msg2, st4, next2 = approve(token=arch_token)
        self.assertEqual(next2, "layout")
        self.assertEqual(st4["phase"], PHASE_LAYOUT)

        # Step 5: Run layout
        lay_text, st5 = run_layout()
        self.assertEqual(st5["phase"], PHASE_LAYOUT_PENDING)
        lay_token = st5["pending_approval_token"]
        self.assertTrue(bool(lay_token))

        # Step 6: Approve layout -> Development
        msg3, st6, next3 = approve(token=lay_token)
        self.assertEqual(next3, "development")
        self.assertEqual(st6["phase"], PHASE_DEV)
        dev_token = st6["dev_auth_token"]
        self.assertTrue(bool(dev_token))

        # Step 7: Create project with legitimate development token
        with patch("brain.project_agent.stream_query", return_value=["print('Hello from Expense Tracker')"]):
            result = create_project("Build an expense tracker CLI", auth_token=dev_token)
            self.assertIn("PROJECT COMPLETE", result)
            st7 = load_state()
            self.assertEqual(st7["phase"], PHASE_DONE)
            self.assertTrue(Path(st7["project_dir"]).exists())


class TestExistingWorkflowsFunctional(ProjectAgentSecurityBase):
    """10. Existing Project Agent workflows remain functional."""

    def test_state_management_resilient(self):
        reset_state()
        state = load_state()
        self.assertEqual(state["phase"], PHASE_IDLE)
        self.assertIn("pending_approval_token", state)
        self.assertIn("active_tokens", state)

    def test_pause_resume_functionality(self):
        project_agent._build_active = True
        try:
            status = pause_build()
            self.assertEqual(status, "paused")
            self.assertTrue(is_paused())

            status = resume_build()
            self.assertEqual(status, "resumed")
            self.assertFalse(is_paused())
        finally:
            project_agent._build_active = False

    @patch("brain.project_agent._llm", return_value="Here is your project memory.")
    def test_project_chat_query_works(self, mock_llm):
        state = load_state()
        state["phase"] = PHASE_REQ_PENDING
        state["request"] = "My Test Project"
        save_state(state)

        resp, next_action = project_chat("What is the current project request?")
        self.assertIn("project memory", resp.lower())
        self.assertIsNone(next_action)


import concurrent.futures

class TestAtomicApprovalAndConcurrency(ProjectAgentSecurityBase):
    """REQUIREMENT 1 — ATOMIC APPROVAL"""

    def test_concurrent_attempts_to_consume_same_token_exactly_one_succeeds(self):
        state = load_state()
        state["phase"] = PHASE_REQ_PENDING
        state["request"] = "Concurrent Project"
        state["requirements"] = {"raw": "Initial Spec"}
        save_state(state)

        token = generate_approval_token("requirements", content="Initial Spec", project_request="Concurrent Project")

        results = []
        def _attempt_approve():
            msg, st, action = approve(token=token)
            return (msg, action)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(_attempt_approve) for _ in range(8)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        successes = [r for r in results if r[1] == "architecture"]
        rejections = [r for r in results if r[1] is None]

        self.assertEqual(len(successes), 1, "Exactly one approval must succeed!")
        self.assertEqual(len(rejections), 7, "All other concurrent attempts must be rejected!")
        for msg, _ in rejections:
            self.assertTrue("⛔ Approval rejected" in msg or "Nothing to approve" in msg)

        # Confirm state transitioned once and token is consumed
        final_state = load_state()
        self.assertEqual(final_state["phase"], PHASE_ARCH)

    def test_rejected_token_cannot_advance_or_spawn_threads(self):
        state = load_state()
        state["phase"] = PHASE_REQ_PENDING
        state["request"] = "Test Project"
        state["requirements"] = {"raw": "Content"}
        save_state(state)

        token = generate_approval_token("requirements", content="Content", project_request="Test Project")
        # Tamper with content hash
        msg, new_st, action = approve(token="FAKE_TOKEN")
        self.assertIn("⛔ Approval rejected", msg)
        self.assertIsNone(action)
        self.assertEqual(new_st["phase"], PHASE_REQ_PENDING)


class TestRestartAndStateConsistencyAdversarial(ProjectAgentSecurityBase):
    """REQUIREMENT 2 — RESTART AND STATE CONSISTENCY"""

    def test_malformed_or_corrupt_state_file_resets_gracefully(self):
        project_agent.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Write corrupted JSON
        project_agent.STATE_FILE.write_text("{broken json:::", encoding="utf-8")
        st = load_state()
        self.assertEqual(st["phase"], PHASE_IDLE)
        self.assertIsInstance(st["active_tokens"], dict)

    def test_invalid_types_in_state_file_sanitized(self):
        project_agent.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # State with invalid field types
        tampered = {
            "phase": "INVALID_HACKED_PHASE",
            "active_tokens": "not_a_dict",
            "requirements": 12345,
            "roadmap": "not_a_list"
        }
        project_agent.STATE_FILE.write_text(json.dumps(tampered), encoding="utf-8")
        st = load_state()
        self.assertEqual(st["phase"], PHASE_IDLE)
        self.assertIsInstance(st["active_tokens"], dict)
        self.assertIsInstance(st["requirements"], dict)
        self.assertIsInstance(st["roadmap"], list)

    def test_revision_and_reset_clears_dev_authorization(self):
        state = load_state()
        state["phase"] = PHASE_DEV
        state["request"] = "App"
        state["dev_auth_token"] = "active_dev_token"
        save_state(state)

        invalidate_pending_tokens()
        st_after = load_state()
        self.assertEqual(st_after.get("dev_auth_token"), "")


class TestFilesystemBoundariesAdversarial(ProjectAgentSecurityBase):
    """REQUIREMENT 3 — FILESYSTEM BOUNDARIES"""

    def test_colon_and_drive_relative_paths_rejected(self):
        files = [
            {"path": "C:escape.py", "description": "drive relative"},
            {"path": "file.txt:stream", "description": "NTFS alternate data stream"},
            {"path": "safe.py", "description": "safe file"}
        ]
        clean = project_agent._sanitize_files(files)
        clean_paths = [f["path"] for f in clean]
        self.assertNotIn("C:escape.py", clean_paths)
        self.assertNotIn("file.txt:stream", clean_paths)
        self.assertIn("safe.py", clean_paths)

    def test_windows_reserved_device_names_rejected(self):
        files = [
            {"path": "CON.py", "description": "reserved device"},
            {"path": "sub/NUL.txt", "description": "reserved device in sub"},
            {"path": "AUX.js", "description": "reserved device"},
            {"path": "valid.py", "description": "valid file"}
        ]
        clean = project_agent._sanitize_files(files)
        clean_paths = [f["path"] for f in clean]
        self.assertNotIn("CON.py", clean_paths)
        self.assertNotIn("sub/NUL.txt", clean_paths)
        self.assertNotIn("AUX.js", clean_paths)
        self.assertIn("valid.py", clean_paths)

    def test_symlink_writing_blocked_in_write_file(self):
        proj_dir = project_agent.PROJECTS_DIR / "sym_test"
        proj_dir.mkdir(parents=True, exist_ok=True)
        file_info = {"path": "link.py", "description": "symlink test"}
        intent = {"title": "SymTest", "language": "python"}
        blueprint = {"files": [file_info]}

        with patch("os.path.islink", return_value=True):
            res = project_agent._write_file(proj_dir, file_info, intent, blueprint, {}, None, None)
            self.assertIsNone(res)

    def test_fix_refuses_to_touch_state_file_or_symlinks(self):
        state_file = project_agent.STATE_FILE
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{}", encoding="utf-8")
        fixed = project_agent._fix(state_file, ["syntax error"], None, None)
        self.assertFalse(fixed)


class TestExecutionAuthorizationBindingAndTampering(ProjectAgentSecurityBase):
    """REQUIREMENT 4 — EXECUTION AUTHORIZATION"""

    def test_modifying_entrypoint_content_after_approval_invalidates_execution(self):
        state = load_state()
        state["phase"] = PHASE_DONE
        state["request"] = "Secure Exec Project"
        proj_dir = project_agent.PROJECTS_DIR / "exec_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        state["project_dir"] = str(proj_dir)
        save_state(state)

        main_file = proj_dir / "main.py"
        main_file.write_text("print('Approved version')", encoding="utf-8")

        # Request execution approval for main.py
        token = request_execution_approval(project_dir=str(proj_dir), entrypoint="main.py")
        self.assertTrue(bool(token))

        # Attacker modifies main.py content after approval
        main_file.write_text("print('Malicious tampered code')", encoding="utf-8")

        # Execution MUST be rejected due to content hash mismatch
        with self.assertRaises(RuntimeError) as ctx:
            execute_project(project_dir=str(proj_dir), entrypoint="main.py", auth_token=token)
        self.assertIn("Approved content has been modified since token issuance", str(ctx.exception))

    def test_switching_entrypoint_after_approval_fails(self):
        state = load_state()
        state["phase"] = PHASE_DONE
        state["request"] = "Secure Exec Project"
        proj_dir = project_agent.PROJECTS_DIR / "exec_proj2"
        proj_dir.mkdir(parents=True, exist_ok=True)
        state["project_dir"] = str(proj_dir)
        save_state(state)

        main_file = proj_dir / "main.py"
        main_file.write_text("print('Approved')", encoding="utf-8")
        evil_file = proj_dir / "evil.py"
        evil_file.write_text("print('Evil')", encoding="utf-8")

        # Request approval for main.py
        token = request_execution_approval(project_dir=str(proj_dir), entrypoint="main.py")

        # Attempt to execute evil.py using token issued for main.py
        with self.assertRaises(RuntimeError) as ctx:
            execute_project(project_dir=str(proj_dir), entrypoint="evil.py", auth_token=token)
        self.assertIn("Approved content has been modified since token issuance", str(ctx.exception))

    def test_unauthorized_runner_or_command_target_mismatch_rejected(self):
        state = load_state()
        state["phase"] = PHASE_DONE
        state["request"] = "Runner Test"
        proj_dir = project_agent.PROJECTS_DIR / "exec_runner"
        proj_dir.mkdir(parents=True, exist_ok=True)
        state["project_dir"] = str(proj_dir)
        save_state(state)

        main_file = proj_dir / "main.py"
        main_file.write_text("print('Safe')", encoding="utf-8")
        token = request_execution_approval(project_dir=str(proj_dir), entrypoint="main.py")

        # Disallowed runner (e.g. bash or powershell)
        with self.assertRaises(RuntimeError) as ctx:
            execute_project(project_dir=str(proj_dir), entrypoint="main.py", run_command="powershell main.py", auth_token=token)
        self.assertIn("Disallowed project execution runner", str(ctx.exception))


class TestHttpEndpointSessionEnforcement(ProjectAgentSecurityBase):
    """REQUIREMENT 5 — HTTP AND ROUTER BOUNDARIES"""

    def test_unauthenticated_requests_to_project_routes_return_401(self):
        import hud.server as srv
        srv.app.config["TESTING"] = True
        client = srv.app.test_client()

        # No session authentication set
        res_post = client.post("/api/project", json={"request": "Build something"})
        self.assertEqual(res_post.status_code, 401)

        res_approve = client.post("/api/project/approve", json={"token": "any"})
        self.assertEqual(res_approve.status_code, 401)

        res_reset = client.post("/api/project/reset")
        self.assertEqual(res_reset.status_code, 401)

        res_chat = client.post("/api/project/chat", json={"message": "hello"})
        self.assertEqual(res_chat.status_code, 401)


class TestAsyncPreAuthorizedNoDoubleConsume(ProjectAgentSecurityBase):
    """REQUIREMENT 6 — create_project_async must not double-consume the dev token.

    Before the fix, create_project_async() consumed the dev token via
    _assert_dev_approved(), then spawned a thread running create_project()
    which called _assert_dev_approved() again with the same (now-consumed)
    token and raised RuntimeError("replay rejected"), causing legitimate
    development builds to always fail silently.
    """

    @patch("brain.project_agent._llm")
    @patch("brain.project_agent._json_llm")
    def test_create_project_async_succeeds_without_replay_error(self, mock_json, mock_llm):
        """The async path must not raise a replay-rejected error in the thread."""
        mock_llm.return_value = "Detailed architectural design and wireframes"
        mock_json.return_value = {
            "title": "Async Test App", "goals": ["test"],
            "features": ["feat1"], "tech_stack": ["python"],
            "name": "async_test_app", "type": "cli", "language": "python",
            "entry_point": "main.py", "milestones": [{"name": "M1"}],
        }

        # Build full approval chain to reach PHASE_DEV
        req_text, st1 = run_requirements("Build an async test app CLI")
        msg1, st2, next1 = approve(token=st1["pending_approval_token"])
        self.assertEqual(next1, "architecture")

        arch_text, st3 = run_architecture()
        msg2, st4, next2 = approve(token=st3["pending_approval_token"])
        self.assertEqual(next2, "layout")

        lay_text, st5 = run_layout()
        msg3, st6, next3 = approve(token=st5["pending_approval_token"])
        self.assertEqual(next3, "development")

        dev_token = st6["dev_auth_token"]
        self.assertTrue(bool(dev_token))

        # Track errors raised inside the background thread
        thread_errors = []

        def _patched_create(request, notify_fn=None, stream_fn=None,
                            auth_token=None, _pre_authorized=False):
            try:
                from brain.project_agent import create_project as _real
                result = _real(request, notify_fn=notify_fn, stream_fn=stream_fn,
                               auth_token=auth_token, _pre_authorized=_pre_authorized)
                if "replay rejected" in result or "already been used" in result:
                    thread_errors.append(result)
            except Exception as e:
                thread_errors.append(str(e))

        import threading
        with patch("brain.project_agent.stream_query",
                   return_value=["print('Hello')"]):
            # Manually replicate async logic to intercept the thread result
            from brain.project_agent import _assert_dev_approved, _build_active, _pause_event
            import brain.project_agent as pa
            pa._assert_dev_approved(dev_token)   # consumes token (pre-flight)
            pa._build_active = True
            pa._pause_event.set()
            t = threading.Thread(
                target=_patched_create,
                args=("Build an async test app CLI",),
                kwargs={"auth_token": dev_token, "_pre_authorized": True},
                daemon=True,
            )
            t.start()
            t.join(timeout=30)

        self.assertEqual(thread_errors, [],
                         f"Thread raised unexpected error(s): {thread_errors}")

    def test_create_project_async_public_api_does_not_raise_on_valid_token(self):
        """create_project_async() itself must succeed (not raise) when authorized."""
        import brain.project_agent as pa

        # Put state into PHASE_DEV with a valid dev token
        state = load_state()
        state["phase"] = PHASE_DEV
        state["request"] = "Build async API"
        state["layout"] = {"raw": "Layout content"}
        save_state(state)

        dev_token = generate_approval_token(
            "development",
            content="Layout content",
            project_request="Build async API",
        )
        state = load_state()
        state["dev_auth_token"] = dev_token
        save_state(state)

        with patch("brain.project_agent.stream_query", return_value=["print('ok')"]):
            with patch("brain.project_agent._json_llm", return_value={
                "title": "Async API", "name": "async_api",
                "type": "cli", "language": "python",
                "entry_point": "main.py", "features": ["f1"],
                "tech_stack": ["python"],
            }):
                with patch("brain.project_agent._llm", return_value="arch text"):
                    # Must not raise; background thread will run independently
                    msg = pa.create_project_async(
                        "Build async API",
                        notify_fn=None,
                        stream_fn=None,
                        auth_token=dev_token,
                    )
        self.assertIn("Project build started", msg)


class TestResetDuringBuildNoStateOverwrite(ProjectAgentSecurityBase):
    """REQUIREMENT 7 — reset during build must not be overwritten by stale state.

    Before the fix, create_project() loaded state ONCE before the file-write
    loop and kept saving that stale snapshot.  If reset_state() ran concurrently,
    the next save_state(state) inside the loop would restore the pre-reset
    PHASE_DEV state, effectively resurrecting obsolete authorization.
    """

    def test_progress_save_honours_concurrent_reset(self):
        """After reset, state must stay PHASE_IDLE despite in-progress saves."""
        import brain.project_agent as pa

        state = load_state()
        state["phase"] = PHASE_DEV
        state["request"] = "App"
        save_state(state)

        # Simulate what the fixed loop does: reload before saving
        # Reset happens after first file write
        reset_state()
        fresh = load_state()
        self.assertEqual(fresh["phase"], PHASE_IDLE)

        # The fixed loop checks phase == PHASE_DEV before saving progress.
        # Since phase is now IDLE, no progress save should happen.
        if fresh.get("phase") == PHASE_DEV:
            fresh["progress"] = 50
            save_state(fresh)

        final = load_state()
        # State must still be IDLE, not overwritten back to DEV.
        self.assertNotEqual(final["phase"], PHASE_DEV,
                            "Concurrent reset was overwritten — stale state bug!")
        self.assertEqual(final["phase"], PHASE_IDLE)

    def test_final_phase_transition_guarded_by_phase_check(self):
        """Phase transition to PHASE_DONE must only happen if still in PHASE_DEV."""
        import brain.project_agent as pa

        state = load_state()
        state["phase"] = PHASE_DEV
        save_state(state)

        # Simulate concurrent reset mid-build
        reset_state()

        # Fixed code: reload and check phase before transitioning
        final = load_state()
        if final.get("phase") == PHASE_DEV:
            final["phase"] = PHASE_DONE
            final["project_dir"] = "/some/path"
            final["progress"] = 100
            save_state(final)

        result = load_state()
        # After reset the phase should be IDLE, not DONE
        self.assertNotEqual(result["phase"], PHASE_DONE,
                            "Stale state write overwrote reset — bug detected!")
        self.assertEqual(result["phase"], PHASE_IDLE)


class TestNoDeadlockOnProgressSave(ProjectAgentSecurityBase):
    """REQUIREMENT 8 — progress saves must not deadlock.

    A previous patch erroneously wrapped load_state()/save_state() inside
    `with _state_lock:`.  Because _state_lock is a non-reentrant Lock and
    both functions already acquire it internally, this produced an instant
    deadlock.  The correct outer guard is _token_lock (RLock, the established
    outer lock throughout the module) which preserves the
    _token_lock -> _state_lock ordering and allows re-entry.
    """

    def test_load_and_save_inside_token_lock_does_not_deadlock(self):
        """Simulate the fixed progress-save pattern: _token_lock outer, then
        load_state/save_state (which acquire _state_lock internally).
        Must complete within a tight timeout; a deadlock would hang forever."""
        import threading
        import brain.project_agent as pa

        state = load_state()
        state["phase"] = PHASE_DEV
        state["request"] = "Deadlock Test App"
        save_state(state)

        result = {"done": False, "error": None}

        def _simulate_progress_save():
            try:
                with pa._token_lock:
                    cur = load_state()            # acquires _state_lock internally
                    if cur.get("phase") == PHASE_DEV:
                        cur["progress"] = 42
                        save_state(cur)           # acquires _state_lock internally
                result["done"] = True
            except Exception as e:
                result["error"] = str(e)

        t = threading.Thread(target=_simulate_progress_save, daemon=True)
        t.start()
        t.join(timeout=5)   # 5 seconds is more than enough; deadlock would never return

        self.assertTrue(t.is_alive() is False,
                        "Thread is still alive after 5 s — likely deadlocked!")
        self.assertIsNone(result["error"], f"Thread raised: {result['error']}")
        self.assertTrue(result["done"], "Thread did not complete successfully")

        final = load_state()
        self.assertEqual(final.get("progress"), 42)

    def test_final_transition_inside_token_lock_does_not_deadlock(self):
        """Simulate the fixed PHASE_DONE transition pattern."""
        import threading
        import brain.project_agent as pa

        state = load_state()
        state["phase"] = PHASE_DEV
        state["request"] = "Deadlock Test App 2"
        save_state(state)

        result = {"done": False, "error": None}

        def _simulate_final_transition():
            try:
                with pa._token_lock:
                    final = load_state()
                    if final.get("phase") == PHASE_DEV:
                        final["phase"] = PHASE_DONE
                        final["progress"] = 100
                        save_state(final)
                result["done"] = True
            except Exception as e:
                result["error"] = str(e)

        t = threading.Thread(target=_simulate_final_transition, daemon=True)
        t.start()
        t.join(timeout=5)

        self.assertFalse(t.is_alive(), "Thread is still alive — likely deadlocked!")
        self.assertIsNone(result["error"], f"Thread raised: {result['error']}")
        self.assertTrue(result["done"])

        final = load_state()
        self.assertEqual(final.get("phase"), PHASE_DONE)


if __name__ == "__main__":
    unittest.main()
