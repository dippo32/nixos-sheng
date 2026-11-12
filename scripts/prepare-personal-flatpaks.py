#!/usr/bin/env python3
"""Prepare a private, mutable ARM64 Flatpak seed; never run the ARM payloads.

Without --prepare this validates local inputs and prints the proposed operation.
All generated files, downloads and package contents stay outside the checkout.
"""

import argparse
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


ARCH = "aarch64"
RUNTIME_BRANCH = "26.08"
BASE = "org.electronjs.Electron2.BaseApp"
PLATFORM = "org.freedesktop.Platform"
SDK = "org.freedesktop.Sdk"
LIBREWOLF = "app/io.gitlab.librewolf-community/aarch64/stable"
# Public Flathub stable ARM64 ref checked on 2026-11-13. Future Discover updates
# remain possible; this selects the initial image version only.
LIBREWOLF_COMMIT = "a43d447a28d39983e09bac8932222a0932eee0348fc9447833f78d3e354a630f"
TARGET_FLATPAK = "/run/current-system/sw/bin/flatpak"
TARGET_PREFIX = "home/dippo/.local/share/flatpak"
APP_IDS = {
    "chatgpt": "io.github.dippo32.ChatGPT",
    "antigravity": "io.github.dippo32.AntigravityIDE",
}
OFFICIAL_DOMAINS = {
    "chatgpt": ("openai.com", "chatgpt.com", "oaistatic.com"),
    "antigravity": ("antigravity.google", "google.com", "googleapis.com", "gvt1.com"),
}
# These exceptions describe bundled alternatives, not runnable target binaries.
# The exact bundled JS loaders were read before adding them: pkg-prebuilds 1.1.0
# derives HID paths from os.platform()/os.arch(), while node-gyp-build 4.8.4
# filters serialport prebuild tuples by the current platform and architecture.
DEVICE_KIT_MODULES = "node_modules/@worklouder/device-kit-oai/node_modules/@worklouder/wl-device-kit/node_modules/"
PREBUILD_LOADERS = {
    "node-hid/nodehid.js": "fdfbaa5a6daf95886de570df6536f0c7ba59991db62222e4cf5b512225c09bf5",
    "node-hid/binding-options.js": "e7c820107f3b6571ca1505a5ffbe17511088336e4c410ec718ea9ec200c6b1e6",
    "node-hid/node_modules/pkg-prebuilds/bindings.js": "fee3428decad2ed6c12a54e50b67eb870bb4b2b09bceef59400d5fb23cd6edea",
    "node-hid/node_modules/pkg-prebuilds/lib/prebuild.js": "a3b92966137073a31a19fb17a1bc78d9bcf07a17d363c645d0983f074435ae33",
    "serialport/node_modules/@serialport/bindings-cpp/dist/load-bindings.js": "f70c71d7d2e810ff570afc60be81ed6c82ed40f16d7f632860e30873635fc722",
    "serialport/node_modules/@serialport/bindings-cpp/dist/poller.js": "f3eae01b7733ff7cd2a260aa607056e5f0c473377fb7dbd44b18c75ae89bd58f",
    "serialport/node_modules/@serialport/bindings-cpp/node_modules/node-gyp-build/index.js": "a7ed0d5ae218a19bdbdf15a590d0893790ddf536313b66a787554693cfaae078",
    "serialport/node_modules/@serialport/bindings-cpp/node_modules/node-gyp-build/node-gyp-build.js": "134f0585f7c665db89f332a379158c6f113274422e42aaf54e0aa9d5ac37f577",
}


class PreparationError(Exception):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value):
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or any(ord(char) < 32 for char in value)
        or str(path) == "."
    ):
        raise PreparationError("The executable must be a relative path without '..' or control characters")
    return path


def is_within(path, directory):
    return path == directory or directory in path.parents


