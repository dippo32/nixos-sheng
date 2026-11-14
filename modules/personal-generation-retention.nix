# Preserve system generations and their GC roots for manual rollback. The
# default extlinux limit stages up to ten generations; the personal U-Boot
# still boots the default directly and does not show a generation menu.
{ ... }:
{
  # Garbage collection removes only unreachable store paths. It does not pass
  # --delete-old or remove system or user profile generation links.
  nix.gc = {
    automatic = true;
    dates = [ "weekly" ];
    options = "";
  };
  systemd.services.nix-gc.serviceConfig = {
    CPUSchedulingPolicy = "idle";
    IOSchedulingClass = "idle";
  };
}
