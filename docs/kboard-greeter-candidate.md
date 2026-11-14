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

Plasma Keyboard and Qt Virtual Keyboard remain dependencies: the pinned
NixOS Plasma module includes both in its required packages and Qt Virtual
Keyboard is also among SDDM's extra packages. The Plasma `excludePackages`
option filters optional packages, not these required ones. Removing their
package references requires a separately tested change to the Plasma module
and dependency closure; this candidate does not claim to remove them.
