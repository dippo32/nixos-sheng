# Google Antigravity App for ARM64, using the pinned Nixpkgs native wrapper.
# This is the App/Hub GUI, not the standalone IDE or the CLI.
{ antigravity-hub, fetchurl }:

antigravity-hub.overrideAttrs (old: {
  version = "2.32.0";
  src = fetchurl {
    url = "https://storage.googleapis.com/antigravity-public/antigravity-hub/2.32.0-6141816156848128/linux-arm/Antigravity.tar.gz";
    hash = "sha256-AUyYM+lzTqwgqIVFQvCmIBPcTSh8DDr97uxjmSb8SO8=";
  };
  passthru = (old.passthru or { }) // {
    buildId = "6141816156848128";
  };
  meta = old.meta // {
    platforms = [ "aarch64-linux" ];
  };
})