def check_elf(path, required=False):
    with path.open("rb") as source:
        header = source.read(64)
    if not header.startswith(b"\x7fELF"):
        if required:
            raise PreparationError(f"Main executable is not an ELF binary: {path}")
        return False
    if len(header) < 64 or header[4:6] != bytes((2, 1)):
        raise PreparationError(f"Expected a 64-bit little-endian ELF: {path}")
    machine = struct.unpack_from("<H", header, 18)[0]
    if machine != 183:
        raise PreparationError(f"Non-AArch64 ELF (e_machine={machine}): {path}")
    return True


def asar_loader_hashes(archive):
    """Read bounded source entries from ASAR as data, without loading JS/addons."""
    if archive.is_symlink() or not archive.is_file():
        raise PreparationError("Optional prebuild exceptions require the original app.asar")
    result = {}
    with archive.open("rb") as source:
        prefix = source.read(16)
        if len(prefix) != 16:
            raise PreparationError("Truncated app.asar header")
        pickle_size, header_size, _, json_size = struct.unpack("<4I", prefix)
        if pickle_size != 4 or not 8 <= header_size <= 16 * 1024 * 1024 or not 0 < json_size <= header_size - 8:
            raise PreparationError("Unsupported app.asar header")
        header = json.loads(source.read(json_size))
        for relative, expected in PREBUILD_LOADERS.items():
            entry = header
            try:
                for part in (DEVICE_KIT_MODULES + relative).split("/"):
                    entry = entry["files"][part]
                offset, size = int(entry["offset"]), int(entry["size"])
                if entry.get("unpacked") or offset < 0 or not 0 < size <= 1024 * 1024:
                    raise ValueError("unsupported source entry")
                source.seek(8 + header_size + offset)
                content = source.read(size)
                if len(content) != size or hashlib.sha256(content).hexdigest() != expected:
                    raise ValueError("loader source changed")
            except (KeyError, TypeError, ValueError) as error:
                raise PreparationError("Optional prebuild loader needs a new source audit: " + relative) from error
            result[DEVICE_KIT_MODULES + relative] = expected
    return result


def optional_prebuilds(root):
    """Allow only audited non-target Node addon alternatives; retain every byte."""
    base = "resources/app.asar.unpacked/" + DEVICE_KIT_MODULES
    candidates = {}
    for binding in ("HID", "HID_hidraw"):
        prefix = base + "node-hid/prebuilds/" + binding + "-linux-"
        counterpart = prefix + "arm64/node-napi-v4.node"
        for other, elf in (("arm", (1, 1, 40)), ("x64", (2, 1, 62)), ("x64-musl", (2, 1, 62))):
            candidates[prefix + other + "/node-napi-v4.node"] = (elf, counterpart)
    prefix = base + "serialport/node_modules/@serialport/bindings-cpp/prebuilds/"
    for other in ("android-arm/node.napi.armv7.node", "linux-arm/node.napi.armv6.node", "linux-arm/node.napi.armv7.node"):
        candidates[prefix + other] = ((1, 1, 40), prefix + "linux-arm64/node.napi.armv8.node")
    for libc in ("glibc", "musl"):
        candidates[prefix + "linux-x64/node.napi." + libc + ".node"] = ((2, 1, 62), prefix + "linux-arm64/node.napi.armv8.node")
    retained = {}
    for relative, (expected, counterpart) in candidates.items():
        path = root / relative
        if not path.exists():
            continue
        target = root / counterpart
        if (path.is_symlink() or not path.is_file() or not target.is_file() or
                not is_within(path.resolve(), root) or not is_within(target.resolve(), root)):
            raise PreparationError("Optional prebuild or counterpart escapes the payload")
        check_elf(target, required=True)
        with path.open("rb") as source:
            header = source.read(64)
        if (len(header) < 64 or header[:4] != b"\x7fELF" or
                (header[4], header[5], struct.unpack_from("<H", header, 18)[0]) != expected):
            raise PreparationError("Optional prebuild differs from its audited architecture: " + relative)
        retained[relative] = {
            "path": relative, "elf_class": expected[0], "elf_machine": expected[2],
            "linux_arm64_counterpart": counterpart,
            "disposition": "retained vendor non-target optional prebuild; not a target ELF",
        }
    archive = root / "resources/app.asar"
    if retained and not is_within(archive.resolve(), root):
        raise PreparationError("Optional prebuild loader archive escapes the payload")
    loaders = asar_loader_hashes(archive) if retained else {}
    return retained, loaders


