# Personal KDE single-boot candidate

This image targets a Xiaomi Pad 6S Pro 12.4 (`sheng`) owner who uses touch input
and does not own the Xiaomi magnetic keyboard or Focus Pen. It is based on
`c41bb12373b8979534e650d101d667c3c272af2e`, retains the locked Nixpkgs and kernel,
and adds a separate `sheng-kde-personal` configuration. Existing single/dual,
CLI, KDE and GNOME outputs retain their previous defaults.

## Included changes

- Keyboard authentication, fold-angle and microphone LED helpers are omitted.
- Pen battery/status UI, automatic pairing helper and autostart are omitted.
- THP touchscreen, audio, sensors, fingerprint, charging and general Bluetooth
  support remain enabled. The shared THP input processor is still required for
  the touchscreen; its low-level pen code is not removed from the driver.
- The installed Plasma Keyboard is selected as KWin's default input method
  through `/etc/xdg/kwinrc`, so touch input has a keyboard in the logged-in
  desktop as well as the SDDM greeter. A user's own KWin preferences take
  precedence. Verify text entry on the actual tablet after boot.
- Flatpak is installed and enabled. KDE's existing portal integration and its
  Flatpak-enabled Discover application are retained.
- Flathub is preconfigured system-wide using Flatpak's supported
  `/etc/flatpak/remotes.d/flathub.flatpakrepo` mechanism. Its upstream signing key
  is included. Registering this remote requires no first-boot network access;
  browsing and downloading applications still require a connection.
- The image selects `mem_sleep_default=s2idle` and permits logind to handle a
  short power-key press with suspend. KDE may manage the button while running.
- `trace-cmd` and the read-only `sheng-power-report` command are included for
  device validation. No trace recording or suspend test runs automatically.

Flathub descriptor retrieved from
<https://dl.flathub.org/repo/flathub.flatpakrepo> on 2026-11-12, SHA256
`3371dd250e61d9e1633630073fefda153cd4426f72f4afa0c3373ae2e8fea03a`.
Upstream documents static remotes in the
[Flatpak reference](https://docs.flatpak.org/en/latest/flatpak-command-reference.html#flatpak).

## Build and check

Configuration: `nixosConfigurations.sheng-kde-personal`.
Image package on an ARM64 builder: `packages.aarch64-linux.nixos-kde-personal`.
Root partition: `userdata`. Hostname/rebuild selector: `sheng-kde-personal`.
Desktop username selection is shared with the other desktop images, default
`nixos`.

```sh
# Evaluation only; does not install or activate anything.
nix eval --raw .#nixosConfigurations.sheng-kde-personal.config.networking.hostName

# Native ARM64 builder only, or a configured remote ARM64 builder.
nix build -L .#nixos-kde-personal
```

The `build-personal-kde` workflow runs for pushes to the dedicated
`codex/kde-personal-flatpak-power` branch, or by manual dispatch, and produces
only this candidate and the matching single-system U-Boot image. Its artifact is named
`sheng-kde-personal-flashable`; it includes revision/lock provenance and
`SHA256SUMS`. A successful workflow is build evidence, not a hardware test.
For unchanged kernels, the workflow checks matching kernel artifacts from this
fork and then the upstream repository. It verifies their path and checksum
before importing, and exports a kernel artifact for future builds. If no cache
is accessible, it builds the locked source on ARM64.

Local checks cover the existing desktop images, all four keyboard/pen switch
combinations, the personal profile, and an actual offline Flatpak remote import
in isolated temporary directories. No user's installed Flatpak applications or
remotes are changed by that test.

## Sleep and remaining validation

The existing [power record](power-validation.md) shows short successful s2idle
tests but also DWC3 workqueue freezes after USB removal. Setting s2idle does not
repair that driver issue, and this profile must not be advertised as stable
overnight standby. Hibernate to disk is not configured.

The owner also reports display glitches or a failure to wake after cover-close,
charging errors and excessive warmth in the existing Linux installation. These
reports still require kernel/service logs and sensor readings; this candidate
does not claim those problems have been repaired. Fastboot's battery readings
alone do not diagnose Linux charging or thermal behaviour.

PR #7 was inspected but is not incorporated: it only requeues a suppressed USB
role switch after a normal device resume; a suspend aborted during freezing may
never call that resume path. It also does not serialize all pre-role-switch
runtime-PM operations. No replacement patch is justified without the actual
blocked stack and repeatable device evidence.

Before installation, verify the built artifact and establish a recovery route.
Installation is separate from preparing this configuration. Once device tests
are authorized, collect `sudo sheng-power-report`, repeated sleep/wake with and
without USB, actual sleep duration, screen/touch/audio/network recovery and
longer battery measurements. Keep a known-good generation for rollback.

After boot, check `flatpak remotes --system` and Discover for Flathub. Device
login, screen keyboard, rotation, camera applications and fingerprint integration
still require the [peripheral validation](peripheral-validation.md) checks.
