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
- The kernel cache now exports and validates all kernel outputs. Earlier logs
  showed that exporting only `out` left `dev` and `modules` unavailable and
  caused the image job to rebuild the kernel. Simulation checks are included in
  the personal workflow; a complete fresh-run cache restore still needs evidence.
- Record the final image run, revision, store paths and hashes here after it
  finishes. Builds do not establish hardware functionality.

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
