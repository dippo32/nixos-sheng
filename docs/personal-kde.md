# Personal KDE single-boot image

Target: Xiaomi Pad 6S Pro 12.4 (`sheng`), Linux-only root on `userdata`.
The locked Nixpkgs/kernel/firmware inputs are retained. Standard CLI, KDE,
GNOME and dual-boot profiles keep their defaults; personal changes are separate.

## Personal desktop and identity

- Login account `dippo`, UID 1000, display name **Dippo Shelan**.
- GUI/TTY autologin is disabled; root's default password is locked.
- Login uses `/var/lib/sheng-private/login.hash`, injected locally after CI.
  Password/PIN content and its hash must never enter Git, Nix expressions,
  the Nix store or public Actions artifacts. `users.mutableUsers=false` makes
  that private file authoritative at activation; change it to change the PIN.
- Plasma Keyboard is selected for SDDM and the user's Wayland session.
- Maliit Keyboard is available as an optional desktop alternative; select it in
  Plasma's Virtual Keyboard settings after login. Plasma Keyboard remains the
  default and supplies the separate login screen. Maliit build and device
  behavior, including lock-screen input and recovery, still need verification.
- Firefox is omitted. Native LibreWolf is included as the default
  HTTP/HTTPS/HTML browser, using the upstream ARM64 binary via Nixpkgs. It does
  not require Flatpak or the legacy private seed. LibreWolf privacy defaults
  remain unchanged; session persistence needs a real-device check.
- The preferred ChatGPT and Antigravity IDE packages are native, optional user
  profile installations, not part of the system image. See [native applications](native-apps.md).
  They have not been built or tested on the tablet.
- The legacy seed contains per-user Flatpaks for LibreWolf, ChatGPT and
  Antigravity IDE; the latter two are non-vendor wrappers. If the seed is
  supplied, a first-boot service extracts it as `dippo`, validates the refs,
  and deletes it only after success. See [removable applications](removable-apps.md).

## Boot, rotation and responsiveness

`u-boot-personal` starts `bootlinux` directly without the generation menu.
The internal current NixOS profile still exists. After boot, a guarded timer
removes older system generation links only when booted/current/profile targets
match. It does not prune user profiles or a pending boot selection; normal GC
runs separately each week. Shell checks and Nix profile deletion are not one
atomic transaction with an unrelated concurrent rebuild. Nix protects the selected
profile and runtime GC roots; this is not a full health check or rollback guarantee.

The personal Wayland session sets the active internal panel's auto-rotation
policy to Always. It discovers the output, waits boundedly for SSC availability,
changes no fixed orientation/mount matrix, and verifies the result. On the owner’s
installed candidate, the sensor changed when held upright, and changing DSI-1
from InTabletMode to Always was followed by user-confirmed display rotation.
The new account's startup helper still needs device validation.

ZSTD zram uses at most 25% of RAM as uncompressed swap capacity, capped at 2 GiB.
Baloo indexes names/metadata without document-content extraction. KDE animation
duration defaults to 0.75 (user-overridable). The personal kernel omits extra
bring-up display dumps/reads; shared touch-log and serial-buffer fixes remain.
CPU/GPU governors, frequency limits and thermal protection are unchanged. No
FPS, temperature or battery-life improvement has been measured.

Keyboard/pen accessory helpers are omitted; shared touchscreen, audio, sensors,
fingerprint, charging and Bluetooth support remain. Low-level pen code shared
with the touchscreen is retained.

## Power and remaining limits

The personal kernel selects `s2idle` and includes manual PM diagnostics and
`sheng-power-report`; no trace/suspend test is run automatically. The legacy USB
serial gadget/getty are disabled through `g_serial.enable=0` on normal extlinux
boot. The U-Boot rescue path has separate arguments and may re-enable serial.

Two MiPPS helper error paths are corrected: current-source PDO validation before
trusting cached authentication, and online-debounce recovery after enqueue
failure. Nine mocked regressions verify these paths, not charging power or
compatibility. The charging stack is otherwise retained from the installed candidate.

**The user chose to retain the existing charging settings. No 40 W cap is applied.** The locked Xiaomi USB
power-supply descriptor has no writable input-power/current setter. A future
kernel RPC setter needs firmware ACK/error/readback validation and does not by
itself establish a global watt cap across voltage negotiation or off-mode.
Do not bypass thermal controls or pretend an unsupported sysfs write is a cap.

The U-Boot charger-insert screen waits for Power with Linux stopped. Its own
source says this is not low-power charging. The packaged Linux charger program
is not enabled by adding an unverified boot flag. Low-power off-mode charging,
actual charger watts, temperature, sleep/wake and overnight standby remain
unverified. The [existing DWC3 freeze](power-validation.md) is not repaired by
selecting s2idle, and PR #7 is not incorporated because its freeze/requeue handling
is incomplete. Hibernate is not configured.

## Public build and private assembly

Configuration: `nixosConfigurations.sheng-kde-personal`.
Image: `packages.aarch64-linux.nixos-kde-personal`.
Boot image: `packages.aarch64-linux.u-boot-personal`.

The personal workflow builds on native ARM64, checks account/desktop/retention/
rotation settings, charger regressions, real kernel configuration and boot/image
formats. Exact-path/checksummed kernel artifacts can be restored from the personal
branch or its earlier successful builds. Build success is separate from boot,
login, application and peripheral tests.

The public artifact is an **unprovisioned base**. Its account is locked until
private assembly injects the hash file. It contains no private PIN or proprietary
application seed. A personal-only 8 GiB reserve preserves the initial mkfs-created
filesystem size, skips the locked builder's shrink/grow commands, and checks
actual free space. No fixed-size resize is used.

For the legacy Flatpak route, prepare a private seed with
`scripts/prepare-personal-flatpaks.py`, then use `scripts/provision-private-image.py`
with the base image, a 0600 hash file and a 0600 seed in a 0700 directory.
That script currently requires both files. It injects them with debugfs,
verifies readback, owner/mode and free space, runs bounded filesystem checks,
and creates a new checksummed sparse image. It never mounts, flashes or resizes
the filesystem. Keep the resulting image and provenance local/private.

The native route does not need the Flatpak seed, but the account still needs a
private hash file before first activation. An account-only provisioning route
must be validated separately; the existing image assembler cannot omit the seed.

Before flashing, verify model/unlock/current slot, exact target partition and
expanded sparse size, hashes and physical fastboot recovery. Installation erases
`userdata`; it does not require erasing firmware, recovery or dtbo. Boot and
application tests need the actual tablet. Check the new login and screen keyboard,
Discover installation/removal, rotation/touch, charging, temperature and sleep.
Use [peripheral validation](peripheral-validation.md) for other hardware claims.
