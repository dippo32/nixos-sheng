# U-Boot for sheng, plus the Android boot.img ABL actually loads.
{
  lib,
  buildUBoot,
  zig_0_15,
  xxd,
  android-tools,
  src,
  version ? "sheng",
  rootPartition ? "userdata",
  directBoot ? false,
}:

let
  # ABL rejects anything else. Offsets and page size come from the stock
  # boot.img header.
  mkbootimgArgs = [
    "--kernel u-boot-dtb.bin"
    "--dtb u-boot.dtb"
    "--cmdline 'console=ttyMSM0,115200n8 console=ttyGS0,115200n8 g_serial.use_acm=1 root=PARTLABEL=${rootPartition}'"
    "--base 0x00000000"
    "--kernel_offset 0x00008000"
    "--tags_offset 0x01e00000"
    "--pagesize 4096"
    "--header_version 2"
    "--id"
  ];
in
assert lib.assertMsg (
  builtins.match "[A-Za-z0-9_-]{1,36}" rootPartition != null
) "U-Boot rootPartition must be a simple GPT partition label";
(buildUBoot {
  inherit src version;

  defconfig = "sm8550_defconfig";

  # The built-in DT captures an 8 GiB tablet's RAM/firmware holes. ABL
  # supplies the actual variant's ranges; use those for relocation and Linux.
  patches = [
    ./patches/prefer-abl-memory-layout.patch
    ./patches/fix-fastboot-menu-reboot-mode.patch
  ];

  # The MDSS register sequencing is Zig. Passed as a make variable rather than
  # put on PATH, because nixpkgs' zig hook would replace buildPhase with `zig
  # build` and there is no build.zig here.
  # This source uses Zig 0.15 syntax; nixpkgs.zig now points to 0.17.
  extraMakeFlags = [ "ZIG=${lib.getExe zig_0_15}" ];

  filesToInstall = [
    "u-boot.bin"
    "u-boot-nodtb.bin"
    "u-boot-dtb.bin"
    "u-boot.dtb"
  ];

  extraMeta = {
    description = "U-Boot for the Xiaomi Pad 6S Pro (sheng, SM8550)";
    platforms = [ "aarch64-linux" ];
  };
}).overrideAttrs
  (
    old:
    {
      pname = "u-boot-sheng";

      nativeBuildInputs = old.nativeBuildInputs ++ [
        android-tools # mkbootimg
        xxd # CONFIG_ENV_USE_DEFAULT_ENV_TEXT_FILE embeds sheng.env via xxd
      ];

      # zig writes caches relative to $HOME, which is not writable here.
      preBuild = ''
        export HOME=$TMPDIR
        export ZIG_GLOBAL_CACHE_DIR=$TMPDIR/zig-cache
        export ZIG_LOCAL_CACHE_DIR=$TMPDIR/zig-cache
      '';

      postInstall = ''
        mkbootimg ${lib.concatStringsSep " " mkbootimgArgs} -o "$out/boot.img"
      '';
    }
    // lib.optionalAttrs (rootPartition != "userdata" || directBoot) {
      # Keep the existing single-system environment byte-for-byte unchanged.
      # Both normal/menu loading and the rescue path must select the same root.
      postPatch =
        (old.postPatch or "")
        + lib.optionalString (rootPartition != "userdata") ''
          substituteInPlace board/qualcomm/sheng.env \
            --replace-fail "part number scsi 0 userdata partnum" "part number scsi 0 ${rootPartition} partnum" \
            --replace-fail "root=PARTLABEL=userdata" "root=PARTLABEL=${rootPartition}"
        ''
        + lib.optionalString directBoot ''
          # Skip the generation menu while keeping bootlinux's normal/rescue path.
          substituteInPlace board/qualcomm/sheng.env \
            --replace-fail 'bootcmd=run loadgenmenu; bootmenu 5' 'bootcmd=run bootlinux'
        '';

    }
  )
