#!/usr/bin/env bash
# Download a Dell-derived, third-party-hosted *candidate* to personal cache.
# Do not redistribute firmware binaries. No privilege or system modification.
set -euo pipefail
test "$(uname -m)" = "aarch64" || { echo "ERROR: expected aarch64" >&2; exit 1; }
expected="8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629"
cache="${XDG_CACHE_HOME:-$HOME/.cache}/xps13-9345-firmware"
url="https://raw.githubusercontent.com/valpackett/firmware-dell-qcom/trunk/qcom/x1e80100/dell/latitude-7455/qcvss8380.mbn.zst"
command -v curl >/dev/null && command -v zstd >/dev/null || { echo "Requires curl and zstd" >&2; exit 1; }
mkdir -p "$cache"
tmp="$(mktemp "$cache/download.XXXXXX")"
raw="$(mktemp "$cache/firmware.XXXXXX")"
trap 'rm -f "$tmp" "$raw"' EXIT
curl --fail --location --silent --show-error --max-time 60 "$url" -o "$tmp"
zstd -d -c "$tmp" > "$raw"
printf '%s  %s\n' "$expected" "$raw" | sha256sum -c --status || { echo "ERROR: hash mismatch" >&2; exit 1; }
chmod 0644 "$raw"
mv -f "$raw" "$cache/qcvss8380.mbn.candidate"
echo "Verified and staged: $cache/qcvss8380.mbn.candidate"
echo "SHA256: $expected"
echo "NOT installed into kernel firmware paths."
