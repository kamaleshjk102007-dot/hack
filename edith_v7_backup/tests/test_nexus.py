import time
import unittest
from unittest.mock import patch

from nexus.planner import create_plan
from nexus.runtime import NexusRuntime


class NexusPlannerTests(unittest.TestCase):
    def test_blender_request_selects_blender(self):
        plan = create_plan("Create a realistic human face in Blender")
        self.assertEqual(plan["application"], "Blender")
        self.assertIn("Verify output", [step["title"] for step in plan["steps"]])

    def test_sensitive_request_requires_approval(self):
        self.assertTrue(create_plan("Delete these files")["requiresApproval"])

    def test_demo_is_always_labelled_simulated(self):
        runtime = NexusRuntime()
        task = runtime.create_task("Create a human face in Blender", demo=True)
        deadline = time.time() + 8
        while runtime.tasks[task["id"]]["status"] not in {"completed", "failed"} and time.time() < deadline:
            time.sleep(.05)
        finished = runtime.tasks[task["id"]]
        self.assertEqual(finished["status"], "completed")
        self.assertTrue(finished["simulated"])
        self.assertIn("No external application was controlled", finished["result"]["summary"])

    def test_live_unconfigured_connector_fails_honestly(self):
        runtime = NexusRuntime()
        task = runtime.create_task("Open VS Code and edit a project", demo=False)
        deadline = time.time() + 4
        while runtime.tasks[task["id"]]["status"] not in {"completed", "failed"} and time.time() < deadline:
            time.sleep(.05)
        self.assertEqual(runtime.tasks[task["id"]]["status"], "failed")
        self.assertIn("Connector not configured", runtime.tasks[task["id"]]["result"]["summary"])

    @patch("plugins.universal_control.search_website", return_value="SUCCESS: Searching google for 'AI news'")
    def test_live_browser_dispatch_uses_real_connector(self, search):
        runtime = NexusRuntime()
        result = runtime._execute_live_request("browser", runtime.connectors["browser"], "search AI news")
        self.assertTrue(result.ok)
        search.assert_called_once_with("google", "AI news")

    @patch("plugins.universal_control.control", return_value="✅ Opening notepad...")
    def test_live_desktop_dispatch_uses_computer_connector(self, control):
        runtime = NexusRuntime()
        result = runtime._execute_live_request("computer", runtime.connectors["computer"], "open notepad")
        self.assertTrue(result.ok)
        control.assert_called_once_with("open_app", target="notepad", text="", keys=None)


if __name__ == "__main__":
    unittest.main()
