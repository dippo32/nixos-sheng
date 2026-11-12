# Vendor userspace integration. Accessory helpers can be disabled independently
# without removing the shared touchscreen, sensors, audio or charging stack.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.shengFirmware;
  sp = pkgs.shengPackages;
in
{
  options.services.shengFirmware = {
    enable = lib.mkEnableOption "Xiaomi sheng vendor userspace stack (sensors, keyboard/pen/fingerprint/charger auth)";
    keyboard.enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Enable authentication, fold-angle and mic-mute helpers for the Xiaomi magnetic keyboard.";
    };
    pen.enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Enable the Focus Pen status utility and desktop automatic pairing.
        The shared THP touchscreen processor remains enabled when this is false.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [
      sp.fastrpc
      sp.libssc
      sp.iio-sensor-proxy
      sp.sheng-sensors
      sp.sheng-fingerprint
      sp.sheng-thp
      sp.sheng-mipps-auth
      sp.sheng-charger-mode
      sp.alsa-ucm-sheng
    ]
    ++ lib.optionals cfg.keyboard.enable [
      sp.sheng-devauth
      sp.sheng-keyboard-helper
    ]
    ++ lib.optional cfg.pen.enable sp.sheng-pen-status;

    systemd.packages = [
      sp.fastrpc # adsprpcd-sensorspd.service
      sp.iio-sensor-proxy # iio-sensor-proxy.service (+ .d/10-sheng-sensors.conf)
      sp.sheng-fingerprint # qteesupplicant.service, sfsconfig.service, fprintd.service.d/*
      sp.sheng-thp # xiaomi-sheng-thp.service
      sp.sheng-mipps-auth # xiaomi-mipps-auth.service
      sp.sheng-charger-mode # xiaomi-charger-mode.service
    ]
    ++ lib.optional cfg.keyboard.enable sp.sheng-devauth;

    # sheng-fingerprint's drop-in expects the distro to provide fprintd.
    services.fprintd.enable = true;

    # The driver's own default is an FHS path, and a missing trusted app
    # surfaces as a misleading "Print was not found".
    systemd.services.fprintd.environment.FPC1553_TA_PATH = "/run/current-system/firmware/fpcsheng.elf";

    systemd.services = {
      "iio-sensor-proxy".wantedBy = [ "multi-user.target" ];
      "qteesupplicant".wantedBy = [ "multi-user.target" ];
      "sfsconfig".wantedBy = [ "qteesupplicant.service" ];
      "xiaomi-sheng-thp".wantedBy = [ "multi-user.target" ];
      "xiaomi-mipps-auth".wantedBy = [ "multi-user.target" ];
      "xiaomi-charger-mode".wantedBy = [ "multi-user.target" ];
      "sheng-devauth" = lib.mkIf cfg.keyboard.enable {
        wantedBy = [ "sysinit.target" ];
      };
    };

    # The aDSP writes temp.json back into this tree, so it has to be a mutable
    # copy rather than the store path fastrpc could point at directly.
    systemd.services."sheng-sensors-data" = {
      description = "Seed the Qualcomm SSC sensor registry fastrpc serves to the aDSP";
      before = [ "adsprpcd-sensorspd.service" ];
      requiredBy = [ "adsprpcd-sensorspd.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        src=${sp.sheng-sensors}/share/qcom
        if [ "$(cat /var/lib/qcom/.nix-source 2>/dev/null)" != "$src" ]; then
          mkdir -p /var/lib/qcom
          # The registry may itself be a persistence bind mount. Clear its
          # contents without trying to remove the mount point (EBUSY).
          find /var/lib/qcom -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
          cp -r --no-preserve=mode,ownership "$src"/. /var/lib/qcom/
          echo "$src" > /var/lib/qcom/.nix-source
        fi
      '';
    };

    systemd.user.services = lib.optionalAttrs cfg.keyboard.enable {
      "xiaomi-sheng-keyboard-helper-micmute" = {
        description = "Xiaomi keyboard mic-mute LED sync";
        after = [ "pipewire-pulse.service" ];
        unitConfig.ConditionPathExists = "/sys/class/leds/nanosic::micmute/brightness";
        serviceConfig = {
          Type = "simple";
          ExecStart = "${sp.sheng-keyboard-helper}/libexec/xiaomi-sheng-keyboard-helper --micmute";
        };
      };
    };

    systemd.services."xiaomi-sheng-keyboard-helper-angle" = lib.mkIf cfg.keyboard.enable {
      description = "Xiaomi keyboard fold-angle helper";
      wants = [ "adsprpcd-sensorspd.service" ];
      after = [ "adsprpcd-sensorspd.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type = "simple";
        ExecStart = "${sp.sheng-keyboard-helper}/libexec/xiaomi-sheng-keyboard-helper --angle";
        Restart = "on-failure";
      };
    };

    services.udev.packages = [
      sp.iio-sensor-proxy # 80-iio-sensor-proxy{,-libssc}.rules
      sp.sheng-sensors # 81-sheng-ssc-sensors.rules
      sp.sheng-fingerprint # 99-qcomtee-fpc.rules
      sp.sheng-mipps-auth # 90-xiaomi-mipps-auth.rules
    ];

    services.udev.extraRules = lib.mkIf cfg.keyboard.enable ''
      SUBSYSTEM=="misc", KERNEL=="nanosic_hinge*", ENV{keyboard_attached}=="1", TAG+="systemd", ENV{SYSTEMD_WANTS}+="xiaomi-sheng-keyboard-helper-angle.service"
      SUBSYSTEM=="input", ATTRS{name}=="Xiaomi Keyboard", TAG+="systemd", ENV{SYSTEMD_USER_WANTS}+="xiaomi-sheng-keyboard-helper-micmute.service"
      SUBSYSTEM=="leds", KERNEL=="nanosic::micmute", MODE="0666"
    '';

    environment.etc = lib.optionalAttrs cfg.pen.enable {
      "xdg/autostart/xiaomi-pen-status.desktop".source =
        "${sp.sheng-pen-status}/etc/xdg/autostart/xiaomi-pen-status.desktop";
    };

    environment.pathsToLink = [ "/share/alsa" ];
    # A union, not the sheng package alone: ALSA_CONFIG_UCM2 replaces the
    # search path rather than extending it, and hiding ucm2/lib makes UCM fail
    # silently -- every PCM present, zero sinks and sources.
    environment.sessionVariables.ALSA_CONFIG_UCM2 = "${
      pkgs.symlinkJoin {
        name = "alsa-ucm2-sheng";
        paths = [
          sp.alsa-ucm-sheng
          pkgs.alsa-ucm-conf
        ];
      }
    }/share/alsa/ucm2";
  };
}
