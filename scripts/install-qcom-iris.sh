#!/usr/bin/env bash
# Install one Dell-verified IRIS firmware binary in the *base* firmware directory.
# IMPORTANT: never use the updates/ directory alone on this hardware:
# protection-domain-mapper may select it instead of base .jsn maps.
set -euo pipefail
test "$(uname -m)" = "aarch64" || { echo "ERROR: requires aarch64" >&2; exit 1; }
grep -qi 'XPS 13 9345' /sys/class/dmi/id/product_name || { echo "ERROR: different hardware model" >&2; exit 1; }
src="${XDG_CACHE_HOME:-$HOME/.cache}/xps13-9345-firmware/qcvss8380.mbn.from-official-dell"
dst="/lib/firmware/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn"
legacy="/lib/firmware/updates/qcom/x1e80100/dell/xps13-9345"
jsn="/lib/firmware/qcom/x1e80100/dell/xps13-9345/adspr.jsn"
expected="8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629"
if [ -d "$legacy" ]; then
  echo "ERROR: old updates/ directory present. This may shadow PD mapping; run scripts/relocate-qcom-iris-firmware.sh through local administrator authorization first." >&2
  exit 2
fi
[ -r "$jsn" ] || { echo "ERROR: expected base protection-domain maps are missing" >&2; exit 1; }
[ -f "$src" ] || { echo "ERROR: extract official Dell firmware first using scripts/extract-official-qcom-iris.sh" >&2; exit 1; }
printf '%s  %s\n' "$expected" "$src" | sha256sum --check --status || { echo "ERROR: firmware SHA-256 mismatch" >&2; exit 1; }
if [ -e "$dst" ]; then
  if printf '%s  %s\n' "$expected" "$dst" | sha256sum --check --status; then
    echo "Firmware already installed at safe location. No changes."
    exit 0
  fi
  echo "ERROR: unexpected existing destination; refusing to overwrite" >&2
  exit 1
fi
echo "Installing SHA-256 verified Dell firmware at the base firmware path"
sudo install -o root -g root -m 0644 "$src" "$dst"
printf '%s  %s\n' "$expected" "$dst" | sha256sum --check --status
echo "Firmware installed. After reboot verify qcom-iris initializes and real hardware decoding succeeds."
echo "Rollback: confirm expected SHA-256, then sudo rm -- '$dst'; reboot."
