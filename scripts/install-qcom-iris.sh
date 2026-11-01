#!/usr/bin/env bash
# Explicit local privilege required. Changes only one firmware path.
set -euo pipefail
test "$(uname -m)" = "aarch64" || { echo "ERROR: expected aarch64" >&2; exit 1; }
grep -qi 'XPS 13 9345' /sys/class/dmi/id/product_name || { echo "ERROR: wrong hardware model" >&2; exit 1; }
src="${XDG_CACHE_HOME:-$HOME/.cache}/xps13-9345-firmware/qcvss8380.mbn.candidate"
dst="/lib/firmware/updates/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn"
expected="8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629"
[ -f "$src" ] || { echo "Stage firmware first: bash scripts/stage-qcom-iris.sh" >&2; exit 1; }
printf '%s  %s\n' "$expected" "$src" | sha256sum -c --status || { echo "ERROR: hash mismatch; abort" >&2; exit 1; }
if [ -e "$dst" ]; then
  if printf '%s  %s\n' "$expected" "$dst" | sha256sum -c --status; then echo "Already installed; no changes"; exit 0; fi
  echo "ERROR: destination exists with a different hash; refusing to overwrite" >&2
  exit 1
fi
echo "Installing one SHA256-verified firmware file at: $dst"
sudo install -D -o root -g root -m 0644 "$src" "$dst"
printf '%s  %s\n' "$expected" "$dst" | sha256sum -c --status || { echo "ERROR: postinstall verification failed" >&2; exit 1; }
echo "Installed. Reboot to evaluate IRIS initialization and test actual video decoding."
echo "Rollback: verify matching SHA256 then sudo rm -- '$dst'; reboot."
