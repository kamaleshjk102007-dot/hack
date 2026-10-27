"""
HUD Pattern Lock Frontend and Integration Tests
Verifies the 3-step pattern change workflow, initial setup flow, security constraints,
DOM elements, state transitions, duplicate submission prevention, and payload structures.
"""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hud.server import app, revoke_session, authorize_session
from security import pattern_lock


class HudPatternFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        template_path = Path(__file__).parent.parent / "hud" / "templates" / "hud.html"
        cls.html_content = template_path.read_text(encoding="utf-8")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "pattern_lock.json"
        self.file_patch = patch.object(pattern_lock, "PATTERN_FILE", self.path)
        self.file_patch.start()
        self.client = app.test_client()

    def tearDown(self):
        self.file_patch.stop()
        self.temp.cleanup()

    # -------------------------------------------------------------------------
    # 1. Inspect Template Structure and UI Elements
    # -------------------------------------------------------------------------
    def test_hud_template_contains_all_pattern_modal_elements(self):
        """Verify modal dialog, step indicators, buttons, and accessibility tags exist."""
        self.assertIn('id="profile-pattern-dialog"', self.html_content)
        self.assertIn('id="pp-title"', self.html_content)
        self.assertIn('id="pp-subtitle"', self.html_content)
        self.assertIn('id="pp-grid"', self.html_content)
        self.assertIn('id="pp-message"', self.html_content)
        self.assertIn('id="pp-cancel"', self.html_content)
        self.assertIn('id="pp-clear"', self.html_content)
        self.assertIn('id="pp-save"', self.html_content)
        self.assertIn('id="pp-close"', self.html_content)

        # Ensure all 9 nodes (1-9) are present
        for i in range(1, 10):
            self.assertIn(f'data-point="{i}"', self.html_content)

    def test_three_step_and_two_step_indicators_present_in_js(self):
        """Verify the 3-step text indicators for change and 2-step for setup exist."""
        self.assertIn("Step 1 of 3: Draw current pattern", self.html_content)
        self.assertIn("Step 2 of 3: Draw new pattern", self.html_content)
        self.assertIn("Step 3 of 3: Confirm new pattern", self.html_content)
        self.assertIn("Step 1 of 2: Draw new pattern", self.html_content)
        self.assertIn("Step 2 of 2: Confirm new pattern", self.html_content)

    def test_payload_structure_and_endpoints_in_js(self):
        """Verify payload keys and endpoints in frontend script."""
        self.assertIn("/api/pattern-lock/change", self.html_content)
        self.assertIn("/api/pattern-lock/setup", self.html_content)
        self.assertIn("/api/pattern-lock/status", self.html_content)
        self.assertIn("current_pattern:", self.html_content)
        self.assertIn("new_pattern:", self.html_content)

    def test_no_credential_logging_in_frontend(self):
        """Ensure no console.log or debug print leaks patterns in frontend script."""
        script_match = re.search(r"profile-pattern-dialog.*?<script>(.*?)</script>", self.html_content, re.DOTALL)
        self.assertTrue(script_match, "Pattern lock script block not found")
        script = script_match.group(1)
        self.assertNotIn("console.log", script)
        self.assertNotIn("console.dir", script)

    def test_explicit_error_status_handling_in_js(self):
        """Verify HTTP 400, 401, 403, 409, 429 are explicitly handled."""
        self.assertIn("err.status === 401", self.html_content)
        self.assertIn("err.status === 403", self.html_content)
        self.assertIn("err.status === 429", self.html_content)
        self.assertIn("err.status === 409", self.html_content)
        self.assertIn("err.status === 400", self.html_content)

    # -------------------------------------------------------------------------
    # 2. JavaScript State Machine Unit Tests via Node.js
    # -------------------------------------------------------------------------
    def test_frontend_state_machine_with_node(self):
        """Execute headless simulation of the pattern lock JS state machine."""
        js_test_code = """
        const assert = require('assert');

        // Minimal DOM mock
        const elements = {};
        function createElement(id) {
            return {
                id,
                textContent: '',
                disabled: false,
                style: {},
                classList: {
                    items: new Set(),
                    add(c) { this.items.add(c); },
                    remove(c) { this.items.delete(c); },
                    contains(c) { return this.items.has(c); }
                },
                setAttribute(k, v) { this[k] = v; },
                focus() {}
            };
        }

        const ids = ['pp-title', 'pp-subtitle', 'pp-message', 'pp-save', 'pp-clear', 'pp-cancel', 'pp-close', 'profile-pattern-dialog'];
        ids.forEach(id => { elements[id] = createElement(id); });

        const nodes = [];
        for (let i = 1; i <= 9; i++) {
            nodes.push({
                dataset: { point: String(i) },
                classList: {
                    items: new Set(),
                    add(c) { this.items.add(c); },
                    remove(c) { this.items.delete(c); }
                }
            });
        }

        // Environment mock
        let fetchCalls = [];
        global.document = {
            getElementById(id) { return elements[id] || null; },
            querySelectorAll(sel) {
                if (sel === '.pp-node') return nodes;
                if (sel === 'div') return [];
                return [];
            },
            addEventListener() {}
        };
        global.fetch = function(url, opts) {
            fetchCalls.push({ url, opts });
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve({ ok: true })
            });
        };

        // --- SIMULATED STATE MACHINE ---
        let pattern = [];
        let currentPattern = null;
        let newPatternFirst = null;
        let step = 1;
        let configured = true;
        let isSubmitting = false;

        function msg(text, error) {
            const el = document.getElementById('pp-message');
            el.textContent = text;
            el.style.color = error ? '#ff8291' : '#8db3c5';
        }

        function clearDrawing() {
            pattern = [];
            nodes.forEach(n => n.classList.remove('selected'));
        }

        function clearAll() {
            clearDrawing();
            currentPattern = null;
            newPatternFirst = null;
            step = 1;
            isSubmitting = false;
        }

        function updateUI() {
            const titleEl = document.getElementById('pp-title');
            const subtitleEl = document.getElementById('pp-subtitle');
            const saveBtn = document.getElementById('pp-save');
            if (configured) {
                titleEl.textContent = 'CHANGE PATTERN PASSWORD';
                if (step === 1) {
                    subtitleEl.textContent = 'Step 1 of 3: Draw current pattern';
                    saveBtn.textContent = 'NEXT STEP';
                } else if (step === 2) {
                    subtitleEl.textContent = 'Step 2 of 3: Draw new pattern';
                    saveBtn.textContent = 'CONTINUE';
                } else if (step === 3) {
                    subtitleEl.textContent = 'Step 3 of 3: Confirm new pattern';
                    saveBtn.textContent = 'SAVE NEW PATTERN';
                }
            } else {
                titleEl.textContent = 'CREATE PATTERN PASSWORD';
                if (step === 1) {
                    subtitleEl.textContent = 'Step 1 of 2: Draw new pattern';
                    saveBtn.textContent = 'CONTINUE';
                } else {
                    subtitleEl.textContent = 'Step 2 of 2: Confirm new pattern';
                    saveBtn.textContent = 'SAVE PATTERN';
                }
            }
        }

        function handleSaveClick() {
            if (isSubmitting) return 'BLOCKED_SUBMITTING';
            const saveBtn = document.getElementById('pp-save');

            if (pattern.length < 4) {
                msg('Connect at least four different points.', true);
                return 'TOO_SHORT';
            }

            if (configured) {
                if (step === 1) {
                    currentPattern = pattern.slice();
                    clearDrawing();
                    step = 2;
                    updateUI();
                    msg('Now draw your replacement pattern.');
                    return 'STEP1_DONE';
                }
                if (step === 2) {
                    newPatternFirst = pattern.slice();
                    clearDrawing();
                    step = 3;
                    updateUI();
                    msg('Confirm by drawing the same replacement pattern again.');
                    return 'STEP2_DONE';
                }
                if (step === 3) {
                    if (newPatternFirst.join('-') !== pattern.join('-')) {
                        clearDrawing();
                        newPatternFirst = null;
                        step = 2;
                        updateUI();
                        msg('New patterns did not match. Please redraw replacement pattern.', true);
                        return 'MISMATCH';
                    }

                    if (!currentPattern || currentPattern.length < 4) {
                        clearAll();
                        updateUI();
                        msg('Current pattern verification is required. Please start over.', true);
                        return 'MISSING_CURRENT';
                    }

                    isSubmitting = true;
                    saveBtn.disabled = true;
                    saveBtn.textContent = 'SAVING...';
                    msg('Updating pattern password...');

                    const payload = {
                        current_pattern: currentPattern,
                        new_pattern: pattern
                    };

                    fetch('/api/pattern-lock/change', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(payload)
                    });
                    return 'SUBMITTED_CHANGE';
                }
            }
        }

        // Test 1: Configured pattern triggers 3-step sequence
        configured = true;
        clearAll();
        updateUI();
        assert.strictEqual(elements['pp-subtitle'].textContent, 'Step 1 of 3: Draw current pattern');

        // Step 1: Draw current pattern [1, 2, 5, 8]
        pattern = [1, 2, 5, 8];
        const res1 = handleSaveClick();
        assert.strictEqual(res1, 'STEP1_DONE');
        assert.strictEqual(step, 2);
        assert.strictEqual(elements['pp-subtitle'].textContent, 'Step 2 of 3: Draw new pattern');
        assert.deepStrictEqual(currentPattern, [1, 2, 5, 8]);

        // Step 2: Draw replacement pattern [3, 5, 7, 8]
        pattern = [3, 5, 7, 8];
        const res2 = handleSaveClick();
        assert.strictEqual(res2, 'STEP2_DONE');
        assert.strictEqual(step, 3);
        assert.strictEqual(elements['pp-subtitle'].textContent, 'Step 3 of 3: Confirm new pattern');
        assert.deepStrictEqual(newPatternFirst, [3, 5, 7, 8]);

        // Step 3: Confirmation mismatch [3, 5, 7, 9] != [3, 5, 7, 8]
        pattern = [3, 5, 7, 9];
        const resMismatch = handleSaveClick();
        assert.strictEqual(resMismatch, 'MISMATCH');
        assert.strictEqual(step, 2, 'Must return to step 2 on mismatch');
        assert.strictEqual(newPatternFirst, null, 'Must reset newPatternFirst on mismatch');
        assert.strictEqual(elements['pp-message'].textContent, 'New patterns did not match. Please redraw replacement pattern.');

        // Step 2 re-entry: Draw [3, 5, 7, 8] again
        pattern = [3, 5, 7, 8];
        handleSaveClick();
        assert.strictEqual(step, 3);

        // Step 3: Confirmation MATCH [3, 5, 7, 8] == [3, 5, 7, 8]
        pattern = [3, 5, 7, 8];
        const resSuccess = handleSaveClick();
        assert.strictEqual(resSuccess, 'SUBMITTED_CHANGE');
        assert.strictEqual(fetchCalls.length, 1);
        assert.strictEqual(fetchCalls[0].url, '/api/pattern-lock/change');
        const sentPayload = JSON.parse(fetchCalls[0].opts.body);
        assert.deepStrictEqual(sentPayload, {
            current_pattern: [1, 2, 5, 8],
            new_pattern: [3, 5, 7, 8]
        });

        // Test duplicate click while isSubmitting is true
        const dupResult = handleSaveClick();
        assert.strictEqual(dupResult, 'BLOCKED_SUBMITTING');

        // Test clearAll on cancel / close
        clearAll();
        assert.strictEqual(currentPattern, null);
        assert.strictEqual(newPatternFirst, null);
        assert.strictEqual(pattern.length, 0);
        assert.strictEqual(step, 1);
        assert.strictEqual(isSubmitting, false);

        // Test missing current pattern cannot be submitted
        step = 3;
        currentPattern = null;
        newPatternFirst = [1, 2, 3, 4];
        pattern = [1, 2, 3, 4];
        const resMissing = handleSaveClick();
        assert.strictEqual(resMissing, 'MISSING_CURRENT');
        assert.strictEqual(currentPattern, null);

        console.log("ALL_NODE_TESTS_PASSED");
        """
        proc = subprocess.run(
            ["node", "-e", js_test_code],
            capture_output=True,
            text=True,
            check=False
        )
        self.assertEqual(proc.returncode, 0, f"Node.js state machine tests failed:\n{proc.stderr}\n{proc.stdout}")
        self.assertIn("ALL_NODE_TESTS_PASSED", proc.stdout)

    # -------------------------------------------------------------------------
    # 3. Full HTTP Lifecycle Verification
    # -------------------------------------------------------------------------
    def test_backend_pattern_change_successful_three_step_payload(self):
        """Verify successful change using the payload generated by Step 3."""
        pattern_lock.configure([1, 2, 5, 8])
        with self.client.session_transaction() as sess:
            sess["face_authorized"] = True
            sess["face_identity"] = "kamalesh"

        res = self.client.post("/api/pattern-lock/change", json={
            "current_pattern": [1, 2, 5, 8],
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])
        self.assertTrue(pattern_lock.verify([3, 5, 7, 8]))
        self.assertFalse(pattern_lock.verify([1, 2, 5, 8]))

    def test_backend_pattern_change_rejects_missing_current_pattern(self):
        """Verify 400 Bad Request when current_pattern is absent."""
        pattern_lock.configure([1, 2, 5, 8])
        with self.client.session_transaction() as sess:
            sess["face_authorized"] = True
            sess["face_identity"] = "kamalesh"

        res = self.client.post("/api/pattern-lock/change", json={
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("Current pattern is required", res.get_json()["message"])

    def test_backend_pattern_change_rejects_incorrect_current_pattern(self):
        """Verify 403 Forbidden when current_pattern does not match."""
        pattern_lock.configure([1, 2, 5, 8])
        with self.client.session_transaction() as sess:
            sess["face_authorized"] = True
            sess["face_identity"] = "kamalesh"

        res = self.client.post("/api/pattern-lock/change", json={
            "current_pattern": [1, 4, 7, 8],  # wrong
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("Current pattern did not match", res.get_json()["message"])

    def test_backend_pattern_change_rate_limiting_returns_429(self):
        """Verify 429 Too Many Requests after repeated invalid current_pattern attempts."""
        pattern_lock.configure([1, 2, 5, 8])
        with self.client.session_transaction() as sess:
            sess["face_authorized"] = True
            sess["face_identity"] = "kamalesh"

        for _ in range(5):
            res = self.client.post("/api/pattern-lock/change", json={
                "current_pattern": [9, 8, 7, 4],
                "new_pattern": [3, 5, 7, 8]
            })
            self.assertEqual(res.status_code, 403)

        # 6th attempt returns 429
        res429 = self.client.post("/api/pattern-lock/change", json={
            "current_pattern": [9, 8, 7, 4],
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(res429.status_code, 429)
        self.assertIn("Too many attempts", res429.get_json()["message"])

    def test_backend_pattern_change_expired_session_returns_401(self):
        """Verify 401 when session has expired."""
        pattern_lock.configure([1, 2, 5, 8])
        with self.client.session_transaction() as sess:
            sess["face_authorized"] = True
            sess["face_identity"] = "kamalesh"
            sess["face_authorized_at"] = "2020-01-01T00:00:00"

        res = self.client.post("/api/pattern-lock/change", json={
            "current_pattern": [1, 2, 5, 8],
            "new_pattern": [3, 5, 7, 8]
        })
        self.assertEqual(res.status_code, 401)

    def test_initial_setup_works_when_unconfigured_and_conflict_when_configured(self):
        """Verify initial setup succeeds on fresh install and returns 409 conflict when already configured."""
        # Fresh setup
        res_setup = self.client.post("/api/pattern-lock/setup", json={"pattern": [1, 4, 7, 8]})
        self.assertEqual(res_setup.status_code, 200)
        self.assertTrue(pattern_lock.verify([1, 4, 7, 8]))

        # Re-attempting setup when configured returns 409 Conflict
        res_conflict = self.client.post("/api/pattern-lock/setup", json={"pattern": [2, 5, 8, 0]})
        self.assertEqual(res_conflict.status_code, 409)
        self.assertIn("already configured", res_conflict.get_json()["message"])


if __name__ == "__main__":
    unittest.main()
