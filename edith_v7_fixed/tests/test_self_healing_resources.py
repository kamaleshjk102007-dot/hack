import time
import unittest
from unittest.mock import MagicMock, patch

from brain import self_healing


class SelfHealingResourceDebounceTests(unittest.TestCase):

    def setUp(self):
        self_healing._last_resource_alerts["ram_warn_time"] = 0.0
        self_healing._last_resource_alerts["ram_crit_time"] = 0.0
        self_healing._last_resource_alerts["disk_warn_time"] = 0.0
        self_healing._last_resource_alerts["disk_crit_time"] = 0.0
        self_healing._last_resource_alerts["down_providers"] = set()

    def test_high_ram_alert_is_debounced(self):
        """Verify that high RAM does not spam alerts on every consecutive sweep."""
        mock_alert = MagicMock()
        mock_vm = MagicMock()
        mock_vm.percent = 93.0  # Above 92% threshold

        with patch.object(self_healing, "_alert", mock_alert), \
             patch("psutil.virtual_memory", return_value=mock_vm), \
             patch("psutil.disk_usage", return_value=MagicMock(percent=50)):

            # First sweep should emit warning
            self_healing._check_system_resources()
            self.assertEqual(mock_alert.call_count, 1)
            self.assertIn("High RAM usage: 93%", mock_alert.call_args[0][0])

            # Immediate second sweep should NOT emit warning (throttled)
            self_healing._check_system_resources()
            self.assertEqual(mock_alert.call_count, 1)

            # Advance time beyond cooldown (e.g. 901s)
            self_healing._last_resource_alerts["ram_warn_time"] = time.time() - 905
            self_healing._check_system_resources()
            self.assertEqual(mock_alert.call_count, 2)

    def test_ram_alert_resets_when_usage_drops(self):
        """Verify cooldown resets once RAM drops below warning threshold."""
        mock_alert = MagicMock()
        mock_vm = MagicMock()

        with patch.object(self_healing, "_alert", mock_alert), \
             patch("psutil.virtual_memory", return_value=mock_vm), \
             patch("psutil.disk_usage", return_value=MagicMock(percent=50)):

            # High RAM
            mock_vm.percent = 93.0
            self_healing._check_system_resources()
            self.assertEqual(mock_alert.call_count, 1)

            # Drops to normal (80%)
            mock_vm.percent = 80.0
            self_healing._check_system_resources()
            self.assertEqual(mock_alert.call_count, 1)
            self.assertEqual(self_healing._last_resource_alerts["ram_warn_time"], 0.0)

            # Spikes back up — should alert again immediately without waiting 15 min
            mock_vm.percent = 94.0
            self_healing._check_system_resources()
            self.assertEqual(mock_alert.call_count, 2)

    def test_cloud_chain_alert_only_on_change(self):
        """Verify cooldown alert only fires when the set of cooling-down providers changes."""
        mock_alert = MagicMock()
        with patch.object(self_healing, "_alert", mock_alert):
            with patch("brain.cloud_router.get_chain_status", return_value={"groq": True, "gemini": False}):
                self_healing._check_cloud_chain()
                self.assertEqual(mock_alert.call_count, 1)

                # Same down providers on next sweep should not alert
                self_healing._check_cloud_chain()
                self.assertEqual(mock_alert.call_count, 1)

            # New provider added to cooldown -> alerts once
            with patch("brain.cloud_router.get_chain_status", return_value={"groq": True, "gemini": True}):
                self_healing._check_cloud_chain()
                self.assertEqual(mock_alert.call_count, 2)


if __name__ == "__main__":
    unittest.main()
