{ flake }:
let
  c = flake.nixosConfigurations.sheng-kde-personal.config;
  packages = builtins.map (p: p.pname or p.name) c.environment.systemPackages;
  remote = builtins.readFile c.environment.etc."flatpak/remotes.d/flathub.flatpakrepo".source;
in
assert c.sheng.rootfs.partlabel == "userdata";
assert c.networking.hostName == "sheng-kde-personal";
assert c.services.desktopManager.plasma6.enable;
assert c.services.displayManager.autoLogin.user == (import ../image-settings.nix).userName;
assert c.services.pipewire.enable && c.services.pipewire.pulse.enable;
assert !c.services.shengFirmware.keyboard.enable;
assert !c.services.shengFirmware.pen.enable;
assert !(c.systemd.services ? sheng-devauth);
assert !(c.systemd.services ? xiaomi-sheng-keyboard-helper-angle);
assert !(c.environment.etc ? "xdg/autostart/xiaomi-pen-status.desktop");
assert c.services.shengFirmware.enable;
assert c.services.flatpak.enable;
assert c.xdg.portal.enable;
assert
  builtins.match ".*InputMethod=.*/share/applications/org.kde.plasma.keyboard.desktop.*"
    c.environment.etc."xdg/kwinrc".text != null;
assert builtins.elem "flatpak" packages;
assert builtins.elem "discover" packages;
assert builtins.elem "xdg-desktop-portal-kde" (
  builtins.map (p: p.pname or p.name) c.xdg.portal.extraPortals
);
assert builtins.elem "mem_sleep_default=s2idle" c.boot.kernelParams;
assert c.services.logind.settings.Login.HandlePowerKey == "suspend";
assert builtins.match ".*Url=https://dl.flathub.org/repo/.*" remote != null;
assert builtins.match ".*GPGKey=.+" remote != null;
{
  hostname = c.networking.hostName;
  root = c.sheng.rootfs.partlabel;
  flatpak = c.services.flatpak.enable;
  flathub = true;
  keyboard = c.services.shengFirmware.keyboard.enable;
  pen = c.services.shengFirmware.pen.enable;
  touchKeyboardDefault = true;
  sleepCandidate = "s2idle; hardware validation required";
}
