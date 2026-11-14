# Entrypoint: aggregates every sheng vendor userspace package into one
# attrset, callPackage-style. Consumed by nixos/xiaomi-sheng-services.nix.
{ lib, callPackage }:

let
  libssc = callPackage ./libssc { };
  sheng-mipps-auth = callPackage ./sheng-mipps-auth { };
in
{
  inherit libssc sheng-mipps-auth;

  sheng-firmware-blobs = callPackage ./sheng-firmware-blobs { };
  fastrpc = callPackage ./fastrpc { };
  iio-sensor-proxy = callPackage ./iio-sensor-proxy { inherit libssc; };
  sheng-sensors = callPackage ./sheng-sensors { };
  sheng-devauth = callPackage ./sheng-devauth { };
  alsa-ucm-sheng = callPackage ./alsa-ucm-sheng { };
  sheng-fingerprint = callPackage ./sheng-fingerprint { };
  sheng-thp = callPackage ./sheng-thp { inherit libssc; };
  sheng-pen-status = callPackage ./sheng-pen-status { };
  sheng-keyboard-helper = callPackage ./sheng-keyboard-helper { inherit libssc; };
  sheng-charger-mode = callPackage ./sheng-charger-mode { inherit sheng-mipps-auth; };
}
