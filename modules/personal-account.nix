# Personal identity and login policy. The password hash is injected privately
# into the image after CI; only its runtime filename belongs in Nix/store data.
{ config, lib, ... }:
let
  login = config.sheng.desktop.userName;
in
{
  sheng.desktop.userName = lib.mkForce "dippo";

  # Apply the private file and root lock on every activation, including an
  # existing installation. With a missing private file, login stays locked.
  users.mutableUsers = lib.mkForce false;
  users.users.${login} = {
    uid = 1000;
    description = lib.mkForce "Dippo Shelan";
    initialPassword = lib.mkForce null;
    initialHashedPassword = lib.mkForce null;
    password = lib.mkForce null;
    hashedPassword = lib.mkForce null;
    hashedPasswordFile = "/var/lib/sheng-private/login.hash";
  };

  users.users.root = {
    initialPassword = lib.mkForce null;
    initialHashedPassword = lib.mkForce null;
    password = lib.mkForce null;
    hashedPasswordFile = lib.mkForce null;
    hashedPassword = lib.mkForce "!";
  };

  systemd.tmpfiles.rules = [ "d /var/lib/sheng-private 0700 root root -" ];

  services.displayManager.autoLogin = {
    enable = lib.mkForce false;
    user = lib.mkForce null;
  };
  services.getty.autologinUser = lib.mkForce null;
}
