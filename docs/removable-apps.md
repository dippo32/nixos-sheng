# Private applications removable in Discover

The personal image can carry LibreWolf and local Flatpak wrappers around official
ChatGPT and Antigravity Linux ARM64 releases. The applications belong to the
mutable user installation at `/home/dippo/.local/share/flatpak`, owned by uid 1000
and the account's primary group (gid 100). They must not be added to `environment.systemPackages`, linked from
`/nix/store`, or installed again by a login/rebuild service. Discover can then
uninstall them normally; an ordinary NixOS rebuild does not restore them.

The wrappers use personal IDs `io.github.dippo32.ChatGPT` and
`io.github.dippo32.AntigravityIDE`. They are local packaging, not vendor-supported
Flatpaks. Their proprietary payloads, private provenance and final image/seed
must stay outside Git and public GitHub Actions artifacts. Public CI should build
the OS without these payloads; private assembly is a separate operation.

## Inputs and preparation

Run `scripts/prepare-personal-flatpaks.py` on the development host. The default
mode checks local inputs without writing files, downloading dependencies or
installing applications. `--prepare` explicitly enables downloads and private
packaging. Neither mode executes an ARM64 application, connects to the tablet,
changes the workstation's existing Flatpak installation, or activates NixOS.

Provide already unpacked official releases. For a Debian package, extract its
data archive into a private directory first. Point `--*-dir` at the application's
complete runtime directory and `--*-executable` at the actual Electron ELF relative
to that directory, rather than a shell launcher. The script rejects non-ARM64
mandatory ELF files, escaping/dangling symlinks and special files; it never extracts untrusted archive
paths itself. Upstream Electron payloads are copied as data, including their
resources and bundled native modules.

The official ChatGPT payload also carries alternate-platform/architecture Node
addon prebuilds. A finite exception list retains the known non-target `node-hid`
and serialport prebuilds as vendor data. Each exception requires its actual Linux
ARM64 counterpart and the exact previously audited ASAR loader sources; the
bundled loaders select the current platform/architecture rather than loading
every prebuild. The private manifest records each exception and loader hash.
No vendor files are deleted or modified, and the main executable and every
other mandatory ELF remain subject to the strict ARM64 check. A changed loader,
missing target counterpart or newly encountered foreign ELF requires a fresh
audit rather than a broad architecture exemption.

Use the project's ignored parent `artifacts/private-image/` directory for inputs
and outputs. Supply a private provenance JSON file with this shape, filling in
the actual versions and public official download URLs. Record the date on which
the download was observed separately from a vendor release date:

```json
{
  "chatgpt": {
    "version": "RELEASE_VERSION",
    "observed_download_date": "2026-11-13",
    "source_url": "https://persistent.oaistatic.com/codex-app-prod/linux/deb/latest/chatgpt_arm64.deb"
  },
  "antigravity": {
    "version": "RELEASE_VERSION",
    "observed_download_date": "2026-11-13",
    "source_url": "https://OFFICIAL_GOOGLE_DOWNLOAD_HOST/PINNED_ARM64_RELEASE"
  }
}
```

Only known official OpenAI/Google domain families are accepted. This checks URL
provenance, not a vendor signature. Optional `archive_sha256` entries require
matching `--chatgpt-archive`/`--antigravity-archive` paths; without supplied expected
hashes, passing those paths still records the archive's SHA256 privately. The
script also records hashes of the exact unpacked payload trees. An optional
`release_date` is accepted only when the vendor date is actually known; no
AppStream release date is invented when it is absent. Never put account
passwords, password hashes, PINs, login tokens or signed download URLs in this file.

Example from the checkout, with paths adjusted to the actual private inputs:

```sh
python3 scripts/prepare-personal-flatpaks.py \
  --chatgpt-dir ../artifacts/private-image/chatgpt-payload \
  --chatgpt-executable chatgpt \
  --chatgpt-tss2-bundle ../artifacts/private-image/dependencies/tss2-4.1.3-1.2 \
  --antigravity-dir ../artifacts/private-image/antigravity-payload \
  --antigravity-executable antigravity \
  --provenance ../artifacts/private-image/releases.json \
  --output-dir ../artifacts/private-image/apps-seed-01
```

