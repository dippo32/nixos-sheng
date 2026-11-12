#!/usr/bin/env python3
"""Provision a disposable ext4 image copy; never mount or resize a filesystem.

Run on the host with debugfs, e2fsck, simg2img, img2simg, zstd and cp in PATH.
All inputs must be regular, non-symlink files. The output directory must already
be private (0700); the output and its two sidecars must not exist. Password hash
content is never placed in arguments, logs, provenance, or a Nix expression.
"""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile


PRIVATE_DIR = "/var/lib/sheng-private"
HASH_TARGET = PRIVATE_DIR + "/login.hash"
SEED_TARGET = PRIVATE_DIR + "/flatpak-seed.tar.zst"
RESERVE_TARGET = PRIVATE_DIR + "/.provisioning-reserve"
SPARSE_MAGIC = 0xED26FF3A
TOOLS = ("debugfs", "e2fsck", "simg2img", "img2simg", "zstd", "cp")


class ProvisionError(Exception):
    pass


def run(command, *, cwd, pass_fds=()):
    """Capture tool diagnostics: debugfs cat output can contain credentials."""
    result = subprocess.run(
        [str(arg) for arg in command],
        cwd=cwd,
        pass_fds=pass_fds,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ | {"LC_ALL": "C"},
    )
    if result.returncode:
        raise ProvisionError(f"{Path(command[0]).name} failed; no image published")
    return result.stdout


