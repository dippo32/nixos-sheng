# Personal single-boot KDE candidate. Existing downloadable images keep their
# defaults; this profile selects the owner's accessory and application needs.
{ pkgs, ... }:
{
  services.shengFirmware.keyboard.enable = false;
  services.shengFirmware.pen.enable = false;

  services.flatpak.enable = true;
  # Flatpak's supported static remote mechanism includes the upstream signing
  # key in the image. Adding Flathub does not require network on first boot.
  environment.etc."flatpak/remotes.d/flathub.flatpakrepo".source = ./assets/flathub.flatpakrepo;

  # SDDM's --inputmethod covers the greeter only. Select the installed keyboard
  # for the logged-in KWin session too; user preferences can override this.
  environment.etc."xdg/kwinrc".text = ''
    [Wayland]
    InputMethod=${pkgs.kdePackages.plasma-keyboard}/share/applications/org.kde.plasma.keyboard.desktop
  '';

  # Short device tests favour s2idle over deep's early USB wakeups. This is a
  # candidate preference, not a fix for the documented DWC3 freeze on unplug.
  boot.kernelParams = [ "mem_sleep_default=s2idle" ];
  services.logind.settings.Login.HandlePowerKey = "suspend";

  environment.systemPackages = [
    pkgs.trace-cmd
    (pkgs.writeShellApplication {
      name = "sheng-power-report";
      runtimeInputs = [
        pkgs.coreutils
        pkgs.util-linux
        pkgs.systemd
      ];
      text = builtins.readFile ../scripts/sheng-power-report;
    })
  ];
}
