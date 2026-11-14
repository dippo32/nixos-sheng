{ flake }:
let
  personal = flake.nixosConfigurations.sheng-kde-personal.config.boot.kernelPackages.kernel;
  diagnostic = flake.nixosConfigurations.sheng-kde.config.boot.kernelPackages.kernel;
in
assert personal.src.pname == "sheng-kernel-src-production";
assert diagnostic.src.pname == "sheng-kernel-src-traced";
assert builtins.match ".*SHENG_.*" personal.src.postPatch == null;
assert builtins.match ".*SHENG_TRACE.*" diagnostic.src.postPatch != null;
assert builtins.match ".*SHENG_RD.*" diagnostic.src.postPatch != null;
assert builtins.match ".*NVT_LOG.*pr_debug.*" personal.src.postPatch != null;
assert builtins.match ".*GS_CONSOLE_BUF_SIZE.*" personal.src.postPatch != null;
assert personal.version == diagnostic.version;
assert personal.modDirVersion == diagnostic.modDirVersion;
assert personal.version == "7.3.4-sheng";
assert personal.modDirVersion == "7.3.4-sm8550";
assert personal.config.isYes "MODULES";
assert personal.config.isYes "PM_DEBUG";
assert personal.config.isYes "PM_SLEEP_DEBUG";
{
  personalDisplayPath = "upstream without bring-up display instrumentation";
  diagnosticKernelAvailable = true;
  touchLogAndSerialBufferFixesRetained = true;
  stagedSleepDiagnosticsAvailable = true;
  runtimePerformanceMeasured = false;
}
