# Configuration checks only; these do not claim device interaction was tested.
{ flake }:
let
  base = flake.nixosConfigurations.sheng-kde;
  names = packages: builtins.map (package: package.pname or package.name) packages;
  hasPackage = name: packages: builtins.elem name (names packages);
  configured =
    keyboard: pen:
    (base.extendModules {
      modules = [
        {
          services.shengFirmware.keyboard.enable = keyboard;
          services.shengFirmware.pen.enable = pen;
        }
      ];
    }).config;
  check =
    keyboard: pen:
    let
      c = configured keyboard pen;
      packages = c.environment.systemPackages;
      systemdPackages = c.systemd.packages;
    in
    assert c.services.shengFirmware.enable;
    assert (hasPackage "sheng-devauth" packages) == keyboard;
    assert (hasPackage "sheng-keyboard-helper" packages) == keyboard;
    assert (hasPackage "sheng-devauth" systemdPackages) == keyboard;
    assert (c.systemd.services ? sheng-devauth) == keyboard;
    assert (c.systemd.services ? xiaomi-sheng-keyboard-helper-angle) == keyboard;
    assert (c.systemd.user.services ? xiaomi-sheng-keyboard-helper-micmute) == keyboard;
    assert (builtins.match ".*nanosic_hinge.*" c.services.udev.extraRules != null) == keyboard;
    assert (hasPackage "sheng-pen-status" packages) == pen;
    assert (c.environment.etc ? "xdg/autostart/xiaomi-pen-status.desktop") == pen;
    assert hasPackage "sheng-thp" packages;
    assert hasPackage "sheng-thp" systemdPackages;
    assert c.systemd.services.xiaomi-sheng-thp.wantedBy == [ "multi-user.target" ];
    assert hasPackage "sheng-sensors" packages;
    assert hasPackage "sheng-fingerprint" packages;
    assert hasPackage "sheng-mipps-auth" packages;
    assert hasPackage "sheng-charger-mode" packages;
    assert hasPackage "sheng-charger-mode" systemdPackages;
    assert c.systemd.services.xiaomi-charger-mode.wantedBy == [ "multi-user.target" ];
    assert hasPackage "alsa-ucm-sheng" packages;
    assert c.services.fprintd.enable;
    assert c.hardware.bluetooth.enable;
    assert c.services.pipewire.enable;
    {
      inherit keyboard pen;
      touchscreen = true;
      coreServices = true;
    };
  defaults = base.config.services.shengFirmware;
in
assert defaults.keyboard.enable;
assert defaults.pen.enable;
{
  defaultAccessories = check true true;
  noKeyboard = check false true;
  noPen = check true false;
  noAccessories = check false false;
}