def regular_input(stack, path, label, *, private=False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise ProvisionError(f"cannot open {label} as a regular non-symlink file") from None
    stack.callback(os.close, fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise ProvisionError(f"{label} must be a regular file")
    if private and stat.S_IMODE(info.st_mode) & 0o077:
        raise ProvisionError(f"{label} must not be readable by group or others")
    if not info.st_size:
        raise ProvisionError(f"{label} is empty")
    return fd, info


def digest_fd(fd):
    digest = hashlib.sha256()
    offset = 0
    while data := os.pread(fd, 1024 * 1024, offset):
        digest.update(data)
        offset += len(data)
    return digest.hexdigest()


def unchanged(fd, before):
    after = os.fstat(fd)
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise ProvisionError("an input changed during provisioning; no image published")


def digest_file(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def image_format(fd):
    magic = os.pread(fd, 4, 0)
    if magic == struct.pack("<I", SPARSE_MAGIC):
        return "android-sparse"
    if os.pread(fd, 2, 1080) == b"\x53\xef":
        return "raw-ext4"
    raise ProvisionError("base image is neither Android sparse nor raw ext4")


def validate_hash(fd):
    data = os.pread(fd, 4097, 0)
    body = data.removesuffix(b"\n")
    if len(data) > 4096 or not re.fullmatch(
        rb"\$(?:y|gy|6|5|2[aby]|7)\$[A-Za-z0-9./$=,+-]+", body
    ):
        raise ProvisionError("password hash file must contain one modular-crypt hash line")
    return data


def fsck_clean(image, cwd):
    for _ in range(3):
        result = subprocess.run(
            ["e2fsck", "-f", "-y", str(image)],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ | {"LC_ALL": "C"},
        )
        if result.returncode == 0:
            return
        if result.returncode != 1:
            raise ProvisionError("filesystem check failed; no image published")
    raise ProvisionError("filesystem did not reach a clean check in three passes")


class Filesystem:
    def __init__(self, image, cwd):
        self.image = image
        self.cwd = cwd

    def command(self, text, *, write=False, pass_fds=()):
        command = ["debugfs"] + (["-w"] if write else [])
        return run(command + ["-R", text, self.image], cwd=self.cwd, pass_fds=pass_fds)

    def inode(self, path):
        output = self.command("stat " + path).decode("ascii", errors="replace")
        metadata = re.search(r"Type:\s+(\w+)\s+Mode:\s+([0-7]+)", output)
        owner = re.search(r"User:\s+(\d+)\s+Group:\s+(\d+)\s+.*?Size:\s+(\d+)", output)
        if not metadata or not owner:
            return None
        return {
            "type": metadata[1],
            "mode": int(metadata[2], 8),
            "uid": int(owner[1]),
            "gid": int(owner[2]),
            "size": int(owner[3]),
        }

    def attributes(self, path, mode):
        for field, value in (("mode", mode), ("uid", "0"), ("gid", "0")):
            self.command(f"set_inode_field {path} {field} {value}", write=True)

    def ensure_private_directory(self):
        for path in ("/var", "/var/lib", PRIVATE_DIR):
            info = self.inode(path)
            if info is None:
                self.command("mkdir " + path, write=True)
                self.attributes(path, "040755")
            elif info["type"] != "directory":
                raise ProvisionError("private directory path contains a non-directory inode")
        self.attributes(PRIVATE_DIR, "040700")

    def remove_regular(self, path):
        info = self.inode(path)
        if info is None:
            return False
        if info["type"] != "regular":
            raise ProvisionError("refusing to replace a non-regular private inode")
        self.command("rm " + path, write=True)
        if self.inode(path) is not None:
            raise ProvisionError("private inode removal failed")
        return True

    def write(self, fd, target):
        self.remove_regular(target)
        # An inherited descriptor is stable and avoids quoting untrusted host
        # filenames in debugfs's separate command language.
        self.command(f"write /proc/self/fd/{fd} {target}", write=True, pass_fds=(fd,))
        self.attributes(target, "0100600")

    def free_space(self):
        output = self.command("stats").decode("ascii", errors="replace")
        values = {}
        for field in ("Block size", "Free blocks", "Free inodes"):
            match = re.search(r"^" + field + r":\s+(\d+)", output, re.MULTILINE)
            if not match:
                raise ProvisionError("could not read filesystem free-space accounting")
            values[field] = int(match[1])
        return values

    def verify_metadata(self, path, kind, mode, size=None):
        info = self.inode(path)
        if (
            info is None
            or info["type"] != kind
            or info["mode"] != mode
            or info["uid"] != 0
            or info["gid"] != 0
            or (size is not None and info["size"] != size)
        ):
            raise ProvisionError("private inode metadata verification failed")

    def digest(self, path):
        digest = hashlib.sha256()
        with subprocess.Popen(
            ["debugfs", "-R", "cat " + path, str(self.image)],
            cwd=self.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=os.environ | {"LC_ALL": "C"},
        ) as process:
            while data := process.stdout.read(1024 * 1024):
                digest.update(data)
            if process.wait():
                raise ProvisionError("private seed readback failed")
        return digest.hexdigest()


def private_file(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def publish(files):
    """Hard links provide atomic no-replace publication on the same filesystem."""
    created = []
    try:
        for source, target in files:
            os.link(source, target)
            created.append((source, target))
        directory = os.open(files[0][1].parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        for source, target in reversed(created):
            try:
                if os.stat(source).st_ino == os.lstat(target).st_ino:
                    os.unlink(target)
            except FileNotFoundError:
                pass
        raise


def provision(args):
    os.umask(0o077)
    output = Path(args.output).absolute()
    parent = output.parent.resolve(strict=True)
    parent_info = parent.stat()
    if not stat.S_ISDIR(parent_info.st_mode) or stat.S_IMODE(parent_info.st_mode) & 0o077:
        raise ProvisionError("output directory must already be private (0700)")
    output = parent / output.name
    if "\n" in output.name or "\r" in output.name:
        raise ProvisionError("output filename must not contain line breaks")
    checksum = output.with_name(output.name + ".sha256")
    provenance = output.with_name(output.name + ".provenance.json")
    if any(os.path.lexists(path) for path in (output, checksum, provenance)):
        raise ProvisionError("output or sidecar already exists; refusing to overwrite")
    for tool in TOOLS:
        if shutil.which(tool) is None:
            raise ProvisionError(f"required host tool is missing: {tool}")

    with ExitStack() as stack:
        base_fd, base_info = regular_input(stack, args.base, "base image")
        hash_fd, hash_info = regular_input(stack, args.password_hash_file, "password hash file", private=True)
        seed_fd, seed_info = regular_input(stack, args.flatpak_seed, "Flatpak seed", private=True)
        hash_content = validate_hash(hash_fd)
        base_format = image_format(base_fd)
        base_digest = digest_fd(base_fd)
        seed_digest = digest_fd(seed_fd)

        with tempfile.TemporaryDirectory(prefix=".provision-private-", dir=parent) as temporary:
            work = Path(temporary)
            raw = work / "filesystem.ext4"
            # zstd otherwise skips the /proc descriptor symlink. -f only
            # permits following it in test mode; there is no output to replace.
            run(["zstd", "-t", "-q", "-f", f"/proc/self/fd/{seed_fd}"], cwd=work, pass_fds=(seed_fd,))
            source = f"/proc/self/fd/{base_fd}"
            if base_format == "android-sparse":
                run(["simg2img", source, raw], cwd=work, pass_fds=(base_fd,))
            else:
                run(["cp", "--reflink=auto", "--sparse=always", source, raw], cwd=work, pass_fds=(base_fd,))
            raw.chmod(0o600)
            with raw.open("rb") as handle:
                if image_format(handle.fileno()) != "raw-ext4":
                    raise ProvisionError("converted base image is not ext4")
            fsck_clean(raw, work)
            filesystem = Filesystem(raw, work)
            removed = filesystem.remove_regular(RESERVE_TARGET) if args.remove_reserve else False
            filesystem.ensure_private_directory()
            available = filesystem.free_space()
            block = available["Block size"]
            data_blocks = sum((size + block - 1) // block for size in (hash_info.st_size, seed_info.st_size))
            # Leave conservative metadata headroom; exact allocation/readback and
            # the final fsck remain authoritative. Never resize to make it fit.
            overhead = max((1024 * 1024 + block - 1) // block, (data_blocks + 99) // 100)
            if available["Free blocks"] < data_blocks + overhead or available["Free inodes"] < 2:
                raise ProvisionError("insufficient free blocks/inodes for private payload; resizing is disabled")
            filesystem.write(hash_fd, HASH_TARGET)
            filesystem.write(seed_fd, SEED_TARGET)
            fsck_clean(raw, work)
            filesystem.verify_metadata(PRIVATE_DIR, "directory", 0o700)
            filesystem.verify_metadata(HASH_TARGET, "regular", 0o600, len(hash_content))
            filesystem.verify_metadata(SEED_TARGET, "regular", 0o600, seed_info.st_size)
            if filesystem.command("cat " + HASH_TARGET) != hash_content:
                raise ProvisionError("private password file readback failed")
            if filesystem.digest(SEED_TARGET) != seed_digest:
                raise ProvisionError("private seed readback mismatch")
            final_space = filesystem.free_space()

            sparse = work / "private.sparse.img"
            run(["img2simg", raw, sparse], cwd=work)
            sparse.chmod(0o600)
            with sparse.open("rb") as handle:
                header = handle.read(28)
            if len(header) != 28:
                raise ProvisionError("output sparse header is truncated")
            magic, major, minor, file_header, chunk_header, block_size, blocks, chunks, crc = struct.unpack(
                "<I4H4I", header
            )
            if magic != SPARSE_MAGIC or major != 1 or block_size * blocks != raw.stat().st_size:
                raise ProvisionError("output sparse image geometry verification failed")
            output_digest = digest_file(sparse)
            note = {
                "schemaVersion": 1,
                "provisionerSha256": digest_file(Path(__file__).resolve()),
                "base": {"format": base_format, "bytes": base_info.st_size, "sha256": base_digest},
                "seed": {"bytes": seed_info.st_size, "sha256": seed_digest},
                "output": {"format": "android-sparse", "bytes": sparse.stat().st_size, "sha256": output_digest},
                "passwordHash": "readback verified; content deliberately omitted",
                "privateModes": "directory 0700; files 0600; uid/gid 0",
                "reserveRemoved": removed,
                "filesystem": {"blockSize": block, "freeBlocksAfter": final_space["Free blocks"]},
                "filesystemResized": False,
            }
            note_file = work / "provenance.json"
            checksum_file = work / "checksum.txt"
            private_file(note_file, (json.dumps(note, indent=2) + "\n").encode())
            private_file(checksum_file, f"{output_digest}  {output.name}\n".encode())
            for fd, info in ((base_fd, base_info), (hash_fd, hash_info), (seed_fd, seed_info)):
                unchanged(fd, info)
            with sparse.open("rb") as handle:
                os.fsync(handle.fileno())
            publish(((sparse, output), (checksum_file, checksum), (note_file, provenance)))
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path, help="regular raw ext4 or Android sparse image")
    parser.add_argument("--password-hash-file", required=True, type=Path, help="private file containing one password hash")
    parser.add_argument("--flatpak-seed", required=True, type=Path, help="private flatpak-seed.tar.zst")
    parser.add_argument("--output", required=True, type=Path, help="new private Android sparse image; parent directory must be 0700")
    parser.add_argument("--remove-reserve", action="store_true", help="remove only the known provisioning reserve inode from the copy")
    args = parser.parse_args(argv)
    try:
        provision(args)
    except (ProvisionError, OSError) as error:
        # Do not echo tool output, file contents, or command arguments here.
        message = str(error) if isinstance(error, ProvisionError) else "host filesystem operation failed"
        print("Provisioning failed: " + message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Provisioning cancelled; inspect output files before retrying", file=sys.stderr)
        return 130
    print("Private sparse image created; checksum and provenance saved beside it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
