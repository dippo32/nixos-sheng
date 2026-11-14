#!/usr/bin/env bash
# Exercise the actual workflow restore script with a fake Nix store and artifacts.
set -euo pipefail
cd "$(dirname "$0")/.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin" "$work/state" "$work/artifacts" "$work/runner"
export PATH="$work/bin:$PATH" MOCK_WORK="$work" MOCK_STATE="$work/state"
export RUNNER_TEMP="$work/runner" GITHUB_REPOSITORY=owner/repo GITHUB_REF_NAME=test GITHUB_RUN_ID=999
export MSYS_NO_PATHCONV=1

awk '
  /- name: Restore matching kernel closure/ { step=1; next }
  step && /        run: \|/ { script=1; next }
  script && /^      - name:/ { exit }
  script { sub(/^          /, ""); print }
' .github/workflows/build-personal-kde.yml > "$work/restore.sh"
test -s "$work/restore.sh"
bash -n "$work/restore.sh"
cd "$work"

cat > "$work/bin/nix" <<'EOF'
#!/usr/bin/env sh
case "$1 $2" in
  'eval --json') echo '["out","dev","modules"]' ;;
  'eval --raw')
    case "$3" in
      *.out.outPath) echo /nix/store/mock-out ;;
      *.dev.outPath) echo /nix/store/mock-dev ;;
      *.modules.outPath) echo /nix/store/mock-modules ;;
      *) exit 1 ;;
    esac ;;
  'path-info '*) test -f "$MOCK_STATE/${2##*/}" ;;
  *) exit 1 ;;
esac
EOF
cat > "$work/bin/jq" <<'EOF'
#!/usr/bin/env sh
cat >/dev/null
if [ "$1" = -r ]; then printf '%s\n' out dev modules; fi
EOF
cat > "$work/bin/gh" <<'EOF'
#!/usr/bin/env sh
case "$1 $2" in
  'run list')
    case " $* " in *' --branch test '*) echo 101 ;; esac ;;
  'api '*) echo 1 ;;
  'run download')
    while [ "$#" -gt 0 ]; do
      if [ "$1" = --dir ]; then mkdir -p "$2"; cp "$MOCK_WORK/artifacts/"* "$2/"; exit; fi
      shift
    done
    exit 1 ;;
  *) exit 1 ;;
esac
EOF
cat > "$work/bin/zstd" <<'EOF'
#!/usr/bin/env sh
cat "$2"
EOF
cat > "$work/bin/sudo" <<'EOF'
#!/usr/bin/env sh
exec "$@"
EOF
cat > "$work/bin/nix-store" <<'EOF'
#!/usr/bin/env sh
test "$1" = --import
while IFS= read -r name; do touch "$MOCK_STATE/$name"; done
EOF
chmod +x "$work/bin/"*

reset_case() {
  rm -rf "$work/state" "$work/artifacts" "$work/runner" seed-kernel
  mkdir -p "$work/state" "$work/artifacts" "$work/runner"
  printf '/nix/store/mock-out\n' > "$work/artifacts/kernel-path.txt"
}
manifest() {
  printf 'out\t/nix/store/mock-out\ndev\t/nix/store/mock-dev\nmodules\t/nix/store/mock-modules\n' > "$work/artifacts/kernel-outputs.txt"
}
checksums() {
  (cd "$work/artifacts" && sha256sum sheng-kernel-closure.nar.zst "$@" > SHA256SUMS)
}
run_case() {
  bash "$work/restore.sh" > "$work/log" 2>&1 || { cat "$work/log"; exit 1; }
}

reset_case
manifest
printf '%s\n' mock-out mock-dev mock-modules > "$work/artifacts/sheng-kernel-closure.nar.zst"
checksums kernel-outputs.txt kernel-path.txt
run_case
grep -q 'Restored all matching kernel outputs' "$work/log"

reset_case
printf '%s\n' mock-out > "$work/artifacts/sheng-kernel-closure.nar.zst"
checksums
run_case
grep -q 'Imported a partial legacy or incomplete closure' "$work/log"
! grep -q 'Restored all matching kernel outputs' "$work/log"

reset_case
manifest
printf '%s\n' mock-out > "$work/artifacts/sheng-kernel-closure.nar.zst"
checksums kernel-outputs.txt kernel-path.txt
run_case
grep -q 'Imported a partial legacy or incomplete closure' "$work/log"
! grep -q 'Restored all matching kernel outputs' "$work/log"

reset_case
manifest
printf 'wrong\n' >> "$work/artifacts/kernel-outputs.txt"
printf '%s\n' mock-out mock-dev mock-modules > "$work/artifacts/sheng-kernel-closure.nar.zst"
checksums kernel-outputs.txt kernel-path.txt
run_case
grep -q 'Kernel output manifest does not match' "$work/log"
! test -e "$work/state/mock-out"

reset_case
manifest
printf '%s\n' mock-out mock-dev mock-modules > "$work/artifacts/sheng-kernel-closure.nar.zst"
checksums kernel-outputs.txt kernel-path.txt
printf 'tampered\n' >> "$work/artifacts/sheng-kernel-closure.nar.zst"
run_case
grep -q 'Kernel closure checksum failed' "$work/log"
! test -e "$work/state/mock-out"

reset_case
touch "$work/state/mock-out" "$work/state/mock-dev" "$work/state/mock-modules"
run_case
grep -q 'All selected kernel outputs are already in the store' "$work/log"

echo 'Kernel closure restore mock tests passed.'