Add `--prepare` only when ready to perform private packaging. The output must be
a new directory outside this Git checkout and outside `/nix/store`; failed
attempts retain their private output for inspection. Flatpak 1.18 or newer is
required; the locked nixpkgs package and current workstation CLI are 1.18.4.
To reuse dependencies after a failed attempt, add
`--reuse-installation ../artifacts/private-image/flatpaks-01/flatpak` and choose a
new output directory. The helper checks the existing `repo/config`, then clones
the installation using `cp -a --reflink=auto`; it never runs Flatpak against the
original. Reflinks use copy-on-write and do not share mutable repository files.
The source must be outside the checkout/Nix store and must not overlap the new
output. Normal dependency installation, commit selection and final checks still
run against the new copy. Existing outputs are not deleted.
The host `zstd` compressor and native `appstreamcli compose` are also required
(the actual host composer was tested at version 1.2.2). Downloads can be several gigabytes
because the SDK/base and runtime are fetched.
The SDK and Electron base application are removed from the final installation
after their contents have been used for packaging.

ChatGPT's checked official Debian control declares TSS2 esys, mu and device
libraries, which are absent from Freedesktop26.08. Its remote-control device-key
addon loads them lazily; a successful basic launch would not exercise that path.
The required `--chatgpt-tss2-bundle` contains four original Debian trixie ARM64
packages at version4.1.3-1.2: `libtss2-esys-3.0.2-0t64`,
`libtss2-mu-4.0.1-0t64`, `libtss2-sys1t64`, and `libtss2-tcti-device0t64`.
`sys` is the recursive ELF dependency of `esys`. Obtain them from the official
Debian `pool/main/t/tpm2-tss/` directory; the exact archive filenames and SHA256
values are pinned in the helper, using each package's official download page
(for example [esys ARM64](https://packages.debian.org/trixie/arm64/libtss2-esys-3.0.2-0t64/download)).

The helper checks all four original archives before reading their data as
archives, extracts only the finite TSS2 library/alias paths and package copyright
files, and installs them under `/app/lib` and `/app/share/licenses/tss2`.
It does not run Debian maintainer scripts, change the vendor payload, or copy
arbitrary host libraries. Private provenance records archive URLs/hashes/versions,
the exact dependency tree hash, and a recursive ARM64 SONAME/GNU-version audit
against the selected Freedesktop runtime. Native `readelf` is required; `ldd` and
ARM execution are not used. The ChatGPT launcher prepends `/app/lib` to the
existing library path for that app. Qt theme shims and unused Android prebuilds
are not made into mandatory runtime dependencies.

This closes the packaged library dependency; it does not establish TPM hardware
availability, permission to access a TPM device, or remote-control enrollment on
the tablet. Those optional features and ordinary app startup still need runtime
testing. No additional device permission is granted by this dependency fix.

The preparation directory contains `personal-flatpaks-home.tar.zst`, its SHA256,
private `provenance.json`, `installed-refs.tsv`, and build/repository working data.
Do not upload this directory through a public artifact workflow. The seed archive
contains only `home/dippo/.local/share/flatpak`; every archive entry has uid/gid
1000. It does not provision an account or modify `/home` ownership. Private image
assembly must create `/home/dippo` separately and keep the seed out of the system's
Nix closure. The intended provisioner opens
`/var/lib/sheng-private/flatpak-seed.tar.zst` as root and passes the open file through
stdin to `tar --zstd --strip-components=5 --no-same-owner`, running as `dippo` in
`/home/dippo/.local/share/flatpak`. This gives extracted files the real account's
uid and primary gid. The archive prefix has exactly five components. The helper
does not assemble, flash or install the OS image or run that provisioner yet.

## Runtime and update behavior

LibreWolf uses Flathub ID `io.gitlab.librewolf-community`. Its initial ARM64 stable
commit is pinned in the script; subsequent updates through Discover remain
available. The checked
[Flathub manifest](https://github.com/flathub/io.gitlab.librewolf-community/blob/a54beea09c0320bb45ae5605a1e3e562c4c53688/io.gitlab.librewolf-community.json)
uses the Freedesktop 26.08 runtime and an explicit official ARM64 archive.
[LibreWolf's own instructions](https://librewolf.net/installation/linux/)
recommend the same Flatpak ID.

Both personal wrappers use
[`org.electronjs.Electron2.BaseApp` 26.08](https://github.com/flathub/org.electronjs.Electron2.BaseApp/blob/branch/26.08/org.electronjs.Electron2.BaseApp.yml)
and the matching Freedesktop Platform. The installed base provides
[`zypak-wrapper`](https://github.com/refi64/zypak), following the
[Flatpak Electron documentation](https://docs.flatpak.org/en/latest/electron.html).
The base's `/app/bin/zypak-wrapper.sh` absolute alias is checked within the target
app tree; it is not resolved against the development host's `/app` directory.
The launcher does not pass `--no-sandbox` or disable Zypak's renderer sandbox.
This packaging choice requires runtime validation; it is not a verified statement
about either vendor's current Electron release. Native helpers outside the
Electron process may need additional compatibility work.

ChatGPT receives network, display/audio, GPU, Secret Service and Downloads access.
Antigravity also receives home-directory access so it can open development
projects. Host command execution is not granted. Its terminal, toolchains,
extensions, authentication callbacks and agent integrations may need further
Flatpak integration before the IDE is fully usable.

The exported desktop entries accept URI arguments through `%U` and register only
the application-specific callback schemes: `codex` for the checked official
ChatGPT release and the exact `urlProtocol` read from Antigravity's `product.json`
(`antigravity-ide` in 2.5.5). This does not grant a D-Bus well-known name and does
not register ChatGPT as an HTTP/HTTPS browser. LibreWolf remains the intended web
browser. Callback handling still needs an actual OAuth/login test.

The local repository is used only during private packaging. Its installed remote
is then disabled and its development-host path is replaced with an inert local
URL. These two personal wrappers do not have a hosted automatic update service;
new official binaries must be repackaged privately. Installed AppStream metadata
is retained for Discover. Flathub stays signed and active for LibreWolf, shared
runtimes and other applications. The seed includes runtime dependencies and
related ARM64 extensions; first launch does not need a package download, but the
online applications still need network access for their services.

Before export, the native host composer generates each application's AppStream
catalog and 64/128-pixel PNG icons offline. Catalogs are placed at
`share/app-info/xmls/APP_ID.xml.gz` and icons under
`share/app-info/icons/flatpak`, matching Flatpak 1.18.4's extractor. The helper
checks that the selected component and icons were actually generated, then
refreshes the private repository's `appstream/aarch64` and `appstream2/aarch64`
refs before importing the remote's metadata. This step never runs an ARM SDK
command or application. The small private repository uses a complete summary
without an architecture index: native x86 Flatpak 1.18.4 metadata staging was
tested to find both ARM64 AppStream refs with that layout. The imported active
catalog is checked for both application IDs, so empty catalog refs do not count
as success.

Exported launchers use `/run/current-system/sw/bin/flatpak`, selected through
`FLATPAK_BINARY` during staging. This avoids embedding the workstation's
`/usr/bin/flatpak` or a host-only Nix store executable path. All staging commands
use isolated `FLATPAK_USER_DIR`, configuration and cache directories.

## Verification boundaries

Preparation checks the selected LibreWolf commit, all installed ref architectures,
the three application IDs, runtime availability and exported launcher paths.
It records the resulting app/runtime commits. Success means the seed was prepared;
it does not prove ARM execution or tablet integration.

Before calling the image ready, verify in a disposable ARM64 desktop or on an
authorized candidate installation: offline launch, login and Secret Service,
Wayland/touch keyboard, file pickers, renderer isolation, IDE tooling, and removal
of each application through Discover. After removal, log out/reboot and perform
an ordinary rebuild to verify the application stays removed. No tablet access or
runtime application test is performed by the helper.
