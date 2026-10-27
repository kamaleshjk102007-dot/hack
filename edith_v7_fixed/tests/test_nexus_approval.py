"""
Deterministic regression tests for NEXUS task approval binding and lifecycle.

Verifies:
1. Valid approval succeeds for the intended task.
2. Missing token is rejected.
3. Invalid token is rejected.
4. Expired token is rejected.
5. Replayed token is rejected.
6. Token issued for task A cannot approve task B.
7. Changing security-relevant task parameters invalidates approval.
8. Two concurrent approval requests cannot authorize duplicate execution.
9. Direct invocation of the runtime execution path cannot bypass approval.
10. A task that does not require approval preserves its legitimate existing behavior.
11. An unauthorized HTTP caller cannot approve a task.
12. Existing task cancellation and status behavior still works.
"""

import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from nexus.runtime import NexusRuntime
from hud.server import app, authorize_session, FACE_ALLOWED_LABEL


class NexusApprovalSecurityTests(unittest.TestCase):
    def setUp(self):
        self.runtime = NexusRuntime()

    def test_1_valid_approval_succeeds_for_intended_task(self):
        """Valid token successfully approves sensitive task."""
        # Create a task requiring approval
        task = self.runtime.create_task("Delete all temporary cache files", demo=True)
        self.assertTrue(task["requiresApproval"])
        token = task.get("pending_approval_token")
        self.assertIsNotNone(token)
        self.assertIsInstance(token, str)

        approved_task, err = self.runtime.approve(task["id"], token)
        self.assertIsNone(err)
        self.assertIsNotNone(approved_task)
        self.assertTrue(approved_task["approved"])
        self.assertTrue(approved_task["approval_consumed"])
        self.assertNotIn("pending_approval_token", approved_task)

    def test_2_missing_token_is_rejected(self):
        """Missing or empty token fails to approve a sensitive task."""
        task = self.runtime.create_task("Delete the database", demo=True)
        self.assertTrue(task["requiresApproval"])

        # Attempt approve with None
        approved, err = self.runtime.approve(task["id"], None)
        self.assertIsNone(approved)
        self.assertIn("required", err.lower())

        # Attempt approve with empty string
        approved, err = self.runtime.approve(task["id"], "")
        self.assertIsNone(approved)
        self.assertIn("required", err.lower())

        # Task remains unapproved
        self.assertFalse(self.runtime.tasks[task["id"]]["approved"])

    def test_3_invalid_token_is_rejected(self):
        """Unrecognized/bogus token is rejected."""
        task = self.runtime.create_task("Remove system files", demo=True)
        self.assertTrue(task["requiresApproval"])

        approved, err = self.runtime.approve(task["id"], "0123456789abcdef0123456789abcdef")
        self.assertIsNone(approved)
        self.assertIn("invalid or unknown", err.lower())
        self.assertFalse(self.runtime.tasks[task["id"]]["approved"])

    def test_4_expired_token_is_rejected(self):
        """Token past its TTL is rejected."""
        task = self.runtime.create_task("Delete old records", demo=True)
        self.assertTrue(task["requiresApproval"])
        token = task.get("pending_approval_token")

        # Simulate expiration
        with self.runtime.lock:
            self.runtime.approval_tokens[token]["expires_at"] = time.time() - 10

        approved, err = self.runtime.approve(task["id"], token)
        self.assertIsNone(approved)
        self.assertIn("expired", err.lower())
        self.assertFalse(self.runtime.tasks[task["id"]]["approved"])

    def test_5_replayed_token_is_rejected(self):
        """A previously consumed token cannot be reused."""
        task = self.runtime.create_task("Remove log history", demo=True)
        token = task.get("pending_approval_token")

        approved1, err1 = self.runtime.approve(task["id"], token)
        self.assertIsNone(err1)
        self.assertTrue(approved1["approved"])

        # Second attempt with same token
        approved2, err2 = self.runtime.approve(task["id"], token)
        self.assertIsNone(approved2)
        self.assertTrue("already" in err2.lower() or "replay" in err2.lower())

    def test_6_token_issued_for_task_a_cannot_approve_task_b(self):
        """Cross-task token reuse is rejected."""
        task_a = self.runtime.create_task("Delete file A", demo=True)
        task_b = self.runtime.create_task("Delete file B", demo=True)
        token_a = task_a.get("pending_approval_token")

        approved_b, err = self.runtime.approve(task_b["id"], token_a)
        self.assertIsNone(approved_b)
        self.assertIn("different task", err.lower())
        self.assertFalse(self.runtime.tasks[task_b["id"]]["approved"])

    def test_7_changing_security_relevant_task_parameters_invalidates_approval(self):
        """Tampering with task request or parameters invalidates token."""
        task = self.runtime.create_task("Delete cache folder", demo=True)
        token = task.get("pending_approval_token")

        # Tamper with request
        with self.runtime.lock:
            task["request"] = "Delete root folder /"

        approved, err = self.runtime.approve(task["id"], token)
        self.assertIsNone(approved)
        self.assertIn("modified", err.lower())
        self.assertFalse(self.runtime.tasks[task["id"]]["approved"])

    def test_8_two_concurrent_approval_requests_cannot_authorize_duplicate_execution(self):
        """Concurrent approvals with the same token result in exactly one success."""
        task = self.runtime.create_task("Remove temporary files", demo=True)
        token = task.get("pending_approval_token")

        results = []
        barrier = threading.Barrier(2)

        def try_approve():
            barrier.wait()
            res = self.runtime.approve(task["id"], token)
            results.append(res)

        t1 = threading.Thread(target=try_approve)
        t2 = threading.Thread(target=try_approve)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [r for r in results if r[0] is not None]
        failures = [r for r in results if r[0] is None]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)

    def test_9_direct_invocation_of_runtime_execution_path_cannot_bypass_approval(self):
        """Direct call to _run without consuming valid token fails execution."""
        task = self.runtime.create_task("Delete secret files", demo=False)
        # Directly set approved = True without going through approve() with valid token
        with self.runtime.lock:
            task["approved"] = True
            task["approval_consumed"] = False
            task["status"] = "running"

        # Wait for _run thread to process or call _run in a thread
        deadline = time.time() + 4
        while self.runtime.tasks[task["id"]]["status"] not in {"completed", "failed"} and time.time() < deadline:
            time.sleep(0.05)

        finished = self.runtime.tasks[task["id"]]
        self.assertEqual(finished["status"], "failed")
        self.assertIn("Execution rejected", finished["result"]["summary"])

    def test_10_task_that_does_not_require_approval_preserves_legitimate_behavior(self):
        """Tasks not requiring approval execute without needing a token."""
        task = self.runtime.create_task("Create a cube in Blender", demo=True)
        self.assertFalse(task["requiresApproval"])
        self.assertNotIn("pending_approval_token", task)

        deadline = time.time() + 8
        while self.runtime.tasks[task["id"]]["status"] not in {"completed", "failed"} and time.time() < deadline:
            time.sleep(0.05)

        finished = self.runtime.tasks[task["id"]]
        self.assertEqual(finished["status"], "completed")

    def test_11_unauthorized_http_caller_cannot_approve_task(self):
        """Unauthenticated HTTP client cannot hit /api/nexus/tasks/<id>/approve."""
        client = app.test_client()
        resp = client.post("/api/nexus/tasks/fake-id/approve", json={"token": "test"})
        # Should be blocked by require_face_authorization -> 401
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("error"), "face_auth_required")

    def test_12_existing_task_cancellation_and_status_behavior_still_works(self):
        """Cancelling a task updates state to cancelled and invalidates token."""
        task = self.runtime.create_task("Remove logs permanently", demo=True)
        token = task.get("pending_approval_token")
        self.assertIsNotNone(token)

        cancelled = self.runtime.cancel(task["id"])
        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled["status"], "cancelled")

        # Now attempting to approve with the old token is rejected
        approved, err = self.runtime.approve(task["id"], token)
        self.assertIsNone(approved)
        self.assertIn("already", err.lower())


if __name__ == "__main__":
    unittest.main()
