#!/usr/bin/env python3
"""Run the actual pruning logic against disposable links and a fake nix-env."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sheng-prune-generations"


class RetentionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profile = self.root / "profiles/system"
        self.profile.parent.mkdir()
        self.booted = self.root / "booted-system"
        self.current = self.root / "current-system"
        self.log = self.root / "calls"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        stub = self.bin / "nix-env"
        stub.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            '[[ "$1" == --profile && "$3" == --delete-generations && $# == 4 ]]\n'
            'printf "%s\\n" "$4" >> "$TEST_LOG"\n'
            'rm -- "$2-$4-link"\n'
            'if [[ -n ${TEST_ACTION:-} ]]; then "$TEST_ACTION"; fi\n'
        )
        stub.chmod(0o755)
        text = SCRIPT.read_text()
        replacements = {
            "booted=/run/booted-system": f"booted={shlex.quote(str(self.booted))}",
            "current=/run/current-system": f"current={shlex.quote(str(self.current))}",
            "profile=/nix/var/nix/profiles/system": f"profile={shlex.quote(str(self.profile))}",
        }
        for before, after in replacements.items():
            self.assertEqual(text.count(before), 1)
            text = text.replace(before, after)
        self.script = self.root / "prune"
        self.script.write_text(text)
        self.target(1)
        self.target(2)
        self.target(3)
        self.select(3)

    def target(self, number, target=None):
        target = target or self.root / f"store-{number}"
        target.mkdir(exist_ok=True)
        self.profile.with_name(f"system-{number}-link").symlink_to(target)
        return target

    def change_link(self, link, target):
        link.unlink(missing_ok=True)
        link.symlink_to(target)

    def select(self, number):
        gen = self.profile.with_name(f"system-{number}-link")
        self.change_link(self.profile, gen.name)
        self.change_link(self.booted, gen.resolve())
        self.change_link(self.current, gen.resolve())

    def run_prune(self, action=None):
        env = os.environ | {"PATH": f"{self.bin}:{os.environ['PATH']}", "TEST_LOG": str(self.log)}
        if action:
            env["TEST_ACTION"] = str(action)
        subprocess.run(["bash", str(self.script)], env=env, check=True)
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_only_snapshot_older_distinct_targets_removed(self):
        self.target(0, self.booted.resolve())
        self.target(4)  # Later generation must survive even when not selected.
        self.assertEqual(self.run_prune(), ["1", "2"])
        for number in (0, 3, 4):
            self.assertTrue(self.profile.with_name(f"system-{number}-link").is_symlink())

    def test_pending_profile_does_not_prune(self):
        self.target(4)
        self.change_link(self.profile, "system-4-link")
        self.assertEqual(self.run_prune(), [])

    def test_test_activation_does_not_prune(self):
        self.change_link(self.current, self.root / "store-2")
        self.assertEqual(self.run_prune(), [])

    def test_missing_boot_state_does_not_prune(self):
        self.booted.unlink()
        self.assertEqual(self.run_prune(), [])

    def test_changed_current_after_first_deletion_stops(self):
        action = self.root / "change-current"
        action.write_text(f"#!/bin/sh\nln -sfn {shlex.quote(str(self.root / 'store-2'))} {shlex.quote(str(self.current))}\n")
        action.chmod(0o755)
        self.assertEqual(self.run_prune(action), ["1"])
        self.assertTrue(self.profile.with_name("system-2-link").is_symlink())

    def test_profile_changes_after_first_deletion_stop(self):
        self.target(4)
        action = self.root / "change-profile"
        action.write_text(f"#!/bin/sh\nln -sfn system-4-link {shlex.quote(str(self.profile))}\n")
        action.chmod(0o755)
        self.assertEqual(self.run_prune(action), ["1"])
        self.assertTrue(self.profile.with_name("system-2-link").is_symlink())
        self.assertTrue(self.profile.with_name("system-4-link").is_symlink())

    def test_snapshot_target_changed_before_deletion_stops(self):
        action = self.root / "change-snapshot"
        action.write_text(
            f"#!/bin/sh\nln -sfn {shlex.quote(str(self.root / 'store-3'))} "
            f"{shlex.quote(str(self.profile.with_name('system-2-link')))}\n"
        )
        action.chmod(0o755)
        self.assertEqual(self.run_prune(action), ["1"])
        self.assertTrue(self.profile.with_name("system-2-link").is_symlink())

    def test_new_generation_after_snapshot_is_not_deleted(self):
        action = self.root / "new-generation"
        action.write_text(
            f"#!/bin/sh\nmkdir -p {shlex.quote(str(self.root / 'store-4'))}\n"
            f"ln -sfn {shlex.quote(str(self.root / 'store-4'))} {shlex.quote(str(self.profile.with_name('system-4-link')))}\n"
        )
        action.chmod(0o755)
        self.assertEqual(self.run_prune(action), ["1", "2"])
        self.assertTrue(self.profile.with_name("system-4-link").is_symlink())


if __name__ == "__main__":
    unittest.main()
