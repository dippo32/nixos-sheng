{ flake }:
let
  personal = flake.nixosConfigurations.sheng-kde-personal.config;
  standard = flake.nixosConfigurations.sheng-kde.config;
in
assert personal.sheng.boot.configurationLimit == 10;
assert !(personal.systemd.timers ? sheng-prune-generations);
assert !(personal.systemd.services ? sheng-prune-generations);
assert personal.nix.gc.automatic;
assert personal.nix.gc.options == "";
assert personal.nix.gc.dates == [ "weekly" ];
assert standard.sheng.boot.configurationLimit == 10;
assert !(standard.systemd.timers ? sheng-prune-generations);
{
  personalGenerationsPreserved = true;
  standardUnchanged = true;
}
