# Configuration proof only; private hash injection and login require separate
# image inspection and device validation. No password/hash content is read here.
{ flake }:
let
  c = flake.nixosConfigurations.sheng-kde-personal.config;
  user = c.users.users.${c.sheng.desktop.userName};
  root = c.users.users.root;
  publicUser = (import ../image-settings.nix).userName;
  standardAccountUnchanged =
    name:
    let
      base = flake.nixosConfigurations.${name}.config;
    in
    base.sheng.desktop.userName == publicUser
    && base.services.displayManager.autoLogin.enable
    && base.services.displayManager.autoLogin.user == publicUser
    && base.users.users.${publicUser}.description == "NixOS desktop user"
    && base.users.users.${publicUser}.initialPassword != null
    && base.users.users.${publicUser}.hashedPasswordFile == null
    && base.services.getty.autologinUser == "root"
    && base.users.mutableUsers;
in
assert c.sheng.desktop.userName == "dippo";
assert !(c.users.users ? nixos);
assert user.isNormalUser;
assert user.uid == 1000;
assert user.home == "/home/dippo";
assert user.description == "Dippo Shelan";
assert builtins.elem "wheel" user.extraGroups;
assert user.initialPassword == null;
assert user.initialHashedPassword == null;
assert user.password == null;
assert user.hashedPassword == null;
assert user.hashedPasswordFile == "/var/lib/sheng-private/login.hash";
assert !c.users.mutableUsers;
assert root.initialPassword == null;
assert root.initialHashedPassword == null;
assert root.password == null;
assert root.hashedPasswordFile == null;
assert root.hashedPassword == "!";
assert !c.services.displayManager.autoLogin.enable;
assert c.services.displayManager.autoLogin.user == null;
assert c.services.getty.autologinUser == null;
assert c.services.displayManager.sddm.enable;
assert c.services.displayManager.sddm.wayland.enable;
assert c.services.displayManager.sddm.wayland.compositor == "kwin";
assert
  builtins.match ".*--inputmethod .*/bin/plasma-keyboard.*" c.services.displayManager.sddm.settings.Wayland.CompositorCommand
  != null;
assert
  builtins.match ".*InputMethod=.*/share/applications/org.kde.plasma.keyboard.desktop.*"
    c.environment.etc."xdg/kwinrc".text != null;
assert builtins.all standardAccountUnchanged [
  "sheng-kde"
  "sheng-gnome"
  "sheng-dual-kde"
  "sheng-dual-gnome"
];
{
  login = c.sheng.desktop.userName;
  displayName = user.description;
  uid = user.uid;
  privateHashFileRequired = true;
  autologin = false;
  rootPasswordLocked = true;
  standardAccountsUnchanged = true;
  runtimeLoginTested = false;
}
