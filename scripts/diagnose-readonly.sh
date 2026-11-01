#!/usr/bin/env bash
# Read-only checks. Deliberately omits machine name, serial, IP, MAC and full logs.
set -uo pipefail
echo "=== XPS ARM64 stability check: $(date -u +%F) UTC ==="
echo "kernel: $(uname -r), architecture: $(uname -m)"
echo "OS: $(. /etc/os-release; echo "$PRETTY_NAME")"
printf 'model: '; cat /sys/class/dmi/id/product_name 2>/dev/null || true
printf 'BIOS: '; cat /sys/class/dmi/id/bios_version 2>/dev/null || true
echo "--- Secure Boot ---"
if command -v mokutil >/dev/null; then mokutil --sb-state 2>&1 | head -n 2; fi
echo "--- Failed services (names only) ---"
systemctl --failed --no-legend --no-pager --plain 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i ~ /\.service$/) {print $i;break}}' | head -n 20
echo "--- DisplayLink module ---"
if command -v modinfo >/dev/null; then
  modinfo evdi 2>/dev/null | grep -E '^(vermagic|sig_hashalgo):' || echo "evdi not available"
  [ -n "$(modinfo -F signer evdi 2>/dev/null)" ] && echo "evdi signer: present (name redacted)"
fi
if command -v dkms >/dev/null; then dkms status 2>/dev/null | grep '^evdi/' || true; fi
echo "--- IRIS candidate file presence ---"
for f in /lib/firmware/updates/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn /lib/firmware/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn; do
  if [ -f "$f" ]; then echo "present: firmware file"; sha256sum "$f" | cut -d' ' -f1; else echo "missing: $f"; fi
done
echo "--- IRIS missing firmware errors (count) ---"
journalctl -k -b --no-pager 2>/dev/null | grep -c 'qcvss8380.mbn.*failed' || true
echo "--- Audio enumeration (no process names) ---"
if command -v wpctl >/dev/null; then wpctl status 2>/dev/null | sed -n '/^Audio$/,/^Video$/p' | sed -n '/^Audio$/,/Streams:/p' | head -n 20; fi
echo "--- Wi-Fi current state (no SSID) ---"
nmcli -t -f TYPE,STATE device 2>/dev/null | grep '^wifi:' | sort -u || true
echo "--- Memory ---"
free -h | head -n 2
echo "=== End (never publish raw personal logs) ==="
