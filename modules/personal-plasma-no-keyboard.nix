# Personal-only replacement of the pinned upstream Plasma module.  Its public
# excludePackages option applies only to optional packages, while the upstream
# module currently hardcodes plasma-keyboard into its requiredPackages list.
{ lib, modulesPath, ... }:
let
  modulePath = "${modulesPath}/services/desktop-managers/plasma6.nix";
  source = builtins.readFile modulePath;
  keyboardLine = "          plasma-keyboard\n";
  # Fail closed when nixpkgs changes this part of the module: a future update
  # must be reviewed rather than silently keeping or removing another package.
  checkedSource = assert builtins.length (lib.splitString keyboardLine source) == 2; source;
  customizedSource = lib.replaceStrings [ keyboardLine ] [ "" ] checkedSource;
in
{
  disabledModules = [ modulePath ];
  imports = [ (builtins.toFile "sheng-personal-plasma6.nix" customizedSource) ];
}
