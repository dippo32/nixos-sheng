# Conservative personal-image defaults. These do not change CPU/GPU governors,
# frequency limits, thermal protection, or the kernel's swappiness default.
{ ... }:
{
  # The locked Debian sheng config (a93aaa1eff77) enables ZRAM=m, SWAP=y and
  # ZRAM_BACKEND_ZSTD=y; its ZRAM_BACKEND_LZ4 is explicitly disabled.
  # https://github.com/ianchb/debian-sheng/blob/a93aaa1eff77a2bf0552b8dafaa35c1e0880317f/sm8550.config
  # memoryMax is bytes; memoryPercent describes the uncompressed swap capacity,
  # not an upfront RAM reservation. Cap it at 2 GiB to limit this first candidate.
  zramSwap = {
    enable = true;
    algorithm = "zstd";
    memoryPercent = 25;
    memoryMax = 2 * 1024 * 1024 * 1024;
    priority = 100;
  };

  # Baloo 6.31's supported setting keeps file-name/metadata indexing while
  # avoiding document-content extraction. A user's own settings take priority.
  environment.etc."xdg/baloofilerc".text = ''
    [General]
    only basic indexing=true
  '';

  # KWin 6.8.2's supported global animation setting; 0.75 is also an official
  # slider value. Default transition durations become 25% shorter, with effects
  # still enabled and user preferences able to override this system default.
  # https://github.com/KDE/kwin/blob/v6.8.2/src/kcms/animations/animationskdeglobalssettings.kcfg
  # This is a timing preference; runtime smoothness still needs measurement.
  environment.etc."xdg/kdeglobals".text = ''
    [KDE]
    AnimationDurationFactor=0.75
  '';
}
