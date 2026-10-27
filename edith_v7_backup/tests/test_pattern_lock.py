import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from security import pattern_lock


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
        changed = client.post("/api/pattern-lock/change", json={"pattern": [3, 5, 7, 8]})
        self.assertEqual(changed.status_code, 200)
        self.assertTrue(pattern_lock.verify([3, 5, 7, 8]))
        self.assertFalse(pattern_lock.verify([1, 2, 5, 8]))


if __name__ == "__main__":
    unittest.main()
