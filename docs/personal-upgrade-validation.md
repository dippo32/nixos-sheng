# Personal upgrade candidate

This candidate retains the single-system `userdata` layout and extlinux boot
while incorporating the upstream Linux 7.3.4 source/configuration and ALSA card
name alias. Keyboard and pen accessory helpers remain disabled in the personal
profile; shared touch input remains enabled.

LibreWolf is a native ARM64 package. Its privacy preferences are unchanged.
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
  The normal boot derivation remained equal to the baseline; the candidate
  boot image has not yet been tested on the tablet.
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
  checked in TWRP matched the built tool. This confirms the tool copy, not a
  completed filesystem restore or resize.

Builds and tool checks do not establish hardware functionality. The fingerprint
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

## Device validation still required

1. Verify the image and physical partition, restore the root filesystem, and
   compare its final filesystem size against the containing partition. Do not
   resize the image at build time or rewrite the partition table to fix a
   smaller filesystem.
2. Provision the account privately and verify login, normal reboot and recovery.
3. Verify native browser and both desktop applications, link handling and login
   persistence. Do not infer cookie behavior solely from the packaging format.
4. Test on-screen keyboard sizing, automatic display/hiding, rotation and lock
   screen; retain an alternative control path.
5. Measure battery charging and suspend on the running system, then test the
   charger boot candidate temporarily, including Power escape and unplug.
6. Compare camera sensors, focus controls, selected resolution and color in the
   same conditions before changing calibration or claiming improved quality.

EFI remains a separate experiment. Upstream temporary boot evidence is useful,
but it does not establish a permanent ESP layout or a benefit for this profile.
