#!/usr/bin/env bash
# Install one vendor-verified Dell Qualcomm IRIS firmware blob.
# Explicit local sudo authorization required. No Secure Boot changes.
set -euo pipefail
test "$(uname -m)" = "aarch64" || { echo "ERROR: expected aarch64" >&2; exit 1; }
grep -qi 'XPS 13 9345' /sys/class/dmi/id/product_name || { echo "ERROR: wrong hardware model" >&2; exit 1; }
src="${XDG_CACHE_HOME:-$HOME/.cache}/xps13-9345-firmware/qcvss8380.mbn.from-official-dell"
dst="/lib/firmware/updates/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn"
expected="8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629"
[ -f "$src" ] || { echo "ERROR: vendor-source firmware not staged. Run scripts/extract-official-qcom-iris.sh first" >&2; exit 1; }
printf '%s  %s\n' "$expected" "$src" | sha256sum --check --status || { echo "ERROR: staged firmware hash mismatch; abort" >&2; exit 1; }
if [ -e "$dst" ]; then
  if printf '%s  %s\n' "$expected" "$dst" | sha256sum --check --status; then echo "Already installed; no changes"; exit 0; fi
  echo "ERROR: destination exists with another hash; refusing to overwrite" >&2
  exit 1
fi
echo "Installing exactly one vendor-verified firmware file: $dst"
sudo install -D -o root -g root -m 0644 "$src" "$dst"
printf '%s  %s\n' "$expected" "$dst" | sha256sum --check --status || { echo "ERROR: post-install firmware hash mismatch" >&2; exit 1; }
echo "Firmware installed; reboot then check qcom-iris kernel logs and real hardware decoding."
echo "Rollback: verify matching SHA-256, sudo rm -- '$dst', reboot."
