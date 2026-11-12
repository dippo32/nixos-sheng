#!/usr/bin/env python3
"""Check the shipped remote with Flatpak in temporary state and no network."""
import os
from pathlib import Path
import subprocess
import tempfile

descriptor = Path(__file__).resolve().parents[1] / "modules/assets/flathub.flatpakrepo"
with tempfile.TemporaryDirectory(prefix="sheng-flatpak-offline-") as temporary:
    base = Path(temporary)
    remotes = base / "config/remotes.d"
    remotes.mkdir(parents=True)
    (remotes / descriptor.name).write_bytes(descriptor.read_bytes())
    environment = dict(os.environ)
    environment.update(
        FLATPAK_SYSTEM_DIR=str(base / "installation"),
        FLATPAK_SYSTEM_CACHE_DIR=str(base / "cache"),
        FLATPAK_CONFIG_DIR=str(base / "config"),
    )
    result = subprocess.run(
        ["unshare", "-Urn", "flatpak", "remotes", "--system", "--columns=name,url"],
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    assert result.stdout.strip() == "flathub\thttps://dl.flathub.org/repo/", result.stdout
    print("Flathub is preconfigured offline; host Flatpak state was untouched.")
