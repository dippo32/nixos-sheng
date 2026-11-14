#!/usr/bin/env python3
"""Exercise charger-mode fail-open behaviour without accessing hardware."""
import contextlib
import importlib.machinery
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

# Linux supplies fcntl; a stub permits the hardware-free tests on Windows.
try:
    import fcntl  # noqa: F401
except ModuleNotFoundError:
    sys.modules["fcntl"] = types.ModuleType("fcntl")

SOURCE = Path(sys.argv[1]).resolve()


def load_helper():
    loader = importlib.machinery.SourceFileLoader("charger_under_test", str(SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.now > 40:
            raise AssertionError("charger loop failed to terminate in test")


class ChargerSafety(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.clock = Clock()
        self.mock("time", new=self.clock)
        self.mock("in_charger_boot", return_value=True)
        self.mock("unblank_display")
        self.mock("find_backlight", return_value=None)
        self.mock("backlight_restore_value", return_value=1)
        self.mock("draw_screen", return_value=False)
        self.mock("run_mipps_auth")
        self.mock("typec_attached", return_value=False)
        self.mock("external_power_present", return_value=False)
        self.mock("battery_info_ready", return_value=False)
        self.mock("open_power_key_events", return_value={})
        self.mock("read_power_key_events", return_value=[])

    def mock(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.helper, name, **kwargs))

    def test_missing_source_with_delayed_battery_continues_boot(self):
        poweroff = self.mock("request_poweroff")
        self.assertEqual(self.helper.main(), 0)
        self.assertGreaterEqual(self.clock.now, self.helper.INITIAL_SOURCE_FALLBACK_SECS)
        poweroff.assert_not_called()

    def test_missing_source_after_battery_ready_continues_boot(self):
        self.helper.battery_info_ready.return_value = True
        poweroff = self.mock("request_poweroff")
        self.assertEqual(self.helper.main(), 0)
        self.assertGreaterEqual(self.clock.now, self.helper.INITIAL_SOURCE_WAIT_SECS)
        poweroff.assert_not_called()

    def test_late_power_key_is_rescanned_and_long_press_continues_boot(self):
        self.helper.external_power_present.return_value = True
        self.helper.open_power_key_events.side_effect = [{}, {42: "power"}]
        event_sent = False

        def events(fds):
            nonlocal event_sent
            if fds and not event_sent:
                event_sent = True
                return [1]
            return []

        self.helper.read_power_key_events.side_effect = events
        poweroff = self.mock("request_poweroff")
        self.assertEqual(self.helper.main(), 0)
        self.assertGreaterEqual(self.helper.open_power_key_events.call_count, 2)
        self.assertGreaterEqual(self.clock.now, 1 + self.helper.POWER_HOLD_SECS)
        poweroff.assert_not_called()

    def test_missing_power_key_with_charger_present_continues_boot(self):
        self.helper.external_power_present.return_value = True
        poweroff = self.mock("request_poweroff")
        self.assertEqual(self.helper.main(), 0)
        self.assertGreaterEqual(self.clock.now, self.helper.KEY_DISCOVERY_TIMEOUT_SECS)
        self.assertGreater(self.helper.open_power_key_events.call_count, 2)
        poweroff.assert_not_called()

    def test_short_press_then_long_press_restores_backlight_before_boot(self):
        self.helper.external_power_present.return_value = True
        self.helper.open_power_key_events.return_value = {42: "power"}
        self.helper.find_backlight.return_value = "/test-backlight"
        self.helper.backlight_restore_value.return_value = 80
        brightness = {"value": 80}
        self.mock("backlight_brightness", side_effect=lambda _: brightness["value"])

        def set_brightness(_, value):
            brightness["value"] = value
            return True

        set_backlight = self.mock("set_backlight", side_effect=set_brightness)
        events = [(0, [1]), (0.2, [0]), (1, [1])]

        def next_events(_):
            return events.pop(0)[1] if events and self.clock.now >= events[0][0] else []

        self.helper.read_power_key_events.side_effect = next_events
        self.assertEqual(self.helper.main(), 0)
        self.assertEqual(brightness["value"], 80)
        self.assertEqual([call.args[1] for call in set_backlight.call_args_list], [0, 80])

    def test_confirmed_unplug_requests_poweroff(self):
        self.helper.external_power_present.side_effect = lambda: self.clock.now < 1
        self.helper.typec_attached.side_effect = lambda: self.clock.now < 1
        poweroff = self.mock("request_poweroff", return_value=True)
        self.assertEqual(self.helper.main(), 0)
        poweroff.assert_called_once_with("external power removed, powering off")

    def test_poweroff_is_queued_via_systemd_and_failure_is_nonfatal(self):
        run = self.stack.enter_context(patch.object(self.helper.subprocess, "run"))
        self.assertTrue(self.helper.request_poweroff("test unplug"))
        self.assertEqual(run.call_args.args[0], ["/usr/bin/systemctl", "--no-block", "poweroff"])
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual(run.call_args.kwargs["timeout"], 10)
        run.side_effect = subprocess.TimeoutExpired("systemctl", 10)
        self.assertFalse(self.helper.request_poweroff("test failure"))

    def test_cmdline_or_device_tree_marker_selects_charger(self):
        self.stack.close()  # Remove the main-loop mock of in_charger_boot.
        with patch.object(self.helper, "read_text", return_value="androidboot.mode=charger"), \
             patch.object(self.helper.os.path, "exists", return_value=False):
            self.assertTrue(self.helper.in_charger_boot())
        with patch.object(self.helper, "read_text", return_value=""), \
             patch.object(self.helper.os.path, "exists", return_value=True) as exists:
            self.assertTrue(self.helper.in_charger_boot())
            exists.assert_called_once_with("/proc/device-tree/chosen/sheng,charger-mode")
        with patch.object(self.helper, "read_text", return_value=""), \
             patch.object(self.helper.os.path, "exists", return_value=False):
            self.assertFalse(self.helper.in_charger_boot())


    def make_screen_harness(self, events):
        """Simulate power, a discovered key, and an actual mutable backlight."""
        self.helper.battery_info_ready.return_value = True
        self.helper.external_power_present.return_value = True
        self.helper.typec_attached.return_value = True
        self.helper.open_power_key_events.return_value = {42: "power"}
        self.helper.find_backlight.return_value = "/test-backlight"
        self.helper.backlight_restore_value.return_value = 80
        self.helper.draw_screen.return_value = True
        brightness = {"value": 80}
        changes = []
        self.mock("backlight_brightness", side_effect=lambda _: brightness["value"])

        def set_brightness(_, value):
            brightness["value"] = value
            changes.append((self.clock.now, value))
            return True

        self.mock("set_backlight", side_effect=set_brightness)
        poweroff = self.mock("request_poweroff", return_value=True)
        pending = list(events)

        def next_events(_):
            return pending.pop(0)[1] if pending and self.clock.now >= pending[0][0] else []

        self.helper.read_power_key_events.side_effect = next_events
        return brightness, changes, poweroff

    def test_screen_blanks_after_ten_seconds_and_long_hold_restores_for_boot(self):
        brightness, changes, poweroff = self.make_screen_harness([(11.0, [1])])
        self.assertEqual(self.helper.main(), 0)
        self.assertEqual([value for _, value in changes], [0, 80])
        self.assertGreaterEqual(changes[0][0], 9.9)
        self.assertLessEqual(changes[0][0], 10.2)
        self.assertEqual(brightness["value"], 80)
        poweroff.assert_not_called()

    def test_short_press_wakes_and_screen_blanks_again_after_ten_seconds(self):
        events = [(10.5, [1]), (10.7, [0]), (21.5, [1])]
        brightness, changes, poweroff = self.make_screen_harness(events)
        self.assertEqual(self.helper.main(), 0)
        self.assertEqual([value for _, value in changes], [0, 80, 0, 80])
        self.assertGreaterEqual(changes[2][0] - changes[1][0], 9.9)
        self.assertLessEqual(changes[2][0] - changes[1][0], 10.2)
        self.assertEqual(brightness["value"], 80)
        poweroff.assert_not_called()

    def test_timeout_starts_when_delayed_battery_display_becomes_ready(self):
        brightness, changes, poweroff = self.make_screen_harness([(15.0, [1])])
        self.helper.battery_info_ready.side_effect = lambda: self.clock.now >= 4.0
        self.assertEqual(self.helper.main(), 0)
        self.assertEqual([value for _, value in changes], [0, 80])
        self.assertGreaterEqual(changes[0][0], 13.9)
        self.assertLessEqual(changes[0][0], 14.2)
        self.assertEqual(brightness["value"], 80)
        poweroff.assert_not_called()

    def test_short_press_can_blank_early_and_long_press_restores_for_boot(self):
        brightness, changes, poweroff = self.make_screen_harness([(0.5, [1]), (0.7, [0]), (1.0, [1])])
        self.assertEqual(self.helper.main(), 0)
        self.assertEqual([value for _, value in changes], [0, 80])
        self.assertLess(changes[0][0], 1.0)
        self.assertEqual(brightness["value"], 80)
        poweroff.assert_not_called()

    def test_unplug_after_auto_blank_still_requests_poweroff(self):
        brightness, changes, poweroff = self.make_screen_harness([])
        self.helper.external_power_present.side_effect = lambda: self.clock.now < 11.0
        self.helper.typec_attached.side_effect = lambda: self.clock.now < 11.0
        self.assertEqual(self.helper.main(), 0)
        self.assertEqual([value for _, value in changes], [0])
        self.assertEqual(brightness["value"], 0)
        self.assertGreaterEqual(self.clock.now, 11.0 + self.helper.UNPLUG_CONFIRM_SECS)
        poweroff.assert_called_once_with("external power removed, powering off")

    def test_held_power_key_at_timeout_never_blanks_before_normal_boot(self):
        brightness, changes, poweroff = self.make_screen_harness([(9.0, [1])])
        self.assertEqual(self.helper.main(), 0)
        self.assertEqual(changes, [])
        self.assertEqual(brightness["value"], 80)
        poweroff.assert_not_called()

    def test_timeout_starts_when_battery_display_is_ready(self):
        brightness, changes, poweroff = self.make_screen_harness([(15.0, [1])])
        self.helper.battery_info_ready.side_effect = lambda: self.clock.now >= 4.0
        self.assertEqual(self.helper.main(), 0)
        self.assertEqual([value for _, value in changes], [0, 80])
        self.assertGreaterEqual(changes[0][0], 13.9)
        self.assertLessEqual(changes[0][0], 14.2)
        poweroff.assert_not_called()

    def test_mipps_timeout_or_spawn_error_does_not_stop_charger_mode(self):
        helper = load_helper()
        with patch.object(helper.os.path, "exists", return_value=True), \
             patch.object(helper.subprocess, "run") as run:
            for failure in (subprocess.TimeoutExpired("flock", 20), OSError("failed")):
                run.side_effect = failure
                self.assertFalse(helper.run_mipps_auth())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
