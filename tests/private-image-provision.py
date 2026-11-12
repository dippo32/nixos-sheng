#!/usr/bin/env python3
"""Exercise the provisioner on tiny disposable ext4 images, never devices."""

import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/provision-private-image.py"
REQUIRED = ("mke2fs", "debugfs", "e2fsck", "img2simg", "simg2img", "zstd", "cp")


@unittest.skipUnless(all(shutil.which(tool) for tool in REQUIRED), "host image tools must be in PATH")
class PrivateImageTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="private-image-test-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.base = self.work / "public base.ext4"
        with self.base.open("wb") as handle:
            handle.truncate(32 * 1024 * 1024)
        self.command("mke2fs", "-q", "-t", "ext4", "-F", str(self.base))
        self.hash_file = self.work / 'private hash "input"'
        # Generated per run; no PIN or password hash fixture lives in Git.
        self.hash_content = ("$6$" + secrets.token_hex(8) + "$" + secrets.token_hex(48) + "\n").encode()
        self.hash_file.write_bytes(self.hash_content)
        self.hash_file.chmod(0o600)
        self.seed = self.work / "private seed.tar.zst"
        self.make_seed(self.seed, 128 * 1024)
        self.output = self.work / "private-output.sparse.img"
        self.original = self.digest(self.base)

    def command(self, *command, input=None):
        return subprocess.run(command, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout

    def make_seed(self, path, size):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as handle:
            payload = secrets.token_bytes(size)
            entry = tarfile.TarInfo("app/fixture/data")
            entry.size = len(payload)
            handle.addfile(entry, io.BytesIO(payload))
        path.write_bytes(self.command("zstd", "-q", "-c", input=archive.getvalue()))
        path.chmod(0o600)

    def digest(self, path):
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()

    def invoke(self, *, base=None, hash_file=None, seed=None, output=None, reserve=False, env=None):
        command = [
            sys.executable, str(SCRIPT), "--base", str(base or self.base),
            "--password-hash-file", str(hash_file or self.hash_file),
            "--flatpak-seed", str(seed or self.seed), "--output", str(output or self.output),
        ]
        if reserve:
            command.append("--remove-reserve")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.assertNotIn(self.hash_content.strip(), result.stdout + result.stderr)
        return result

    def unpack_output(self):
        raw = self.work / "verified.ext4"
        self.command("simg2img", str(self.output), str(raw))
        return raw

    def read_image(self, raw, path):
        return self.command("debugfs", "-R", "cat " + path, str(raw))

    def test_raw_image_injection_preserves_base_and_private_metadata(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(self.digest(self.base), self.original)
        raw = self.unpack_output()
        self.assertEqual(raw.stat().st_size, self.base.stat().st_size)
        self.command("e2fsck", "-f", "-n", str(raw))
        self.assertEqual(self.read_image(raw, "/var/lib/sheng-private/login.hash"), self.hash_content)
        self.assertEqual(self.read_image(raw, "/var/lib/sheng-private/flatpak-seed.tar.zst"), self.seed.read_bytes())
        for target, mode in (("/var/lib/sheng-private", "0700"), ("/var/lib/sheng-private/login.hash", "0600"), ("/var/lib/sheng-private/flatpak-seed.tar.zst", "0600")):
            inode = self.command("debugfs", "-R", "stat " + target, str(raw)).decode()
            self.assertRegex(inode, r"Mode:\s+" + mode)
            self.assertRegex(inode, r"User:\s+0\s+Group:\s+0")
        for suffix in ("", ".sha256", ".provenance.json"):
            self.assertEqual(stat.S_IMODE(Path(str(self.output) + suffix).stat().st_mode), 0o600)
        note = Path(str(self.output) + ".provenance.json").read_bytes()
        self.assertNotIn(self.hash_content.strip(), note)
        provenance = json.loads(note)
        self.assertFalse(provenance["filesystemResized"])
        self.assertEqual(provenance["output"]["sha256"], self.digest(self.output))
        self.assertEqual(provenance["base"]["sha256"], self.original)
        self.assertTrue(Path(str(self.output) + ".sha256").read_text().startswith(self.digest(self.output) + "  "))

    def test_sparse_input_and_optional_reserve_removal(self):
        self.command("debugfs", "-w", "-R", "mkdir /var", str(self.base))
        self.command("debugfs", "-w", "-R", "mkdir /var/lib", str(self.base))
        self.command("debugfs", "-w", "-R", "mkdir /var/lib/sheng-private", str(self.base))
        reserve = self.work / "reserve"
        reserve.write_bytes(secrets.token_bytes(1024 * 1024))
        self.command("debugfs", "-w", "-R", f"write {reserve} /var/lib/sheng-private/.provisioning-reserve", str(self.base))
        sparse = self.work / "base.sparse.img"
        self.command("img2simg", str(self.base), str(sparse))
        before = self.digest(sparse)
        result = self.invoke(base=sparse, reserve=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(self.digest(sparse), before)
        raw = self.unpack_output()
        inode = self.command("debugfs", "-R", "stat /var/lib/sheng-private/.provisioning-reserve", str(raw))
        self.assertNotIn(b"Inode:", inode)
        self.assertTrue(json.loads(Path(str(self.output) + ".provenance.json").read_text())["reserveRemoved"])

    def test_insufficient_space_fails_without_output_or_resize(self):
        self.make_seed(self.seed, 33 * 1024 * 1024)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"insufficient free blocks", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.digest(self.base), self.original)
        self.assertEqual(list(self.work.glob(".provision-private-*")), [])

    def test_existing_output_and_sidecar_are_never_overwritten(self):
        for suffix in ("", ".sha256", ".provenance.json"):
            target = Path(str(self.output) + suffix)
            target.write_bytes(b"keep this existing file")
            result = self.invoke()
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_bytes(), b"keep this existing file")
            target.unlink()
        self.assertFalse(self.output.exists())

    def test_symlink_and_fifo_inputs_are_rejected(self):
        linked = self.work / "linked.ext4"
        linked.symlink_to(self.base)
        self.assertNotEqual(self.invoke(base=linked).returncode, 0)
        fifo = self.work / "pipe.ext4"
        os.mkfifo(fifo)
        self.assertNotEqual(self.invoke(base=fifo).returncode, 0)
        self.assertFalse(self.output.exists())

    def test_invalid_hash_and_nonprivate_destination_fail_without_secrets(self):
        invalid = secrets.token_hex(18).encode()
        self.hash_file.write_bytes(invalid)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(invalid, result.stdout + result.stderr)
        self.hash_file.write_bytes(self.hash_content)
        public_directory = self.work / "public"
        public_directory.mkdir(mode=0o755)
        public_directory.chmod(0o755)
        self.assertNotEqual(self.invoke(output=public_directory / "image").returncode, 0)

    def test_corrupt_seed_and_exposed_hash_file_fail_closed(self):
        self.hash_file.chmod(0o644)
        self.assertNotEqual(self.invoke().returncode, 0)
        self.hash_file.chmod(0o600)
        self.seed.write_bytes(secrets.token_bytes(128))
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.digest(self.base), self.original)

    def test_symlink_in_private_destination_path_is_rejected(self):
        self.command("debugfs", "-w", "-R", "symlink /var /elsewhere", str(self.base))
        original = self.digest(self.base)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"non-directory inode", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.digest(self.base), original)

    def test_never_clean_checker_is_bounded(self):
        tools = self.work / "tools"
        tools.mkdir()
        checker = tools / "e2fsck"
        checker.write_text('#!/bin/sh\nprintf "called\\n" >> "$FSCK_CALLS"\nexit 1\n')
        checker.chmod(0o700)
        calls = self.work / "checker-calls"
        env = os.environ | {"PATH": str(tools) + os.pathsep + os.environ["PATH"], "FSCK_CALLS": str(calls)}
        result = self.invoke(env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.read_text().splitlines(), ["called"] * 3)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.digest(self.base), self.original)

    def test_publication_race_preserves_existing_sidecar_and_rolls_back_image(self):
        tools = self.work / "tools"
        tools.mkdir()
        converter = tools / "img2simg"
        converter.write_text(
            '#!/usr/bin/env python3\nimport os,sys\n'
            'with open(os.environ["COLLIDE_WITH"], "xb") as f: f.write(b"existing sidecar")\n'
            'os.execv(os.environ["REAL_IMG2SIMG"], [os.environ["REAL_IMG2SIMG"], *sys.argv[1:]])\n'
        )
        converter.chmod(0o700)
        sidecar = Path(str(self.output) + ".sha256")
        env = os.environ | {
            "PATH": str(tools) + os.pathsep + os.environ["PATH"],
            "COLLIDE_WITH": str(sidecar), "REAL_IMG2SIMG": shutil.which("img2simg"),
        }
        self.assertNotEqual(self.invoke(env=env).returncode, 0)
        self.assertEqual(sidecar.read_bytes(), b"existing sidecar")
        self.assertFalse(self.output.exists())
        self.assertFalse(Path(str(self.output) + ".provenance.json").exists())
        self.assertEqual(self.digest(self.base), self.original)


if __name__ == "__main__":
    unittest.main()
