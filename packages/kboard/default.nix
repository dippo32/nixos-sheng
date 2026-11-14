# Native, optional KWin input method. No installer or user settings are run.
{
  lib,
  stdenv,
  fetchurl,
  cmake,
  ninja,
  pkg-config,
  dbus,
  writableTmpDirAsHomeHook,
  kdePackages,
  qt6,
  wayland,
  wayland-protocols,
  libxkbcommon,
  hunspell,
  hunspellDicts,
  sdl3,
  systemd,
}:
let
  whisper = fetchurl {
    url = "https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v1.9.4.tar.gz";
    hash = "sha256-V+KAzuN1qwJCW4Bq1RRrmfbrk1fjwrMTV8imry4uRK4=";
  };
in
stdenv.mkDerivation {
  pname = "kboard";
  version = "0.1.0-unstable-2026-11-03";
  src = fetchurl {
    name = "kboard-source.tar.gz";
    url = "https://codeload.github.com/DevL0rd/KBoard/tar.gz/dba54380765fe223036a70c74807340cde53e572";
    hash = "sha256-dWSjyFBfvmuWelNT0aAmV5JTj/p8Z5+tGu7csVu62Yo=";
  };

  patches = [ ./privacy-defaults.patch ./hunspell-path.patch ./landscape-split.patch ];

  postPatch = ''
    substituteInPlace src/typing/localeresolver.cpp \
      --replace-fail @KBOARD_HUNSPELL_DEFAULT@ ${hunspellDicts.en_US}/share/hunspell
  '';

  nativeBuildInputs = [ cmake ninja pkg-config dbus kdePackages.extra-cmake-modules qt6.wrapQtAppsHook ];
  nativeCheckInputs = [ writableTmpDirAsHomeHook ];
  buildInputs = [
    qt6.qtbase qt6.qtdeclarative qt6.qtwayland qt6.qtmultimedia qt6.qttools
    kdePackages.kconfig kdePackages.kcoreaddons kdePackages.ki18n
    kdePackages.kguiaddons kdePackages.kwindowsystem kdePackages.kdbusaddons
    kdePackages.kirigami kdePackages.kcrash kdePackages.kservice
    kdePackages.qqc2-desktop-style
    wayland wayland-protocols libxkbcommon hunspell sdl3 systemd
  ];

  # Supply the fixed upstream whisper source locally: CMake must not download
  # during the sandboxed build. Native ARM builds do not enable x86 AVX flags.
  preConfigure = ''
    mkdir -p "$TMPDIR/kboard-whisper"
    tar -xf ${whisper} -C "$TMPDIR/kboard-whisper" --strip-components=1
    cmakeFlagsArray+=("-DFETCHCONTENT_SOURCE_DIR_WHISPER_CPP=$TMPDIR/kboard-whisper")
  '';
  cmakeFlags = [ "-DKBOARD_BUNDLED_WHISPER=ON" "-DKBOARD_WERROR=OFF" ];
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    export QT_QPA_PLATFORM=offscreen
    for test_name in testkeylayout clipboardhistorytest kboard-typing-predictiontest; do
      ctest --show-only | grep -Eq "Test +#[0-9]+: +$test_name$"
    done
    dbus-run-session --config-file=${dbus}/share/dbus-1/session.conf -- ctest --no-tests=error --verbose -R '^(testkeylayout|clipboardhistorytest|kboard-typing-predictiontest)$' | tee "$TMPDIR/kboard-check.log"
    if grep -Eq 'SKIP.*(private D-Bus session|isolated session)' "$TMPDIR/kboard-check.log"; then
      echo 'Clipboard D-Bus isolation test was skipped' >&2
      exit 1
    fi
    runHook postCheck
  '';
  postInstall = ''
    test -x "$out/bin/kboard"
    test -x "$out/bin/kboard-settings"
    test -f "$out/share/applications/org.devl0rd.kboard.desktop"
    grep -q '^X-KDE-Wayland-VirtualKeyboard=true$' "$out/share/applications/org.devl0rd.kboard.desktop"
  '';
  meta = {
    description = "Native Plasma Wayland keyboard with split layout";
    homepage = "https://github.com/DevL0rd/KBoard";
    license = lib.licenses.gpl3Only;
    platforms = [ "aarch64-linux" ];
    mainProgram = "kboard";
  };
}
