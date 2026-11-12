# Personal-only cleanup. The current NixOS system generation is still required
# internally. Remove only earlier system generation links after the selected
# system has booted; do not touch user profiles or a pending boot generation.
{ config, pkgs, ... }:
let
  prune = pkgs.writeShellApplication {
    name = "sheng-prune-generations";
    runtimeInputs = [
      pkgs.coreutils
      config.nix.package
    ];
    text = builtins.readFile ../scripts/sheng-prune-generations;
  };
in
{
  # The installer still emits default/diagnostic entries, but no old generation
  # entries. The independent personal U-Boot candidate removes the menu itself.
  sheng.boot.configurationLimit = 0;

  systemd.services.sheng-prune-generations = {
    description = "Prune old NixOS system generations after the selected system boots";
    after = [
      "nix-daemon.service"
      "sheng-mark-boot-successful.service"
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${prune}/bin/sheng-prune-generations";
      CPUSchedulingPolicy = "idle";
      IOSchedulingClass = "idle";
    };
  };
  systemd.timers.sheng-prune-generations = {
    wantedBy = [ "timers.target" ];
    timerConfig.OnBootSec = "10min";
  };

  # Garbage collection is separate, scoped to unreachable objects, and never
  # passes --delete-old: other users' profile generations stay untouched.
  nix.gc = {
    automatic = true;
    dates = [ "weekly" ];
    options = "";
  };
  systemd.services.nix-gc.serviceConfig = {
    CPUSchedulingPolicy = "idle";
    IOSchedulingClass = "idle";
  };
}
