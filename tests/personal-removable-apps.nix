{ flake }:
let
  c = flake.nixosConfigurations.sheng-kde-personal.config;
  names = builtins.map (p: p.pname or p.name) c.environment.systemPackages;
  unit = c.systemd.services.sheng-seed-flatpaks;
  nativeApps = flake.packages.aarch64-linux;
in
assert !c.programs.firefox.enable;
assert !(builtins.any (name: flake.inputs.nixpkgs.lib.hasPrefix "firefox" name) names);
assert !(builtins.elem "librewolf" names);
assert !(builtins.elem "antigravity-ide" names);
assert !(builtins.elem "chatgpt" names);
assert nativeApps.chatgpt-native.pname == "chatgpt";
assert nativeApps.antigravity-native.pname == "antigravity-ide";
assert builtins.elem "aarch64-linux" nativeApps.chatgpt-native.meta.platforms;
assert builtins.elem "aarch64-linux" nativeApps.antigravity-native.meta.platforms;
assert !(builtins.hasAttr "x-scheme-handler/codex" c.xdg.mime.defaultApplications);
assert !(builtins.hasAttr "x-scheme-handler/antigravity-ide" c.xdg.mime.defaultApplications);
assert c.services.flatpak.enable && c.xdg.portal.enable;
assert c.xdg.mime.defaultApplications."text/html" == "io.gitlab.librewolf-community.desktop";
assert
  c.xdg.mime.defaultApplications."x-scheme-handler/https" == "io.gitlab.librewolf-community.desktop";
assert builtins.elem "display-manager.service" unit.before;
assert unit.unitConfig.ConditionPathExists == "/var/lib/sheng-private/flatpak-seed.tar.zst";
assert unit.serviceConfig.Type == "oneshot";
assert c.sheng.rootfs.privateProvisioningReserveMiB == 8192;
assert c.sheng.rootfs.imageSize == null;
assert flake.nixosConfigurations.sheng-kde.config.sheng.rootfs.privateProvisioningReserveMiB == 0;
assert flake.nixosConfigurations.sheng-kde.config.programs.firefox.enable;
{
  firefoxRemoved = true;
  mutableUserFlatpaks = true;
  nativeAppsAvailableForUserProfile = true;
  privateSeedRequired = true;
  privateProvisioningReserveMiB = c.sheng.rootfs.privateProvisioningReserveMiB;
  runtimeAppsTested = false;
}
