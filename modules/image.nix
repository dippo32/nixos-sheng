# Builds config.system.build.shengImage: a raw ext4 filesystem plus an Android
# sparse copy, to `fastboot flash userdata`. Calls make-ext4-fs.nix directly
# rather than building on sd-image-aarch64.nix, which would partition a whole
# card with a GPT and an ESP; this device has one existing partition.
{
  self,
  config,
  lib,
  pkgs,
  modulesPath,
  ...
}:

let
  cfg = config.sheng.rootfs;

  rawImageBase = pkgs.callPackage "${modulesPath}/../lib/make-ext4-fs.nix" {
    storePaths = [ config.system.build.toplevel ];
    volumeLabel = cfg.partlabel;
    populateImageCommands = ''
      mkdir -p ./files/boot ./files/sbin

      kernelImage=${config.system.build.kernel}/${config.system.boot.loader.kernelFile}
      dtb=${config.hardware.deviceTree.package}/qcom/sm8550-xiaomi-sheng.dtb

      cp "$kernelImage" ./files/boot/Image
      cp "$dtb" ./files/boot/sm8550-xiaomi-sheng.dtb

      ln -sf ${config.system.build.toplevel}/init ./files/sbin/init

      ${config.sheng.boot.installer}/bin/sheng-install-boot \
        -d ./files/boot ${config.system.build.toplevel}

      # A mutable copy, so the device can rebuild without a host.
      mkdir -p ./files/etc/nixos
      cp -r --no-preserve=mode,ownership ${self}/. ./files/etc/nixos/
    ''
    + lib.optionalString (cfg.privateProvisioningReserveMiB > 0) ''
      # Its apparent size contributes to make-ext4-fs's initial size estimate.
      # No private credentials or application payloads are present in CI.
      mkdir -p ./files/var/lib/sheng-private
      truncate -s ${toString cfg.privateProvisioningReserveMiB}M \
        ./files/var/lib/sheng-private/.provisioning-reserve
    '';
  };

  rawImage =
    if cfg.privateProvisioningReserveMiB == 0 then
      rawImageBase
    else
      rawImageBase.overrideAttrs (
        old:
        let
          shrink = "resize2fs -M $img";
          grow = "resize2fs $img $new_size";
          matchesOnce = needle: builtins.length (lib.splitString needle old.buildCommand) == 2;
        in
        # Fail closed if the locked builder changes. Preserve the filesystem
        # created by mkfs, avoiding the shrink/grow cycle and its bitmap issue.
        assert lib.assertMsg (
          matchesOnce shrink && matchesOnce grow
        ) "The locked make-ext4-fs shrink commands changed; review private provisioning reserve handling.";
        {
          buildCommand =
            builtins.replaceStrings
              [ shrink grow ]
              [
                ": # Preserve initial filesystem space for private provisioning"
                ": # No build-time filesystem growth"
              ]
              old.buildCommand
            + ''
              faketime -f '1970-01-01 00:00:01' debugfs -w \
                -R 'rm /var/lib/sheng-private/.provisioning-reserve' "$out"
              e2fsck -fn "$out"
              free_bytes=$(dumpe2fs -h "$out" 2>/dev/null | awk -F: \
                '/^Free blocks:/{free=$2} /^Block size:/{size=$2} END{printf "%.0f",free*size}')
              required_bytes=${toString (cfg.privateProvisioningReserveMiB * 1024 * 1024)}
              if [ "$free_bytes" -lt "$required_bytes" ]; then
                echo "Image has insufficient free space for private provisioning: $free_bytes bytes" >&2
                exit 1
              fi
            '';
        }
      );
in
{
  options.sheng.rootfs = {
    partlabel = lib.mkOption {
      type = lib.types.str;
      default = "userdata";
      description = ''
        PARTLABEL of the existing Android partition this image gets flashed
        onto. The default replaces Android entirely; set it to "linux" for the
        reference project's dual-boot convention.
      '';
    };

    imageSize = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = ''
        Fixed size to grow the image to, or null to leave it auto-sized.

        Leave it null. A fixed size corrupts the filesystem: resize2fs writes
        the block groups it adds with bitmap checksums the kernel rejects,
        while build-time e2fsck reports the image clean, so nothing catches it
        until the device boots and refuses every later resize -- including the
        growfs that would have claimed the rest of the partition. It buys
        nothing either, since img2simg drops the empty blocks anyway.
      '';
    };

    keepRawImage = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Also ship the raw ext4 image next to the Android sparse one, to
        loopback-mount and look inside. Off by default because nothing
        consumes it and it costs imageSize bytes per fetch.
      '';
    };

    privateProvisioningReserveMiB = lib.mkOption {
      type = lib.types.addCheck lib.types.int (n: n >= 0 && n <= 16384);
      default = 0;
      description = ''
        Free space reserved for private local credential/application injection.
        Nonzero values preserve the initial mkfs size instead of shrinking it.
        Public builds contain no private provisioning data.
      '';
    };
  };

  config = {
    assertions = [
      {
        assertion = cfg.privateProvisioningReserveMiB == 0 || cfg.imageSize == null;
        message = "Private provisioning reserve requires automatic image sizing; do not resize the image at build time.";
      }
    ];
    system.build.shengImage =
      pkgs.runCommand "sheng-rootfs-images"
        {
          nativeBuildInputs = [
            pkgs.e2fsprogs
            pkgs.android-tools
          ];
        }
        ''
          mkdir -p "$out"
          img="$TMPDIR/sheng-rootfs.img"

          cp --reflink=auto ${rawImage} "$img"
          chmod +w "$img"

          ${lib.optionalString (cfg.imageSize != null) ''
            # Check BEFORE truncating, which cannot refuse a too-small size.
            e2fsck -fy "$img" || true
            min_blocks="$(resize2fs -P "$img" 2>/dev/null | awk '{ print $NF }')"
            want_blocks=$(( $(numfmt --from=iec ${cfg.imageSize}) / 4096 ))
            if [ "$want_blocks" -lt "$min_blocks" ]; then
              echo "sheng.rootfs.imageSize is ${cfg.imageSize}, but this configuration needs at least" >&2
              echo "$(( (min_blocks * 4096 + 1073741823) / 1073741824 ))G of filesystem to hold it." >&2
              echo "Raise sheng.rootfs.imageSize, or set it to null to auto-size to the contents." >&2
              exit 1
            fi

            echo "Growing image to ${cfg.imageSize}..."
            truncate -s ${cfg.imageSize} "$img"
            resize2fs "$img" ${cfg.imageSize}
          ''}

          # e2fsck exits 1 on the pass that fixes something, so loop rather than
          # swallow that with `|| true` and ship an image it never finished.
          echo "Final filesystem check..."
          clean=0
          for i in 1 2 3 4; do
            if e2fsck -fy "$img"; then
              echo "e2fsck reported clean on pass $i"
              clean=1
              break
            fi
            echo "e2fsck pass $i made changes, re-checking..."
          done
          if [ "$clean" != 1 ]; then
            echo "e2fsck did not converge to clean after 4 passes -- refusing to ship this image" >&2
            exit 1
          fi

          echo "Converting to Android sparse format..."
          img2simg "$img" "$out/sheng-rootfs.sparse.img"

          ${lib.optionalString cfg.keepRawImage ''
            mv "$img" "$out/sheng-rootfs.img"
          ''}
        '';
  };
}