def validate_tree(directory, executable):
    if directory.is_symlink() or not directory.is_dir():
        raise PreparationError(f"Payload must be an unpacked directory, not a symlink/archive: {directory}")
    root = directory.resolve(strict=True)
    relative = safe_relative(executable)
    entry = root.joinpath(*relative.parts)
    try:
        resolved = entry.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise PreparationError(f"Cannot resolve main executable {entry}: {error}") from error
    if not is_within(resolved, root) or not resolved.is_file():
        raise PreparationError("Main executable escapes its payload directory or is not a regular file")
    if not resolved.stat().st_mode & 0o111:
        raise PreparationError(f"Main executable has no executable permission: {entry}")
    check_elf(resolved, required=True)
    retained, loaders = optional_prebuilds(root)
    digest = hashlib.sha256()
    count = 0
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        info = path.lstat()
        if any(ord(char) < 32 for char in name):
            raise PreparationError(f"Control character in payload filename: {name!r}")
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            try:
                destination = path.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                raise PreparationError(f"Dangling or looping payload symlink: {name}") from error
            if os.path.isabs(target) or not is_within(destination, root):
                raise PreparationError(f"Payload symlink escapes its directory: {name}")
            detail = "link:" + target
        elif stat.S_ISREG(info.st_mode):
            if name not in retained:
                count += int(check_elf(path))
            detail = "file:" + sha256_file(path)
        elif stat.S_ISDIR(info.st_mode):
            detail = "dir"
        else:
            raise PreparationError(f"Special files are not allowed in a payload: {name}")
        digest.update(json.dumps([name, stat.S_IMODE(info.st_mode), detail], ensure_ascii=True).encode() + b"\n")
    return root, relative, {
        "tree_sha256": digest.hexdigest(), "aarch64_elf_files": count,
        "foreign_arch_optional_prebuilds_as_data": list(retained.values()),
        "audited_optional_prebuild_loader_sha256": loaders,
    }


def validate_provenance(path, key, archive):
    with path.open(encoding="utf-8") as source:
        document = json.load(source)
    if not isinstance(document, dict) or not isinstance(document.get(key), dict):
        raise PreparationError(f"{key}: provenance must contain an object for this application")
    item = document.get(key, {})
    version = item.get("version", "")
    source_url = item.get("source_url", "")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_~-]{0,99}", version):
        raise PreparationError(f"{key}: provenance needs a plain release version")
    if not isinstance(source_url, str):
        raise PreparationError(f"{key}: source_url must be a public official HTTPS URL")
    url = urlsplit(source_url)
    hostname = (url.hostname or "").lower()
    official = any(hostname == domain or hostname.endswith("." + domain) for domain in OFFICIAL_DOMAINS[key])
    if not official or url.scheme != "https" or url.username or url.password or url.query or url.fragment or url.port not in (None, 443):
        raise PreparationError(f"{key}: source_url must be a public official HTTPS URL without credentials/query/fragment")
    result = {"version": version, "source_url": source_url}
    for date_key in ("release_date", "observed_download_date"):
        if date_key in item:
            try:
                value = item[date_key]
                if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError("expected YYYY-MM-DD")
                result[date_key] = datetime.date.fromisoformat(value).isoformat()
            except (TypeError, ValueError) as error:
                raise PreparationError(f"{key}: {date_key} must be YYYY-MM-DD when provided") from error
    if archive is not None:
        if not archive.is_file() or archive.is_symlink():
            raise PreparationError(f"{key}: archive must be a regular local file")
        actual = sha256_file(archive)
        expected = item.get("archive_sha256")
        if expected is not None and expected != actual:
            raise PreparationError(f"{key}: archive SHA256 differs from the private provenance")
        result["archive_sha256"] = actual
    elif "archive_sha256" in item:
        raise PreparationError(f"{key}: provide --{key}-archive to verify archive_sha256")
    return result


