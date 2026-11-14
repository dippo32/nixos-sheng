# Sheng kernel and vendor userspace, injected into pkgs so modules can use
# pkgs.shengKernel / pkgs.shengPackages.* instead of importing paths.
final: prev: {
  # Keep the software ISP producer and its IPA consumers on the same build:
  # the upstream AWB backport changes their internal shared statistics layout.
  libcamera = prev.libcamera.overrideAttrs (old: {
    patches = (old.patches or [ ]) ++ [
      ./packages/libcamera/0001-softisp-awb-exclude-saturated.patch
    ];
    nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ final.python3 ];
    postPatch = (old.postPatch or "") + ''
      python3 ${./tests/softisp-awb-fixtures.py} .
    '';
  });
  shengKernel = final.callPackage ./packages/kernel { };
  shengPackages = final.callPackage ./packages/firmware { };
}
