# The touch-only personal tablet has no keyboard/tablet-mode switch. KWin's
# default InTabletMode policy can therefore leave working SSC orientation unused.
{ config, pkgs, ... }:
let
  enableRotation = pkgs.writeShellApplication {
    name = "sheng-enable-rotation";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.jq
      pkgs.kdePackages.libkscreen
    ];
    text = builtins.readFile ../scripts/sheng-enable-rotation;
  };
in
{
  environment.systemPackages = [ enableRotation ];

  # Run inside the real Wayland user session after KWin, not in SDDM or as root.
  # SSC can arrive later than the compositor; the helper retries with a delay
  # and exits, rather than leaving a display/sensor polling daemon running.
  # Type=exec lets the desktop target proceed as soon as the helper starts.
  systemd.user.services.sheng-enable-rotation = {
    description = "Enable automatic orientation for the internal tablet display";
    wantedBy = [ "plasma-workspace-wayland.target" ];
    after = [
      "plasma-kwin_wayland.service"
      "graphical-session.target"
    ];
    partOf = [ "graphical-session.target" ];
    unitConfig.ConditionUser = config.sheng.desktop.userName;
    serviceConfig = {
      Type = "exec";
      ExecStart = "${enableRotation}/bin/sheng-enable-rotation";
      TimeoutStartSec = "10s";
      TimeoutStopSec = "5s";
      RuntimeMaxSec = "6min";
    };
  };
}
