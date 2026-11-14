#!/usr/bin/env python3
"""Exercise the extlinux installer's real shell body in a disposable root."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExtlinuxGenerations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profiles = self.root / "profiles"
        self.profiles.mkdir()
        self.boot = self.root / "boot"
        for generation in (1, 2, 3):
            system = self.root / f"store-system-{generation}"
            (system / "dtbs/qcom").mkdir(parents=True)
            (system / "dtbs/qcom/sm8550-xiaomi-sheng.dtb").write_text("dtb")
            (system / "kernel").write_text(f"kernel-{generation}")
            (system / "nixos-version").write_text(f"test-{generation}")
            (system / "kernel-params").write_text("console=tty0")
            (self.profiles / f"system-{generation}-link").symlink_to(system)
        (self.profiles / "system").symlink_to("system-3-link")

    def install(self, limit):
        content = (ROOT / "modules/extlinux.nix").read_text()
        body = content.split("    text = ''\n", 1)[1].split("\n    '';", 1)[0]
        self.assertEqual(body.count("${toString cfg.configurationLimit}"), 1)
        body = body.replace("${toString cfg.configurationLimit}", str(limit))
        body = body.replace("${cfg.dtbName}", "qcom/sm8550-xiaomi-sheng.dtb")
        body = body.replace("''${", "${")
        body = body.replace("/nix/var/nix/profiles/system", str(self.profiles / "system"))
        script = self.root / "install-boot"
        script.write_text("set -euo pipefail\n" + body)
        subprocess.run(["bash", str(script), "-d", str(self.boot), str(self.profiles / "system")], check=True)
        return ((self.boot / "extlinux/extlinux.conf").read_text(), (self.boot / "sheng-bootmenu.env").read_text())

    def test_ten_stages_current_and_previous_generation_entries(self):
        conf, menu = self.install(10)
        for name in ("nixos-default", "nixos-diagnostic", "nixos-1", "nixos-2", "nixos-3"):
            self.assertIn(f"LABEL {name}\n", conf)
        self.assertIn("NixOS generation 3", menu)
        self.assertIn("NixOS generation 2", menu)
        self.assertIn("NixOS generation 1", menu)
        for generation in (1, 2, 3):
            self.assertTrue((self.profiles / f"system-{generation}-link").is_symlink())
            self.assertIn(f"{self.root}/store-system-{generation}/init", conf)

    def test_zero_stages_only_default_and_diagnostic(self):
        conf, menu = self.install(0)
        self.assertIn("LABEL nixos-default\n", conf)
        self.assertIn("LABEL nixos-diagnostic\n", conf)
        self.assertNotIn("LABEL nixos-1\n", conf)
        self.assertNotIn("NixOS generation 1", menu)
        self.assertTrue((self.profiles / "system-1-link").is_symlink())

    def test_limit_two_stages_two_newest(self):
        conf, menu = self.install(2)
        self.assertIn("LABEL nixos-3\n", conf)
        self.assertIn("LABEL nixos-2\n", conf)
        self.assertNotIn("LABEL nixos-1\n", conf)
        self.assertIn("NixOS generation 2", menu)
        self.assertTrue((self.profiles / "system-1-link").is_symlink())


if __name__ == "__main__":
    unittest.main()