def environment(output):
    env = {key: value for key, value in os.environ.items() if not key.startswith("FLATPAK_")}
    env.update({
        "FLATPAK_USER_DIR": str(output / "flatpak"),
        "FLATPAK_SYSTEM_DIR": str(output / "empty-system"),
        "FLATPAK_CONFIG_DIR": str(output / "site-config"),
        "FLATPAK_BINARY": TARGET_FLATPAK,
        "FLATPAK_GL_DRIVERS": "default",
        "XDG_CACHE_HOME": str(output / "cache"),
        "XDG_CONFIG_HOME": str(output / "user-config"),
        "XDG_DATA_HOME": str(output / "user-data"),
        "TMPDIR": str(output / "tmp"),
    })
    return env


def run(arguments, env, capture=False):
    return subprocess.run(arguments, env=env, check=True, text=True, capture_output=capture).stdout


def write_text(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def app_protocol(key, root):
    # ChatGPT's official Debian desktop entry declares codex. Antigravity's
    # exact protocol is release metadata, not the visible application name.
    if key == "chatgpt":
        return "codex"
    with (root / "resources/app/product.json").open(encoding="utf-8") as source:
        protocol = json.load(source).get("urlProtocol")
    if (not isinstance(protocol, str) or not re.fullmatch(r"[a-z][a-z0-9+.-]{1,63}", protocol)
            or protocol in {"http", "https", "file"}):
        raise PreparationError("Antigravity product.json needs a valid application-specific urlProtocol")
    return protocol


def check_zypak_wrapper(files):
    """Resolve only the audited /app alias against the app tree, not the host."""
    wrapper = files / "bin/zypak-wrapper"
    if wrapper.is_symlink():
        if os.readlink(wrapper) != "/app/bin/zypak-wrapper.sh":
            raise PreparationError("Electron2 BaseApp has an unexpected Zypak wrapper alias")
        wrapper = files / "bin/zypak-wrapper.sh"
    if (wrapper.is_symlink() or not wrapper.is_file() or
            not is_within(wrapper.resolve(), files.resolve()) or
            not wrapper.stat().st_mode & 0o111):
        raise PreparationError("Electron2 BaseApp lacks a regular executable Zypak wrapper")


def validate_reuse_installation(source, output, repository):
    if source.is_symlink() or not source.is_dir():
        raise PreparationError("Reuse source must be an existing private Flatpak directory")
    source = source.resolve(strict=True)
    if is_within(source, repository) or "/nix/store/" in str(source) + "/":
        raise PreparationError("Reuse source must be outside the checkout and Nix store")
    if is_within(source, output) or is_within(output, source):
        raise PreparationError("Reuse source and new output must not overlap")
    config = source / "repo/config"
    if config.is_symlink() or not config.is_file() or not is_within(config.resolve(), source):
        raise PreparationError("Reuse source must contain a regular repo/config inside its tree")
    return source


def clone_installation(source, destination, env):
    if destination.exists() or destination.is_symlink():
        raise PreparationError("Reuse destination must not exist")
    # Reflinks are copy-on-write; cp -a preserves links within the copy without
    # hardlinking any mutable repository data back to the original installation.
    run(["cp", "-a", "--reflink=auto", "--", str(source), str(destination)], env)


def compose_appstream(files, app_id, env):
    """Compose on the native host; no command is run inside the ARM SDK."""
    composer = shutil.which("appstreamcli")
    if composer is None:
        raise PreparationError("Native appstreamcli with compose support is required")
    info = files / "share/app-info"
    run([composer, "compose", "--no-net", "--prefix=/", "--origin=flatpak",
         "--components=" + app_id, "--image-format=png",
         "--data-dir=" + str(info / "xmls"),
         "--icons-dir=" + str(info / "icons/flatpak"), str(files)], env)
    generated = info / "xmls/flatpak.xml.gz"
    if not generated.is_file():
        raise PreparationError("AppStream compose did not generate its catalog")
    with gzip.open(generated, "rb") as source:
        catalog = ET.parse(source).getroot()
    if not any(component.findtext("id") == app_id for component in catalog.findall("component")):
        raise PreparationError("AppStream compose omitted the selected application: " + app_id)
    for size in ("64x64", "128x128"):
        if not (info / "icons/flatpak" / size / (app_id + ".png")).is_file():
            raise PreparationError("AppStream compose omitted a required cached icon: " + app_id)
    # Flatpak 1.18.4's appstream extractor requires this exact filename; the
    # composer names its output after the origin instead of the component ID.
    generated.rename(info / "xmls" / (app_id + ".xml.gz"))


def package_app(flatpak, output, env, key, payload, provenance, branch):
    app_id = APP_IDS[key]
    root, executable, _ = payload
    build = output / "build" / key
    run([flatpak, "build-init", "--arch=" + ARCH, "--base=" + BASE, "--base-version=" + branch,
         str(build), app_id, SDK, PLATFORM, branch], env)
    files = build / "files"
    check_zypak_wrapper(files)
    shutil.copytree(root, files / "personal-payload", symlinks=True)
    command = key + "-personal"
    write_text(files / "bin" / command,
               "#!/bin/sh\nexec zypak-wrapper " + shlex.quote("/app/personal-payload/" + executable.as_posix()) + ' "$@"\n', 0o755)
    title = "ChatGPT" if key == "chatgpt" else "Antigravity IDE"
    summary = "Personal package of the official ARM64 desktop application"
    protocol = app_protocol(key, root)
    write_text(files / "share/applications" / (app_id + ".desktop"),
               f"[Desktop Entry]\nName={title}\nComment={summary}\nExec={command} %U\n"
               f"Icon={app_id}\nType=Application\nMimeType=x-scheme-handler/{protocol};\n"
               f"Categories={'Network;Chat;' if key == 'chatgpt' else 'Development;IDE;'}\nTerminal=false\n")
    write_text(files / "share/icons/hicolor/scalable/apps" / (app_id + ".svg"),
               '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">'
               '<rect x="8" y="8" width="112" height="112" rx="24" fill="#255987"/>'
               '<path d="M36 38h56v40H65L46 94V78H36z" fill="white"/></svg>\n')
    component = ET.Element("component", {"type": "desktop-application"})
    for tag, text in [("id", app_id), ("metadata_license", "CC0-1.0"), ("project_license", "LicenseRef-proprietary"),
                      ("name", title), ("summary", summary)]:
        ET.SubElement(component, tag).text = text
    ET.SubElement(component, "launchable", {"type": "desktop-id"}).text = app_id + ".desktop"
    ET.SubElement(ET.SubElement(component, "provides"), "mediatype").text = "x-scheme-handler/" + protocol
    ET.SubElement(component, "url", {"type": "homepage"}).text = provenance["source_url"]
    ET.SubElement(ET.SubElement(component, "description"), "p").text = (
        "A private Flatpak wrapper around the vendor's Linux ARM64 release. "
        "This wrapper is maintained locally and is not a vendor-supported Flatpak.")
    if "release_date" in provenance:
        ET.SubElement(ET.SubElement(component, "releases"), "release", {
            "version": provenance["version"], "date": provenance["release_date"]})
    write_text(files / "share/metainfo" / (app_id + ".metainfo.xml"), ET.tostring(component, encoding="unicode") + "\n")
    compose_appstream(files, app_id, env)
    permissions = ["--share=ipc", "--share=network", "--socket=wayland", "--socket=fallback-x11",
                   "--socket=pulseaudio", "--device=dri", "--talk-name=org.freedesktop.secrets"]
    if key == "antigravity":
        permissions.append("--filesystem=home")
    else:
        permissions.append("--filesystem=xdg-download")
    run([flatpak, "build-finish", "--command=" + command, "--require-version=1.18.0", *permissions, str(build)], env)
    run([flatpak, "build-export", "--arch=" + ARCH, "--no-summary-index", "--update-appstream",
         str(output / "private-repo"), str(build), "stable"], env)


def make_seed(installation, archive):
    def target_owner(info):
        info.uid = info.gid = 1000
        info.uname = info.gname = "dippo"
        info.mtime = 0
        info.pax_headers = {}
        return info

    # Archive only the Flatpak subtree, never parent /home ownership or accounts.
    # The image assembler must create /home/dippo with uid/gid 1000 separately.
    zstd = shutil.which("zstd")
    if zstd is None:
        raise PreparationError("Host zstd is required to create the seed archive")
    with archive.open("xb") as compressed:
        with subprocess.Popen([zstd, "-T0", "-3", "-c"], stdin=subprocess.PIPE, stdout=compressed) as compressor:
            try:
                with tarfile.open(fileobj=compressor.stdin, mode="w|", dereference=False) as target:
                    target.add(installation, arcname=TARGET_PREFIX, filter=target_owner)
            finally:
                compressor.stdin.close()
            if compressor.wait() != 0:
                raise PreparationError("zstd compression failed")


def prepare(args, payloads, provenances, output):
    flatpak = shutil.which(args.flatpak)
    if flatpak is None:
        raise PreparationError("Flatpak CLI not found; use the project environment or --flatpak")
    if shutil.which("zstd") is None:
        raise PreparationError("Host zstd is required to create the seed archive")
    if shutil.which("appstreamcli") is None:
        raise PreparationError("Native appstreamcli with compose support is required")
    host_version = subprocess.run([flatpak, "--version"], check=True, capture_output=True, text=True).stdout.strip()
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", host_version)
    if match is None or tuple(map(int, match.groups())) < (1, 18, 0):
        raise PreparationError("Flatpak 1.18 or newer is required")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = environment(output)
    for name in ("tmp", "site-config", "empty-system", "user-config", "user-data", "cache"):
        (output / name).mkdir(mode=0o700)
    installation = output / "flatpak"
    if args.reuse_installation is not None:
        clone_installation(args.reuse_installation, installation, env)
    repo_file = Path(__file__).resolve().parents[1] / "modules/assets/flathub.flatpakrepo"
    run([flatpak, "remote-add", "--user", "--if-not-exists", "flathub", str(repo_file)], env)
    run([flatpak, "install", "--user", "--arch=" + ARCH, "--noninteractive", "-y", "--no-auto-pin", "flathub",
         "app/" + BASE + "/" + ARCH + "/" + args.runtime_branch,
         "runtime/" + SDK + "/" + ARCH + "/" + args.runtime_branch, LIBREWOLF], env)
    # install has no --commit option. Downgrade/verify after the initial pull;
    # normal dependency resolution pulls any runtime required by the pinned app.
    run([flatpak, "update", "--user", "--arch=" + ARCH, "--noninteractive", "-y",
         "--commit=" + LIBREWOLF_COMMIT, LIBREWOLF], env)
    actual = run([flatpak, "info", "--user", "--show-commit", LIBREWOLF], env, capture=True).strip()
    if actual != LIBREWOLF_COMMIT:
        raise PreparationError("Installed LibreWolf does not match the selected ARM64 commit")
    for key in APP_IDS:
        package_app(flatpak, output, env, key, payloads[key], provenances[key], args.runtime_branch)
    # A full summary is tiny for two apps and lets the x86 staging client find
    # ARM AppStream refs without selecting a host-architecture subsummary.
    run([flatpak, "build-update-repo", "--no-summary-index", str(output / "private-repo")], env)
    branches = json.loads(run([flatpak, "repo", "--branches", "--json", str(output / "private-repo")], env, capture=True))
    appstream_refs = {"appstream/" + ARCH, "appstream2/" + ARCH}
    if not appstream_refs.issubset({entry["ref"] for entry in branches}):
        raise PreparationError("Private repository lacks the generated ARM64 AppStream refs")
    run([flatpak, "remote-add", "--user", "--no-gpg-verify", "personal-local", (output / "private-repo").as_uri()], env)
    run([flatpak, "install", "--user", "--arch=" + ARCH, "--noninteractive", "-y", "personal-local",
         *["app/" + app_id + "/" + ARCH + "/stable" for app_id in APP_IDS.values()]], env)
    run([flatpak, "update", "--user", "--arch=" + ARCH, "--appstream", "--noninteractive", "-y", "personal-local"], env)
    cached_catalog = installation / "appstream/personal-local" / ARCH / "active/appstream.xml"
    if not cached_catalog.is_file():
        raise PreparationError("Private AppStream metadata was not cached")
    cached_ids = {component.findtext("id") for component in ET.parse(cached_catalog).getroot().findall("component")}
    if not set(APP_IDS.values()).issubset(cached_ids):
        raise PreparationError("Cached private AppStream metadata lacks a selected application")
    # Keep installed AppStream metadata for Discover, but do not retain a host
    # file:// URL or promise an update service for these personal wrappers.
    run([flatpak, "remote-modify", "--user", "--disable",
         "--url=file:///var/empty/sheng-personal-flatpaks", "personal-local"], env)
    run([flatpak, "uninstall", "--user", "--noninteractive", "-y",
         "app/" + BASE + "/" + ARCH + "/" + args.runtime_branch,
         "runtime/" + SDK + "/" + ARCH + "/" + args.runtime_branch], env)
    run([flatpak, "uninstall", "--user", "--unused", "--noninteractive", "-y"], env)
    refs = run([flatpak, "list", "--user", "--columns=ref,active,origin"], env, capture=True)
    rows = [line.split("\t") for line in refs.splitlines() if line.strip()]
    # Flatpak's list/ref column omits the app/ or runtime/ prefix.
    expected_apps = {LIBREWOLF.removeprefix("app/"), *[item + "/" + ARCH + "/stable" for item in APP_IDS.values()]}
    found_apps = set(run([flatpak, "list", "--user", "--app", "--columns=ref"], env, capture=True).splitlines())
    for row in rows:
        parts = row[0].split("/")
        if len(parts) != 3 or parts[1] != ARCH:
            raise PreparationError("Seed contains an unexpected architecture/ref: " + row[0])
    if found_apps != expected_apps:
        raise PreparationError("Seed application list differs from the three selected apps")
    for app_ref in sorted(expected_apps):
        runtime = run([flatpak, "info", "--user", "--show-runtime", app_ref], env, capture=True).strip()
        run([flatpak, "info", "--user", "runtime/" + runtime], env, capture=True)
    for app_id in [LIBREWOLF.split("/")[1], *APP_IDS.values()]:
        desktop = installation / "app" / app_id / ARCH / "stable/active/export/share/applications" / (app_id + ".desktop")
        if not desktop.is_file():
            raise PreparationError("Installed application lacks its exported desktop entry: " + app_id)
        exec_lines = []
        for line in desktop.read_text(encoding="utf-8").splitlines():
            if line.startswith("Exec="):
                exec_lines.append(line)
                if not line.startswith("Exec=" + TARGET_FLATPAK + " "):
                    raise PreparationError("Exported launcher has an unexpected Flatpak path: " + str(desktop))
        if not exec_lines:
            raise PreparationError("Exported desktop entry lacks Exec: " + app_id)
    write_text(output / "installed-refs.tsv", refs)
    write_text(output / "provenance.json", json.dumps({
        "format": 1, "target": {"user": "dippo", "uid": 1000, "gid": 100, "architecture": ARCH},
        "archive_owner": {"uid": 1000, "gid": 1000},
        "prepared_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "flatpak_cli": host_version, "runtime_branch": args.runtime_branch,
        "librewolf": {"ref": LIBREWOLF, "commit": LIBREWOLF_COMMIT},
        "payloads": {key: {**provenances[key], **payloads[key][2]} for key in APP_IDS},
        "installed_refs": rows,
        "verified": "Metadata, ELF architecture and seed contents only; ARM applications were not executed.",
    }, indent=2) + "\n", 0o600)
    archive = output / "personal-flatpaks-home.tar.zst"
    make_seed(installation, archive)
    write_text(output / "seed-sha256.txt", sha256_file(archive) + "  " + archive.name + "\n", 0o600)
    print("Prepared private seed: " + str(archive))
    print("ARM desktop startup, renderer isolation, permissions and Discover removal remain to be tested.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in APP_IDS:
        parser.add_argument("--" + key + "-dir", type=Path, required=True)
        parser.add_argument("--" + key + "-executable", required=True, help="Relative path to the real AArch64 Electron ELF, not a shell launcher")
        parser.add_argument("--" + key + "-archive", type=Path, help="Optional original release archive for private hash/provenance checking")
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="New private directory outside this Git checkout")
    parser.add_argument("--flatpak", default="flatpak")
    parser.add_argument("--runtime-branch", default=RUNTIME_BRANCH)
    parser.add_argument("--reuse-installation", type=Path,
                        help="Clone an existing private Flatpak tree into the new output before normal dependency/pin checks")
    parser.add_argument("--prepare", action="store_true", help="Download ARM runtimes/apps and create the private seed; otherwise validate only")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"\d{2}\.\d{2}", args.runtime_branch):
            raise PreparationError("Invalid runtime branch; expected YY.MM")
        repository = Path(__file__).resolve().parents[1]
        output = args.output_dir.resolve()
        if is_within(output, repository) or "/nix/store/" in str(output) + "/":
            raise PreparationError("Output must be outside the Git checkout and outside the Nix store")
        if output.exists():
            raise PreparationError("Output directory already exists; choose a new private directory")
        if args.reuse_installation is not None:
            args.reuse_installation = validate_reuse_installation(args.reuse_installation, output, repository)
        payloads, provenances = {}, {}
        private_inputs = [args.provenance, args.chatgpt_dir, args.antigravity_dir,
                          args.chatgpt_archive, args.antigravity_archive]
        for private_path in private_inputs:
            if private_path is not None and is_within(private_path.resolve(), repository):
                raise PreparationError("Proprietary payloads and private provenance must be outside this Git checkout")
        for key in APP_IDS:
            payloads[key] = validate_tree(getattr(args, key + "_dir"), getattr(args, key + "_executable"))
            if is_within(output, payloads[key][0]) or is_within(payloads[key][0], output):
                raise PreparationError("Output and payload directories must not overlap")
            provenances[key] = validate_provenance(args.provenance, key, getattr(args, key + "_archive"))
            provenances[key]["url_protocol"] = app_protocol(key, payloads[key][0])
        if not args.prepare:
            print("Local ARM64 payload/provenance validation passed. No files were written or downloaded.")
            retained_count = sum(len(payload[2]["foreign_arch_optional_prebuilds_as_data"]) for payload in payloads.values())
            print(f"Retained {retained_count} audited non-target optional prebuilds as vendor data.")
            print("With --prepare: install signed Flathub ARM64 dependencies, wrap both local apps with Zypak,")
            print("and create a private Flatpak seed for /home/dippo. Output: " + str(output))
            if args.reuse_installation is not None:
                print("Existing dependency data will be cloned from: " + str(args.reuse_installation))
            return 0
        prepare(args, payloads, provenances, output)
        return 0
    except (PreparationError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Preparation failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
