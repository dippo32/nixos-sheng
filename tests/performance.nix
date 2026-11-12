# Evaluated configuration checks; RAM pressure, CPU/GPU load and temperature
# still require device measurements before making performance claims.
{ flake }:
let
  c = flake.nixosConfigurations.sheng-kde-personal.config;
  base = flake.nixosConfigurations.sheng-kde.config;
  generator = c.services.zram-generator.settings.zram0;
  baloo = c.environment.etc."xdg/baloofilerc".text;
in
assert c.zramSwap.enable;
assert c.zramSwap.algorithm == "zstd";
assert c.zramSwap.memoryPercent == 25;
assert c.zramSwap.memoryMax == 2147483648;
assert c.zramSwap.priority == 100;
assert c.zramSwap.swapDevices == 1;
assert c.services.zram-generator.enable;
assert generator.compression-algorithm == "zstd";
assert generator.swap-priority == 100;
assert c.systemd.services."systemd-zram-setup@".restartIfChanged == false;
assert builtins.match ".*only basic indexing=true.*" baloo != null;
assert builtins.match ".*Indexing-Enabled=false.*" baloo == null;
assert c.powerManagement.cpuFreqGovernor == base.powerManagement.cpuFreqGovernor;
assert c.powerManagement.cpufreq.min == base.powerManagement.cpufreq.min;
assert c.powerManagement.cpufreq.max == base.powerManagement.cpufreq.max;
assert
  (c.boot.kernel.sysctl."vm.swappiness" or null) == (base.boot.kernel.sysctl."vm.swappiness" or null);
assert c.services.power-profiles-daemon.enable == base.services.power-profiles-daemon.enable;
assert !c.services.tlp.enable;
assert !c.services.auto-cpufreq.enable;
{
  zram = {
    algorithm = c.zramSwap.algorithm;
    memoryPercent = c.zramSwap.memoryPercent;
    maximumBytes = c.zramSwap.memoryMax;
    priority = c.zramSwap.priority;
  };
  fileNameIndexing = true;
  contentIndexing = false;
  governorsAndLimitsUnchanged = true;
  runtimePerformanceMeasured = false;
}
