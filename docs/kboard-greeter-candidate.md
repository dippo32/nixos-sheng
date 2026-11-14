# KBoard greeter candidate

This experimental personal profile selects the same native KBoard package for
the SDDM KWin input method and for the system desktop default. The package is
part of the system generation rather than relying on the personal user's
profile. A greeter-only wrapper explicitly sets `XDG_CONFIG_HOME=/etc/xdg`,
so its KBoard reads the system kboardrc without depending on SDDM's
`XDG_CONFIG_DIRS`. This system file is read-only to the SDDM user. The system
KBoard configuration supplies silent keys and automatic split defaults; the
logged-in user can override them through their own configuration. Maliit is no
longer explicitly installed by this profile.

Evaluation does not establish that the SDDM user can start KBoard, that a
password can be entered on the greeter or on the lock screen, or that the
system defaults are honored by the SDDM session. Test those on the tablet
before treating this profile as ready for routine use. Preserve another tested
access path and working boot generation until the login test passes.

The personal-only module replaces exactly one line in the pinned upstream
Plasma module to omit Plasma Keyboard from `environment.systemPackages`.
The replacement checks that the expected line occurs exactly once and fails
evaluation on upstream changes; each nixpkgs update needs review. It leaves
all other module behavior and the non-personal configurations unchanged.
This does not remove old generations or their store paths; keep the known-good
generation for rollback. `qtvirtualkeyboard` remains because KWin, Plasma,
and SDDM reference it as a runtime dependency. Omitting the Plasma Keyboard
from the system package list alone does not prove the store closure is clear.
