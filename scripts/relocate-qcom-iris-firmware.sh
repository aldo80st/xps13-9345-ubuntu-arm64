#!/usr/bin/env bash
# Correct a pd-mapper regression introduced when firmware was placed in the
# otherwise empty /lib/firmware/updates/.../xps13-9345 directory.
# Run with local policy authorization; does not touch Secure Boot or bootloader.
set -euo pipefail
expected='8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629'
src='/lib/firmware/updates/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn'
dst='/lib/firmware/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn'
jsn='/lib/firmware/qcom/x1e80100/dell/xps13-9345/adspr.jsn'
test "$(id -u)" -eq 0 || { echo 'Root authorization required' >&2; exit 1; }
grep -qi 'XPS 13 9345' /sys/class/dmi/id/product_name || { echo 'Wrong device' >&2; exit 1; }
test -r "$jsn" || { echo 'Base PD maps missing; refusing to modify' >&2; exit 1; }
if [ -e "$dst" ]; then
  printf '%s  %s\n' "$expected" "$dst" | sha256sum -c --status || { echo 'Unexpected destination firmware; refusing to overwrite' >&2; exit 1; }
else
  test -f "$src" || { echo 'Source firmware absent' >&2; exit 1; }
  printf '%s  %s\n' "$expected" "$src" | sha256sum -c --status || { echo 'Source checksum mismatch' >&2; exit 1; }
  install -o root -g root -m 0644 "$src" "$dst"
fi
printf '%s  %s\n' "$expected" "$dst" | sha256sum -c --status || { echo 'Destination verification failed; old copy preserved' >&2; exit 1; }
if [ -e "$src" ]; then
  printf '%s  %s\n' "$expected" "$src" | sha256sum -c --status || { echo 'Unexpected source content; refusing deletion' >&2; exit 1; }
  rm -- "$src"
fi
rmdir '/lib/firmware/updates/qcom/x1e80100/dell/xps13-9345' 2>/dev/null || true
rmdir '/lib/firmware/updates/qcom/x1e80100/dell' 2>/dev/null || true
rmdir '/lib/firmware/updates/qcom/x1e80100' 2>/dev/null || true
rmdir '/lib/firmware/updates/qcom' 2>/dev/null || true
echo 'FIRMWARE_RELOCATED_TO_BASE_AND_SHA256_VERIFIED'
systemctl reset-failed pd-mapper.service
systemctl start pd-mapper.service
if systemctl is-active --quiet pd-mapper.service; then echo 'PD_MAPPER_ACTIVE'; else echo 'PD_MAPPER_STILL_NOT_ACTIVE'; exit 3; fi
