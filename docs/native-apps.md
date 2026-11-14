# Optional native desktop applications

The project exposes `chatgpt-native` and `antigravity-native` for
`aarch64-linux` from the pinned Nixpkgs. They use the Nixpkgs packages for
ChatGPT Desktop and Antigravity IDE, rather than the project's Flatpak
wrappers. These outputs do not add either application to the system image.

Both packages are unfree. The project imports its pinned Nixpkgs with unfree
packages enabled; a separate Nixpkgs import may have different settings.
The pinned ChatGPT package uses an official ARM64 OpenAI release, and the
Antigravity IDE package uses an official ARM64 Google release. Build success
and correct runtime behaviour on this device have not yet been verified.
NixOS is not in OpenAI's list of officially supported Linux distributions for
the ChatGPT preview; consult the vendor's Linux documentation for current
platform and feature limitations.

After booting a system and obtaining a checkout containing these outputs,
an individual user can install either application into their own profile:

```sh
cd /path/to/nixos-sheng
nix profile install .#chatgpt-native
nix profile install .#antigravity-native
```

These commands can download dependencies or trigger builds, possibly large
ones. Use the project's ARM64 CI or another suitable build host and cache when
needed; do not assume that an unfree package is present in a public binary
cache. These commands have not been run or validated on the tablet.

To remove an application from the user profile, first inspect its profile name
and then remove that exact name:

```sh
nix profile list
nix profile remove chatgpt-native
nix profile remove antigravity-native
```

Use the names displayed by `nix profile list` if they differ. Removing a
profile entry does not automatically remove personal application settings or
login data. A NixOS rebuild does not install these optional profile entries.

The legacy private Flatpak seed remains optional. Native LibreWolf is included
in the personal system image separately from these optional user-profile apps.
Its existing privacy defaults are unchanged; testing must establish whether
desired site logins persist, and users can change site-specific settings in the
browser. The system no longer forces `codex:` or
`antigravity-ide:` links to the legacy Flatpak desktop IDs; verify link handling
and desktop integration after installing the chosen native applications.
Neither the native packages nor URI handling, updates, login persistence,
extensions, or device access have been tested on the tablet.
