# The legacy private Flatpak seed remains optional; the native apps can be
# installed separately into a user's Nix profile.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  seed = pkgs.writeShellApplication {
    name = "sheng-seed-flatpaks";
    runtimeInputs = with pkgs; [
      coreutils
      flatpak
      gnutar
      python3
      util-linux
      zstd
    ];
    text = builtins.readFile ../scripts/sheng-seed-flatpaks;
  };
  browser = "io.gitlab.librewolf-community.desktop";
in
{
  assertions = [
    {
      assertion =
        config.sheng.desktop.userName == "dippo"
        && config.users.users.dippo.uid == 1000
        && config.users.users.dippo.group == "users"
        && config.users.groups.users.gid == 100
        && config.users.users.dippo.home == "/home/dippo";
      message = "The private Flatpak seed requires dippo with uid 1000, users gid 100 and /home/dippo.";
    }
  ];

  programs.firefox.enable = lib.mkForce false;
  xdg.mime.defaultApplications = {
    "text/html" = browser;
    "application/xhtml+xml" = browser;
    "x-scheme-handler/http" = browser;
    "x-scheme-handler/https" = browser;
  };

  # The image assembler inserts the seed privately, outside the Nix store.
  # Successful first-boot extraction is one-shot: later application removal is
  # a user action and must never trigger a reinstall.
  systemd.services.sheng-seed-flatpaks = {
    description = "Seed private per-user Flatpaks once before desktop login";
    wantedBy = [ "multi-user.target" ];
    before = [ "display-manager.service" ];
    after = [ "local-fs.target" ];
    requires = [ "local-fs.target" ];
    unitConfig.ConditionPathExists = "/var/lib/sheng-private/flatpak-seed.tar.zst";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${seed}/bin/sheng-seed-flatpaks";
      TimeoutStartSec = "30min";
    };
  };
}
