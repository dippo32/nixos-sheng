# Personal single-boot KDE candidate. Existing downloadable images keep their
# defaults; this profile selects the owner's accessory and application needs.
{ lib, pkgs, ... }:
let
  kboard = pkgs.callPackage ../packages/kboard { };
  # The SDDM greeter runs as a separate user and its XDG_CONFIG_DIRS is not
  # guaranteed to include /etc/xdg. Match the tested explicit config-home
  # arrangement without changing the logged-in user's settings.
  kboardGreeter = pkgs.writeShellScriptBin "kboard-sddm" ''
    export XDG_CONFIG_HOME=/etc/xdg
    exec ${lib.getExe kboard} "$@"
  '';
in
{
  imports = [
    ./personal-performance.nix
    ./personal-generation-retention.nix
    ./personal-account.nix
    ./personal-removable-apps.nix
    ./personal-rotation.nix
  ];

  sheng.rootfs.privateProvisioningReserveMiB = 8192;

  boot.kernelPackages = lib.mkForce (
    pkgs.linuxPackagesFor (
      pkgs.shengKernel.override {
        displayDiagnostics = false;
        powerDiagnostics = true;
      }
    )
  );

  services.shengFirmware.keyboard.enable = false;
  services.shengFirmware.pen.enable = false;

  # The base bring-up image enables a root USB serial console. Stopping its
  # getty alone does not release the UDC because g_serial is built in. The
  # pinned driver's enable parameter skips usb_composite_probe at boot.
  services.shengSerialConsole.enable = lib.mkForce false;

  services.flatpak.enable = true;
  sheng.virtualKeyboard.package = kboardGreeter;
  # Flatpak's supported static remote mechanism includes the upstream signing
  # key in the image. Adding Flathub does not require network on first boot.
  environment.etc."flatpak/remotes.d/flathub.flatpakrepo".source = ./assets/flathub.flatpakrepo;

  # SDDM's --inputmethod covers the greeter only. Select the installed keyboard
  # for the logged-in KWin session too; user preferences can override this.
  environment.etc."xdg/kwinrc".text = ''
    [Wayland]
    InputMethod=${kboard}/share/applications/org.devl0rd.kboard.desktop
  '';

  # User preferences override these defaults. The greeter runs as its own user.
  environment.etc."xdg/kboardrc".text = ''
    [Look]
    splitMode=Auto

    [Sound]
    soundEnabled=false
  '';

  # Short device tests favour s2idle over deep's early USB wakeups. This is a
  # candidate preference, not a fix for the documented DWC3 freeze on unplug.
  boot.kernelParams = [
    "mem_sleep_default=s2idle"
    "g_serial.enable=0"
  ];
  services.logind.settings.Login.HandlePowerKey = "suspend";

  environment.systemPackages = [
    # Retain KBoard as part of the system generation, including at SDDM.
    kboard
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
