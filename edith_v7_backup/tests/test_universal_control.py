import unittest
from unittest.mock import patch

from plugins import universal_control as control


class UniversalControlTests(unittest.TestCase):
    @patch("plugins.universal_control.webbrowser.open", return_value=True)
    def test_named_site_opens_official_url(self, browser_open):
        result = control.open_website("youtube")
        browser_open.assert_called_once_with("https://www.youtube.com", new=2)
        self.assertTrue(result.startswith("SUCCESS:"))

    @patch("plugins.universal_control.webbrowser.open", return_value=True)
    def test_search_query_is_encoded(self, browser_open):
        result = control.search_website("github", "edith voice agent")
        called_url = browser_open.call_args.args[0]
        self.assertIn("edith+voice+agent", called_url)
        self.assertTrue(result.startswith("SUCCESS:"))

    def test_unsafe_scheme_is_rejected(self):
        self.assertTrue(control.open_website("file:///C:/secret").startswith("ERROR:"))

    def test_high_impact_action_requires_confirmation(self):
        result = control.control("type_text", text="send payment now")
        self.assertIn("CONFIRMATION_REQUIRED", result)

    @patch("plugins.universal_control._execute", return_value="SUCCESS: test")
    def test_confirmation_is_single_use(self, execute):
        request = control.control("close_app", target="notepad")
        token = request.split("[")[1].split("]")[0]
        self.assertEqual(control.confirm(token), "SUCCESS: test")
        self.assertTrue(control.confirm(token).startswith("ERROR:"))
        execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
