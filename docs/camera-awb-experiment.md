# Experimental software ISP AWB backport

This branch is an A/B candidate, not a verified camera improvement. It
backports libcamera upstream commit
[`7ebae537183fbacebf8c3ae9b5e97435b468e3de`](https://github.com/libcamera-org/libcamera/commit/7ebae537183fbacebf8c3ae9b5e97435b468e3de)
to the pinned libcamera 0.7.2. Its two statistics hunks are unchanged; AWB
processing is adapted to the older `src/ipa/simple` API. Pixels at or above
95% in any colour channel are excluded from AWB sums, but still counted in
the exposure histogram. With no unsaturated pixels, the old gains are kept.

The overlay selects the patched libcamera globally, so software ISP, its IPA,
GStreamer and PipeWire are rebuilt against the same statistics layout. Although
the public libcamera version remains 0.7.2, the internal shared-memory layout
changes: do not mix IPA modules and libraries from patched and unpatched
builds. A package build and a comparison on the actual tablet remain necessary.

The package build runs the fixture against the actual patched source in its
`postPatch` phase, using the Nix compiler and Python. On an ARM64 Nix host run
`nix build -L --no-link .#libcamera-awb-test`. To run the fixture manually after
applying the patch to a clean 0.7.2 source tree, run:

```sh
python3 tests/softisp-awb-fixtures.py /path/to/patched/libcamera-0.7.2
```

The fixture checks normal, boundary, all-saturated and 10/12-bit samples,
including the unchanged histogram totals. It does not test the complete IPA,
image quality, autofocus or the hardware. Build the NixOS closure on aarch64
and compare matched scenes and lighting against the unpatched image; check
color, exposure and behavior with highlights. Actual sensor calibration and
autofocus may need separate work.

2026-11-14 correction to earlier camera notes: the OV02B1B auxiliary sensor is
monochrome, according to its [manufacturer datasheet](https://sunnywale.com/uploadfile/2021/1020/OV02B1B_Awin.pdf)
and the [sheng driver](https://github.com/ianchb/sm8550-mainline/blob/87ac0f2347eb433933841e6854950dd90e96e6b2/drivers/media/i2c/ov02b1b.c),
which declares `MEDIA_BUS_FMT_Y10_1X10`. Earlier references to a raw Bayer
colour camera should not be taken as confirmed identification. Verify the
actual media graph and reported formats on the running tablet.
