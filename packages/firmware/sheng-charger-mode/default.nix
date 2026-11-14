# Framebuffer charger-mode screen, shown when the cmdline carries
# androidboot.mode=charger. The upstream program is a Python script.
{
  lib,
  stdenvNoCC,
  fetchFromGitHub,
  python3,
  util-linux,
  plymouth,
  sheng-mipps-auth,
}:

stdenvNoCC.mkDerivation {
  pname = "sheng-charger-mode";
  version = "0.1";

  src = fetchFromGitHub {
    owner = "ianchb";
    repo = "xiaomi-charger-mode";
    rev = "0c00fcd2cb064f563f44babb345c1dffecf2ada2"; # master as of 2026-08-18
    hash = "sha256-g0IfrZzQ98Uwd2kXEZeYt9Zwf0dzTw12nyoDMgL69WQ=";
  };

  dontBuild = true;
  dontConfigure = true;

  installPhase = ''
    runHook preInstall

    install -Dm755 xiaomi-charger-mode "$out/libexec/xiaomi-charger-mode"
    install -Dm644 xiaomi-charger-mode.service \
      "$out/lib/systemd/system/xiaomi-charger-mode.service"

    # The upstream paths are for Debian and do not exist on NixOS. Keep the
    # executable and the optional charger authentication in the closure.
    substituteInPlace "$out/libexec/xiaomi-charger-mode" \
      --replace-fail '#!/usr/bin/python3' '#!${python3}/bin/python3' \
      --replace-fail '/usr/libexec/xiaomi-mipps-auth' '${sheng-mipps-auth}/libexec/xiaomi-mipps-auth' \
      --replace-fail '/usr/bin/flock' '${util-linux}/bin/flock' \
      --replace-fail '/usr/bin/plymouth' '${plymouth}/bin/plymouth'
    substituteInPlace "$out/lib/systemd/system/xiaomi-charger-mode.service" \
      --replace-fail '/usr/libexec/xiaomi-charger-mode' "$out/libexec/xiaomi-charger-mode"

    runHook postInstall
  '';

  doInstallCheck = true;
  installCheckPhase = ''
    runHook preInstallCheck
    grep -Fx "ExecStart=$out/libexec/xiaomi-charger-mode" "$out/lib/systemd/system/xiaomi-charger-mode.service"
    grep -Fx 'ConditionKernelCommandLine=androidboot.mode=charger' "$out/lib/systemd/system/xiaomi-charger-mode.service"
    grep -Fx 'Before=basic.target display-manager.service shutdown.target' "$out/lib/systemd/system/xiaomi-charger-mode.service"
    grep -Fx '#!${python3}/bin/python3' "$out/libexec/xiaomi-charger-mode"
    grep -F '${sheng-mipps-auth}/libexec/xiaomi-mipps-auth' "$out/libexec/xiaomi-charger-mode"
    grep -F '${util-linux}/bin/flock' "$out/libexec/xiaomi-charger-mode"
    grep -F '${plymouth}/bin/plymouth' "$out/libexec/xiaomi-charger-mode"
    ${python3}/bin/python3 -c 'import pathlib, sys; p = pathlib.Path(sys.argv[1]); compile(p.read_bytes(), str(p), "exec")' "$out/libexec/xiaomi-charger-mode"
    runHook postInstallCheck
  '';

  meta = {
    description = "Xiaomi charger-mode UI daemon";
    license = lib.licenses.gpl2Only;
    platforms = [ "aarch64-linux" ];
  };
}
