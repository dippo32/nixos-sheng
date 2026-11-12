#!/usr/bin/env python3
"""Exercise auth re-entry without accessing firmware, sysfs or systemd."""
import ast
import contextlib
import hashlib
import hmac
import importlib.machinery
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


SOURCE = Path(sys.argv[1]).resolve()


def load_helper():
    loader = importlib.machinery.SourceFileLoader("mipps_under_test", str(SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class AuthenticationReentry(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.state = {}
        self.stack.enter_context(patch.object(self.helper, "write_state_file", side_effect=self.state.__setitem__))
        self.stack.enter_context(patch.object(self.helper, "read_state_file", side_effect=self.state.get))

    def mock(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.helper, name, **kwargs))

    def arguments(self, *arguments):
        self.stack.enter_context(patch.object(sys, "argv", ["xiaomi-mipps-auth", *arguments]))

    def authentication_path(self, pdo_unsupported, vdm_state=6):
        self.arguments("--sysfs", "/nonexistent-test-sysfs")
        self.mock("wait_usb_online", return_value=True)
        pdo = self.mock("should_skip_pdo2", return_value=pdo_unsupported)
        vdm = self.mock("vdm_state", return_value=(vdm_state, ""))
        fuel_gauge = self.mock("enable_battery_auth")
        role_swap = self.mock("ensure_typec_host")
        notify = self.mock("notify_completed_charge")
        self.mock("print_status")
        self.mock("wait_real_type", return_value="USB")
        return pdo, vdm, fuel_gauge, role_swap, notify

    def test_unsupported_source_skips_stale_completed_auth(self):
        pdo, _, fuel_gauge, role_swap, notify = self.authentication_path(True)
        with self.assertRaises(self.helper.UnsupportedChargerError) as raised:
            self.helper.main()
        self.assertTrue(raised.exception.terminal)
        pdo.assert_called_once()
        fuel_gauge.assert_not_called()
        role_swap.assert_not_called()
        notify.assert_called_once()

    def test_unsupported_source_is_checked_before_vdm_read(self):
        _, vdm, fuel_gauge, role_swap, _ = self.authentication_path(True)
        vdm.side_effect = ValueError("stale/unavailable VDM state")
        with self.assertRaises(self.helper.UnsupportedChargerError):
            self.helper.main()
        vdm.assert_not_called()
        fuel_gauge.assert_not_called()
        role_swap.assert_not_called()

    def test_valid_completed_auth_retains_fuel_gauge_path(self):
        pdo, vdm, fuel_gauge, role_swap, notify = self.authentication_path(False)
        self.helper.main()
        pdo.assert_called_once()
        vdm.assert_called_once()
        fuel_gauge.assert_called_once()
        role_swap.assert_not_called()
        notify.assert_called_once()

    def test_unsupported_fresh_auth_still_skips_role_swap(self):
        _, _, fuel_gauge, role_swap, _ = self.authentication_path(True, vdm_state=0)
        with self.assertRaises(self.helper.UnsupportedChargerError):
            self.helper.main()
        fuel_gauge.assert_not_called()
        role_swap.assert_not_called()

    def test_fresh_source_waits_for_type_before_checking_pdo(self):
        pdo, _, fuel_gauge, role_swap, _ = self.authentication_path(True, vdm_state=0)
        source = {"type_ready": False, "unsupported_pdo": True}

        def settle_type(root, timeout):
            source["type_ready"] = True
            source["unsupported_pdo"] = False
            return "PD"

        def current_pdo(root):
            self.assertTrue(source["type_ready"], "PDO checked before type wait completed")
            return source["unsupported_pdo"]

        class ReachedRoleSwap(Exception):
            pass

        self.helper.wait_real_type.side_effect = settle_type
        pdo.side_effect = current_pdo
        role_swap.side_effect = ReachedRoleSwap
        with self.assertRaises(ReachedRoleSwap):
            self.helper.main()
        self.helper.wait_real_type.assert_called_once()
        pdo.assert_called_once()
        fuel_gauge.assert_not_called()

    def test_terminal_unsupported_keeps_cli_success_exit(self):
        # Execute the source's real CLI exception handler without hardware calls.
        entry = ast.Module(body=[ast.parse(SOURCE.read_text()).body[-1]], type_ignores=[])
        namespace = dict(vars(self.helper))
        namespace["__name__"] = "__main__"

        def unsupported():
            raise self.helper.UnsupportedChargerError("no authentication PDO", terminal=True)

        namespace["main"] = unsupported
        with self.assertRaises(SystemExit) as raised:
            exec(compile(entry, str(SOURCE), "exec"), namespace)
        self.assertEqual(raised.exception.code, 0)

    def test_valid_fresh_auth_retains_protocol(self):
        _, _, fuel_gauge, role_swap, notify = self.authentication_path(False, vdm_state=0)
        self.mock("current_adapter_svid", return_value=self.helper.XIAOMI_SVID)
        self.stack.enter_context(patch.object(self.helper.random, "randrange", return_value=0))
        challenge = "ab" * 16
        adapter = "deadbeef"
        self.stack.enter_context(patch.object(self.helper.secrets, "token_hex", return_value=challenge))
        self.mock("detect_adapter_id", return_value=adapter)
        digest = hmac.new(
            bytes.fromhex(self.helper.KEYS[0]),
            bytes.fromhex(challenge + adapter),
            hashlib.sha256,
        ).hexdigest()
        commands = self.mock(
            "send_vdm",
            side_effect=lambda root, command, *args, **kwargs: (
                command, digest[:32] if command == 5 else ""
            ),
        )
        self.stack.enter_context(patch.object(self.helper.os.path, "exists", return_value=False))
        self.helper.main()
        self.assertEqual([call.args[1] for call in commands.call_args_list], [1, 2, 3, 4, 5, 6, 8, 7])
        fuel_gauge.assert_called_once()
        role_swap.assert_called_once()
        notify.assert_called_once_with(
            "/nonexistent-test-sysfs", self.helper.NOTIFICATION_STATE_FILE, True
        )

    def test_failed_systemd_enqueue_does_not_latch_online(self):
        self.arguments("--usb-online-trigger")
        start = self.mock("start_systemd_unit")
        for failure in (
            FileNotFoundError("systemctl unavailable"),
            subprocess.CalledProcessError(1, ["systemctl"]),
            subprocess.TimeoutExpired(["systemctl"], 2),
        ):
            with self.subTest(failure=type(failure).__name__):
                self.state.clear()
                start.reset_mock()
                start.side_effect = failure
                with self.assertRaises(type(failure)):
                    self.helper.main()
                self.assertEqual(self.state[self.helper.USB_ONLINE_STATE_FILE], "0")
                start.side_effect = None
                self.helper.main()
                self.assertEqual(start.call_count, 2)
                self.assertEqual(self.state[self.helper.USB_ONLINE_STATE_FILE], "1")

    def test_already_online_does_not_enqueue_duplicate(self):
        self.arguments("--usb-online-trigger")
        self.state[self.helper.USB_ONLINE_STATE_FILE] = "1"
        start = self.mock("start_systemd_unit")
        self.helper.main()
        start.assert_not_called()


unittest.main(argv=[sys.argv[0]])
