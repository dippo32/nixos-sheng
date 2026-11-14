# Charger mode runs before basic.target and may remain there for a long time.
# The ADSP is already running, so start the registry and sensor RPC daemon in
# parallel with the charger, instead of leaving the sensor PD without its host
# RPC for the entire charging interval. Preserve normal userland dependencies.
{ lib, ... }:
{
  systemd.services.sheng-sensors-data = {
    unitConfig = {
      DefaultDependencies = false;
      RequiresMountsFor = "/var/lib/qcom";
    };
    after = [ "local-fs.target" "systemd-journald.socket" ];
    wants = [ "local-fs.target" ];
    before = [ "shutdown.target" ];
    conflicts = [ "shutdown.target" ];
    serviceConfig.TimeoutStartSec = "30s";
  };

  systemd.services.adsprpcd-sensorspd = {
    unitConfig.DefaultDependencies = false;
    after = [
      "local-fs.target"
      "systemd-journald.socket"
      "systemd-udev-trigger.service"
      "systemd-modules-load.service"
    ];
    wants = [ "local-fs.target" "systemd-udev-trigger.service" "systemd-modules-load.service" ];
    before = [ "basic.target" "shutdown.target" ];
    conflicts = [ "shutdown.target" ];
    serviceConfig.TimeoutStartSec = "30s";
  };

  # A sensor failure must never block charger mode. Do not order the charger
  # after the daemon: a delayed registry copy must not delay its battery UI.
  systemd.services.xiaomi-charger-mode = {
    # Matches the packaged charger's base unit, and makes the intended early
    # ordering explicit in the generated drop-in as well.
    unitConfig.DefaultDependencies = false;
    wants = [ "adsprpcd-sensorspd.service" ];
  };

  # The upstream daemon has ConditionPathExists= for either FastRPC node. If
  # its first start is skipped because the node is late, request it again on
  # the device event. Append to existing IIO requests; never replace them.
  services.udev.extraRules = lib.mkAfter ''
    SUBSYSTEM=="misc", KERNEL=="fastrpc-adsp*", TAG+="systemd", ENV{SYSTEMD_WANTS}+="adsprpcd-sensorspd.service"
  '';
}
