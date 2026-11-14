# Root filesystem flash verification

An `OKAY` response from fastboot confirms the command completed; it does not
prove that all expanded image bytes were written correctly. Verify the result
before mounting or booting it. The checks below apply to the actual selected
root partition: `userdata` for the single-system image or `linux` for the
separate dual-system image. Do not substitute one for the other.

## Observed single-system failure

On 2026-11-14, the personal image from source `8a1a79c` and
[build 43570628913](https://github.com/dippo32/nixos-sheng/actions/runs/43570628913)
passed its artifact checksums and sparse structure checks. The device's
`userdata` had previously been erased. A Windows fastboot invocation with
`-S 256M flash userdata` reported success for all 38 sparse transfers. A
subsequent offline `e2fsck -f -n` reported a corrupt journal; `debugfs` also
reported a block bitmap checksum mismatch. Sampled image blocks at and beyond
block 2,621,440 were zero on the device even where the verified sparse image
contained data. This observation does not establish the cause or mean every
fastboot transfer fails. The invocation did not issue a fresh fastboot erase
immediately before flashing, so it does not establish whether that would have
changed this result.

The same image was expanded and written in checked chunks from recovery. Its
entire **24,332,206,080-byte expanded range** was then read back on the device:
the SHA-256 matched the locally expanded image
`800f637b56b092586aa74164ab7b4a09932f81a8bc9090d09e6ac1bf7a4f7dc8`.
Offline e2fsck was clean before and after expansion to the existing partition;
the resulting system booted. This is evidence for that transfer, image, and
device, not a guarantee for other combinations.

## Verification procedure

1. Verify the downloaded artifact and its included image checksums. Confirm the
   exact source revision, selected image, physical device, root PARTLABEL and
   partition size. Keep a working recovery path and protect any data that must
   be retained. Do not rewrite the partition table to grow the filesystem.
2. Expand the **verified** Android sparse image to a raw file with a compatible
   tool, such as `simg2img`, on a host with sufficient free space. Record its
   exact byte length and SHA-256. An Android sparse file's length or SHA-256 is
   not the length or SHA-256 of the expanded data.
3. Before first mount or resize, identify the selected partition in recovery and
   ensure it is unmounted, not in use as swap, and has no active holders. Read
   back and hash **exactly the expanded raw image length** from that partition,
   then compare with the raw host image. Hash the data on the device rather
   than piping raw partition data through a terminal. Stop if size or hash
   differs; fastboot success and filesystem metadata checks alone are not a
   complete content verification.
4. Run a compatible, recent `e2fsck -f -n` on the unmounted partition and
   inspect the result. A report of journal, bitmap, or other corruption requires
   investigation; do not treat repairing only the journal as proof that the
   remaining image is intact. e2fsprogs 1.47.4 was used for the incident above;
   older recovery tools may not understand image features such as `orphan_file`.
5. Once the image and filesystem pass, grow the filesystem against the checked
   physical partition if needed, run another offline check, and then proceed
   with private account provisioning and boot. Record the actual results.

## Recovery transfer cautions

On the Windows host used above, sending arbitrary binary image bytes to
`adb shell` stdin stopped at byte `0x1a`; `-T` did not fix this. ADB sync
`push` to ordinary temporary files was verified byte-for-byte, and the checked
chunks were written to the already identified unmounted partition with `dd`
and `fsync`. Whole-range readback and offline e2fsck were still required.

Do not `adb push` an image directly to a `by-name` symlink: a test using a
temporary symlink replaced the symlink with a regular file. A test against a
temporary block node preserved its type but changed its mode. Neither test is a
general guarantee for real block devices or other ADB versions. The local
incident helper was device-specific; it is not a supported generic installer.
Any reusable helper needs independent target, mount, size, data-integrity,
interruption and cleanup guards and meaningful tests before use.
