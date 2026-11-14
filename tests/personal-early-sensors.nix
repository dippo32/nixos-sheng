# Declarative checks only; systemd transaction checks and hardware tests are
# still necessary to establish actual startup order and sensor discovery.
{ flake }:
let
  lib = flake.inputs.nixpkgs.lib;
  personal = flake.nixosConfigurations.sheng-kde-personal.config;
  base = flake.nixosConfigurations.sheng-kde.config;
  registry = personal.systemd.services.sheng-sensors-data;
  rpc = personal.systemd.services.adsprpcd-sensorspd;
  charger = personal.systemd.services.xiaomi-charger-mode;
  earlyRule = ''SUBSYSTEM=="misc", KERNEL=="fastrpc-adsp*", TAG+="systemd", ENV{SYSTEMD_WANTS}+="adsprpcd-sensorspd.service"'';
  hasAll = values: expected: builtins.all (value: builtins.elem value values) expected;
  avoidsLateTargets = unit: !(builtins.elem "basic.target" unit.after) && !(builtins.elem "sysinit.target" unit.after);
in
assert personal.services.shengFirmware.enable;
assert registry.unitConfig.DefaultDependencies == false;
assert registry.unitConfig.RequiresMountsFor == "/var/lib/qcom";
assert hasAll registry.after [ "local-fs.target" "systemd-journald.socket" ];
assert hasAll registry.before [ "adsprpcd-sensorspd.service" "shutdown.target" ];
assert builtins.elem "shutdown.target" registry.conflicts;
assert builtins.elem "adsprpcd-sensorspd.service" registry.requiredBy;
assert registry.serviceConfig.TimeoutStartSec == "30s";
assert avoidsLateTargets registry;
assert rpc.unitConfig.DefaultDependencies == false;
assert hasAll rpc.after [ "local-fs.target" "systemd-journald.socket" "systemd-udev-trigger.service" "systemd-modules-load.service" ];
assert hasAll rpc.wants [ "local-fs.target" "systemd-udev-trigger.service" "systemd-modules-load.service" ];
assert hasAll rpc.before [ "basic.target" "shutdown.target" ];
assert builtins.elem "shutdown.target" rpc.conflicts;
assert rpc.serviceConfig.TimeoutStartSec == "30s";
assert avoidsLateTargets rpc;
assert builtins.elem "adsprpcd-sensorspd.service" charger.wants;
assert !(builtins.elem "adsprpcd-sensorspd.service" charger.requires);
assert !(builtins.elem "adsprpcd-sensorspd.service" charger.after);
assert lib.hasInfix earlyRule personal.services.udev.extraRules;
assert !(lib.hasInfix earlyRule base.services.udev.extraRules);
assert !(base.systemd.services ? adsprpcd-sensorspd)
  || ((base.systemd.services.adsprpcd-sensorspd.unitConfig.DefaultDependencies or true) != false);
{
  personalOnly = true;
  sensorStartDoesNotOrderCharger = true;
  deviceLateRetryViaUdev = true;
  fullTransactionAndHardwareVerified = false;
}
