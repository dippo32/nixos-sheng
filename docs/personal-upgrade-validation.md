# Personal upgrade candidate

This candidate retains the single-system `userdata` layout and extlinux boot
while incorporating the upstream Linux 7.3.4 source/configuration and ALSA card
name alias. Keyboard and pen accessory helpers remain disabled in the personal
profile; shared touch input remains enabled.

LibreWolf is a native ARM64 package. The base image retains its upstream
privacy preferences. On the tested tablet, the owner subsequently chose a
user-level override to retain cookies and site data when the browser closes.
ChatGPT Desktop and Google Antigravity App 2.32.0 are separate native profile
outputs (`chatgpt-native` and `antigravity-native`). Antigravity App uses the
`antigravity-hub` wrapper and is distinct from Antigravity IDE and CLI.
Maliit is available as an alternative input method; the default login keyboard
is retained until a device test verifies the replacement.

## Build evidence

- GUI application configuration and native ARM64 builds passed in
  [run 43569038143](https://github.com/dippo32/nixos-sheng/actions/runs/43569038143).
  This does not establish successful login or UI/device integration.
- Charger userspace, systemd unit verification and the optional boot image
  passed [run 43569205450](https://github.com/dippo32/nixos-sheng/actions/runs/43569205450).
  The normal boot derivation remained equal to the baseline.
- The final image build passed in
  [run 43570628913](https://github.com/dippo32/nixos-sheng/actions/runs/43570628913)
  from source commit `8a1a79c`. Its ARM64 job took 19 minutes 17 seconds.
  The flashable artifact ID is `14105051020`; its GitHub artifact ZIP digest is
  `sha256:ac2b6582fd93d0f4196a8ac636d6dc263a9fa1ccbe614061ec8a0833b2f91a32`.
  This digest identifies the downloaded ZIP, not the image file inside it.
- That run verified the kernel closure, output manifest and kernel-path
  checksums, then restored all matching outputs from
  [run 43568366425](https://github.com/dippo32/nixos-sheng/actions/runs/43568366425).
  The subsequent kernel build and export step completed in three seconds.
  The final run also compiled the FastRPC 64-bit log-format fix on ARM64.
- The static filesystem tools passed
  [run 43571313139](https://github.com/dippo32/nixos-sheng/actions/runs/43571313139).
  The built e2fsprogs version is 1.47.4; the version and SHA-256 of the copy
  checked in TWRP matched the built tool.

## Device restore evidence

The 2026-11-14 installation initially exposed incomplete data after fastboot
reported success. A recovery rewrite passed full expanded-image readback and
offline filesystem checks before and after growing the existing partition; see
[rootfs flash verification](rootfs-flash-verification.md) for the details and
limits of that evidence. NixOS subsequently booted the expected 7.3.4 kernel,
and the running root filesystem reported 229 GiB total. ChatGPT Desktop and
Antigravity App were installed in the user's native profile and the user
confirmed that both windows opened; their sign-in and other integration remain
to be tested.

The owner selected retention of cookies and site data for all sites. The local
LibreWolf override changes only `privacy.clearOnShutdown_v2.cookiesAndStorage`
to `false` as a default; the source image itself is unchanged. The owner
confirmed that one tested website stayed signed in after closing and reopening
LibreWolf. Other sites, expiry policies, and upgrades still need their own tests.
Maliit was also tried on the logged-in desktop. A user-specific landscape
height of 0.31 of the screen was reported comfortable as a temporary layout;
the requested split layout was then tested with KBoard. The owner confirmed
split keys in landscape, joined keys in portrait, typing in landscape, and
comfortable key height. Key sounds were disabled at the owner's request.
KBoard's login-greeter and lock-screen behavior still require separate tests;
the existing login keyboard and Maliit have not been removed.

Builds, the restore and GUI launch checks do not establish all hardware
functionality. The fingerprint
driver tests were skipped due to missing introspection dependencies; the
assembling test also lacked dependencies. Runtime validation is still required.

## Charger experiment

The normal U-Boot output retains its existing charger-insert waiting behavior.
The separate `u-boot-personal-charger-test` output can pass a charger-boot device
tree marker to a patched Linux charger service. It provides a Power-button
escape window. This output is for temporary boot testing before any permanent
deployment.

The patched userspace retries missing input discovery, falls back to normal boot
when early detection fails, restores the backlight before normal boot, and asks
systemd to perform shutdown after confirmed unplug. Mock tests cannot establish
actual charging, power consumption, temperature or key/firmware behavior.

On 2026-11-14 the candidate booted normally from slot B and was tested after
power-off and charger insertion. The owner observed the charging screen, a
battery increase from 96% to 97%, a short Power press blanking and restoring
the screen, and a long press continuing into NixOS. The service journal
corroborated the long-press exit. MiPPS authentication was skipped after a VDM
timeout; this test does not establish maximum charging power. The screen did
not blank automatically in this generation.

An automatic screen timeout and authentication-error handling were built and
passed 16 mocked tests in [run 43580952938](https://github.com/dippo32/nixos-sheng/actions/runs/43580952938).
The candidate generation was registered and tested on the tablet. The owner
confirmed that the screen blanked automatically on charger insertion, and that
a short Power press displayed it again followed by another automatic blank.
Synchronous charger authentication can delay the timer and Power handling while
it runs.

After continuing to NixOS from the charger screen, the accelerometer was not
detected and automatic rotation was unavailable. The sensor daemon had started
only after the long-running charger service released `basic.target`; QMI service
400 was absent. Restarting only the userspace sensor services did not recover
it. After a normal restart, the accelerometer and automatic rotation returned,
and the owner confirmed correct display and touch rotation. An early-sensor
startup candidate is being investigated; causation and a permanent fix still
need testing through another charger-to-desktop transition.

## Device validation still required

1. Verify normal reboot and the recovery path after account provisioning and
   first desktop login. Do not resize the image at build time or rewrite the
   partition table to fix a smaller filesystem.
2. Verify more native-browser sites and both desktop applications beyond opening
   windows, including sign-in, link handling and persistence.
3. Test on-screen keyboard sizing, automatic display/hiding, rotation and lock
   screen; retain an alternative control path.
4. Test charger unplug behavior, authentication, charging power, and the
   pending fix for rotation after charger boot; measure suspend separately.
5. Compare camera sensors, focus controls, selected resolution and color in the
   same conditions before changing calibration or claiming improved quality.

EFI remains a separate experiment. Upstream temporary boot evidence is useful,
but it does not establish a permanent ESP layout or a benefit for this profile.
