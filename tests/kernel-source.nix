# Source-generation contract, without reading/building the ARM .config. The
# effective NixOS kernel selection is checked separately on the ARM builder.
{ flake }:
let
  pkgs = flake.nixosConfigurations.sheng-kde-personal.pkgs;
  sourceArguments =
    diagnostics:
    pkgs.callPackage ../packages/kernel {
      displayDiagnostics = diagnostics;
      linuxManualConfig = arguments: arguments;
    };
  production = sourceArguments false;
  diagnostic = sourceArguments true;
in
assert production.src.pname == "sheng-kernel-src-production";
assert diagnostic.src.pname == "sheng-kernel-src-traced";
assert builtins.match ".*SHENG_.*" production.src.postPatch == null;
assert builtins.match ".*SHENG_TRACE.*" diagnostic.src.postPatch != null;
assert builtins.match ".*SHENG_RD.*" diagnostic.src.postPatch != null;
assert builtins.match ".*NVT_LOG.*pr_debug.*" production.src.postPatch != null;
assert builtins.match ".*GS_CONSOLE_BUF_SIZE.*" production.src.postPatch != null;
assert production.version == diagnostic.version;
assert production.modDirVersion == diagnostic.modDirVersion;
{
  productionDisplayInstrumentation = false;
  legacyDiagnosticsAvailable = true;
  sharedTouchAndConsoleFixesRetained = true;
}
