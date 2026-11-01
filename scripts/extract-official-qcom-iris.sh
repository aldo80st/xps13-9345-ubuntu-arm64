#!/usr/bin/env bash
# Extract only video subsystem firmware from a SHA256-verified official Dell
# Windows ARM64 installer. Never execute the Windows package. No root needed.
set -euo pipefail
if [ "$#" -ne 1 ]; then echo "Usage: bash $0 /path/to/Qualcomm-Adreno-...KPF2C...EXE" >&2; exit 2; fi
package="$1"
test -f "$package" || { echo "Package file not found" >&2; exit 1; }
expected_pkg='83ca322727b86d80042fe06824cc4dcef705bab511d31aca4a25bbf741ee5d91'
expected_fw='8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629'
printf '%s  %s\n' "$expected_pkg" "$package" | sha256sum --check --status || { echo "ERROR: Dell installer checksum mismatch; abort" >&2; exit 1; }
cache="${XDG_CACHE_HOME:-$HOME/.cache}/xps13-9345-firmware"
mkdir -p "$cache"
if command -v 7zz >/dev/null 2>&1; then
  sevenzip="$(command -v 7zz)"
else
  command -v apt >/dev/null && command -v dpkg-deb >/dev/null || { echo "Requires 7zz, or apt + dpkg-deb for user-only extraction" >&2; exit 1; }
  tooling="$cache/tooling"
  mkdir -p "$tooling"
  if [ ! -x "$tooling/unpacked/usr/lib/7zip/7zz" ]; then
    (cd "$tooling"; apt download 7zip-standalone; deb="$(find . -maxdepth 1 -name '7zip-standalone*.deb' | head -n1)"; test -n "$deb"; dpkg-deb -x "$deb" unpacked)
  fi
  sevenzip="$tooling/unpacked/usr/lib/7zip/7zz"
fi
tmp="$(mktemp -d "$cache/extraction.XXXXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT
"$sevenzip" x -y -o"$tmp" "$package" >/dev/null
matches=()
while IFS= read -r -d '' f; do matches+=("$f"); done < <(find "$tmp" -type f -name 'qcvss8380.mbn' -print0)
if [ "${#matches[@]}" -ne 1 ]; then echo "Expected one qcvss8380.mbn; found ${#matches[@]}; abort" >&2; exit 1; fi
printf '%s  %s\n' "$expected_fw" "${matches[0]}" | sha256sum --check --status || { echo "ERROR: extracted firmware checksum mismatch" >&2; exit 1; }
install -m 0644 "${matches[0]}" "$cache/qcvss8380.mbn.from-official-dell"
echo "Verified original Dell firmware staged at:"
echo "$cache/qcvss8380.mbn.from-official-dell"
echo "SHA-256: $expected_fw"
echo "NO kernel files changed."
