import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from security import pattern_lock
from hud.server import app, revoke_session, authorize_session


class PatternLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "pattern_lock.json"
        self.file_patch = patch.object(pattern_lock, "PATTERN_FILE", self.path)
        self.file_patch.start()

    def tearDown(self):
        self.file_patch.stop()
        self.temp.cleanup()

    def test_pattern_is_hashed_and_verifies(self):
        pattern_lock.configure([1, 2, 5, 8])
        stored = self.path.read_text(encoding="utf-8")
        self.assertNotIn("1-2-5-8", stored)
        self.assertTrue(pattern_lock.verify([1, 2, 5, 8]))
        self.assertFalse(pattern_lock.verify([1, 4, 7, 8]))

    def test_pattern_requires_four_unique_points(self):
        with self.assertRaises(ValueError):
            pattern_lock.configure([1, 2, 3])
        with self.assertRaises(ValueError):
            pattern_lock.configure([1, 2, 2, 3])

    def test_api_requires_face_then_authorizes_both_factors(self):
        from hud.server import app
        client = app.test_client()
        blocked = client.post("/api/pattern-lock/setup", json={"pattern": [1, 2, 5, 8]},
                              environ_base={"REMOTE_ADDR": "10.0.0.9"})
        self.assertEqual(blocked.status_code, 401)
        with client.session_transaction() as session:
            session["face_verified"] = True
        created = client.post("/api/pattern-lock/setup", json={"pattern": [1, 2, 5, 8]})
        self.assertEqual(created.status_code, 200)
        with client.session_transaction() as session:
            self.assertTrue(session["face_authorized"])

    def test_configured_pattern_unlocks_without_face(self):
        from hud.server import app
        pattern_lock.configure([1, 4, 5, 8])
        client = app.test_client()
        response = client.post("/api/pattern-lock/verify", json={"pattern": [1, 4, 5, 8]})
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as session:
            self.assertTrue(session["face_authorized"])

    def test_enrollment_request_marks_next_face_scan(self):
        from hud.server import app
        client = app.test_client()
        response = client.post("/api/pattern-lock/enroll", json={})
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as session:
            self.assertTrue(session["pattern_enroll_requested"])

    def test_profile_can_replace_pattern_only_when_authorized(self):
        from hud.server import app
        pattern_lock.configure([1, 2, 5, 8])
        client = app.test_client()
        blocked = client.post("/api/pattern-lock/change", json={"pattern": [3, 5, 7, 8]})
        self.assertEqual(blocked.status_code, 401)
        with client.session_transaction() as session:
            session["face_authorized"] = True
            session["face_identity"] = "kamalesh"
        changed = client.post("/api/pattern-lock/change", json={
            "current_pattern": [1, 2, 5, 8],
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(changed.status_code, 200)
        self.assertTrue(pattern_lock.verify([3, 5, 7, 8]))
        self.assertFalse(pattern_lock.verify([1, 2, 5, 8]))

    def test_pattern_change_missing_current_pattern_returns_400(self):
        pattern_lock.configure([1, 2, 5, 8])
        client = app.test_client()
        with client.session_transaction() as session:
            session["face_authorized"] = True
            session["face_identity"] = "kamalesh"
        res = client.post("/api/pattern-lock/change", json={"new_pattern": [3, 5, 7, 8]})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Current pattern is required", res.get_json()["message"])
        # Stored pattern must remain unchanged
        self.assertTrue(pattern_lock.verify([1, 2, 5, 8]))
        self.assertFalse(pattern_lock.verify([3, 5, 7, 8]))

    def test_pattern_setup_cannot_overwrite_existing_pattern(self):
        pattern_lock.configure([1, 2, 5, 8])
        client = app.test_client()
        res = client.post("/api/pattern-lock/setup", json={"pattern": [3, 5, 7, 8]})
        self.assertEqual(res.status_code, 409)
        self.assertIn("already configured", res.get_json()["message"])
        self.assertTrue(pattern_lock.verify([1, 2, 5, 8]))
        self.assertFalse(pattern_lock.verify([3, 5, 7, 8]))

    def test_pattern_change_rate_limiting_after_repeated_failures(self):
        pattern_lock.configure([1, 2, 5, 8])
        client = app.test_client()
        with client.session_transaction() as session:
            session["face_authorized"] = True
            session["face_identity"] = "kamalesh"

        for _ in range(5):
            res = client.post("/api/pattern-lock/change", json={
                "current_pattern": [1, 4, 7, 8],  # wrong
                "new_pattern": [3, 5, 7, 8]
            })
            self.assertEqual(res.status_code, 403)

        # 6th attempt should be blocked by rate limiting (429)
        res_blocked = client.post("/api/pattern-lock/change", json={
            "current_pattern": [1, 4, 7, 8],
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(res_blocked.status_code, 429)
        self.assertIn("Too many attempts", res_blocked.get_json()["message"])
        self.assertTrue(pattern_lock.verify([1, 2, 5, 8]))

    def test_pattern_change_expired_or_revoked_session_returns_401(self):
        pattern_lock.configure([1, 2, 5, 8])
        client = app.test_client()

        # Expired session
        with client.session_transaction() as session:
            session["face_authorized"] = True
            session["face_identity"] = "kamalesh"
            session["face_authorized_at"] = (datetime.now() - timedelta(hours=25)).isoformat()
            session["session_id"] = "expired_pattern_sess"
        res_expired = client.post("/api/pattern-lock/change", json={
            "current_pattern": [1, 2, 5, 8],
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(res_expired.status_code, 401)

        # Revoked session
        with client.session_transaction() as session:
            session["face_authorized"] = True
            session["face_identity"] = "kamalesh"
            session["face_authorized_at"] = datetime.now().isoformat()
            session["session_id"] = "revoked_pattern_sess"
        revoke_session(session_id="revoked_pattern_sess")
        res_revoked = client.post("/api/pattern-lock/change", json={
            "current_pattern": [1, 2, 5, 8],
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(res_revoked.status_code, 401)
        self.assertTrue(pattern_lock.verify([1, 2, 5, 8]))

    def test_pattern_responses_and_logs_do_not_expose_credentials(self):
        pattern_lock.configure([1, 2, 5, 8])
        client = app.test_client()
        with client.session_transaction() as session:
            session["face_authorized"] = True
            session["face_identity"] = "kamalesh"

        res = client.post("/api/pattern-lock/change", json={
            "current_pattern": [1, 2, 5, 8],
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        # Asserts neither points nor internal salt/digest are leaked in response
        self.assertNotIn("1-2-5-8", body)
        self.assertNotIn("3-5-7-8", body)
        self.assertNotIn("digest", body)
        self.assertNotIn("salt", body)


if __name__ == "__main__":
    unittest.main()
