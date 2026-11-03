#!/usr/bin/env bash
# Read-only post-boot checks for one-time GRUB test; does not alter kernel or MOK.
set -euo pipefail
echo "=== BOOT REPRODUCTION REPORT ==="
printf 'BOOT_KERNEL=%s\n' "$(uname -r)"
printf 'SYSTEM_ARCH=%s\n' "$(uname -m)"
if mokutil --sb-state 2>&1 | grep -qx 'SecureBoot enabled'; then
  echo 'SECURE_BOOT=ENABLED'
else
  echo 'SECURE_BOOT=NOT_CONFIRMED'
fi
if grep -qw 'efi=noruntime' /proc/cmdline; then
  echo 'EFI_NORUNTIME=YES'
else
  echo 'EFI_NORUNTIME=NO'
fi
if test -d /sys/module/evdi; then
  echo 'EVDI_MODULE=LOADED'
else
  echo 'EVDI_MODULE=NOT_LOADED'
fi
if systemctl is-active --quiet displaylink-driver.service; then
  echo 'DISPLAYLINK=ACTIVE'
else
  echo 'DISPLAYLINK=NOT_ACTIVE'
fi
if systemctl is-active --quiet pd-mapper.service; then
  echo 'PD_MAPPER=ACTIVE'
else
  echo 'PD_MAPPER=NOT_ACTIVE'
fi
if systemctl --user is-active --quiet desktop-commander-remote.service; then
  echo 'REMOTE_AGENT=ACTIVE'
else
  echo 'REMOTE_AGENT=NOT_ACTIVE'
fi
if test -n "$(journalctl -k -b -o cat --no-pager -g 'secureboot mode unknown, no efi' -n 1 2>/dev/null)"; then
  echo 'KERNEL_EFI_INTEGRITY=UNKNOWN_NO_EFI'
else
  echo 'KERNEL_EFI_INTEGRITY=NO_UNKNOWN_NO_EFI_LOG_FOUND'
fi
if test -n "$(journalctl -k -b -o cat --no-pager -g 'UEFI:MokListRT' -n 1 2>/dev/null)"; then
  echo 'MOK_IMPORT_LOG=FOUND'
else
  echo 'MOK_IMPORT_LOG=NOT_FOUND'
fi
count_connected=0
count_dp_connected=0
for st in /sys/class/drm/card*-*/status; do
  test -r "$st" || continue
  if grep -qx 'connected' "$st"; then
    count_connected=$((count_connected + 1))
    case "$st" in *-DP-*) count_dp_connected=$((count_dp_connected + 1));; esac
  fi
done
printf 'DRM_CONNECTED_CONNECTORS=%s\n' "$count_connected"
printf 'DRM_CONNECTED_DP_CONNECTORS=%s\n' "$count_dp_connected"
echo 'NOTE=DRM connections are NOT proof of working external monitors'
echo 'NOTE=shim_validation_not_assumed_from_mokutil_alone'
