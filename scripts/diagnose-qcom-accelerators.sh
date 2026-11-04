#!/usr/bin/env bash
# Read-only Qualcomm accelerator inventory: no sudo, no firmware writes.
set -euo pipefail

printf 'Qualcomm accelerator diagnostic | %s | %s\n' "$(uname -m)" "$(uname -r)"
printf '\n== Adreno platform device ==\n'
found=0
for device in /sys/bus/platform/drivers/adreno/*.gpu; do
  [[ -d "$device" ]] || continue
  for freq in "$device"/devfreq/*; do
    [[ -r "$freq/cur_freq" ]] || continue
    found=1
    printf 'GPU driver=adreno; devfreq=%s\n' "$(basename "$freq")"
    for field in cur_freq min_freq max_freq; do
      value="$(cat "$freq/$field" 2>/dev/null || true)"
      if [[ "$value" =~ ^[0-9]+$ ]]; then
        awk -v field="$field" -v value="$value" 'BEGIN {printf "%s: %.0f MHz\n", field, value / 1000000}'
      fi
    done
  done
done
if (( found == 0 )); then echo 'No Adreno devfreq policy detected'; fi

printf '\n== GPU thermal sensors (not utilization) ==\n'
for path in /sys/class/hwmon/hwmon*; do
  [[ -r "$path/name" && -r "$path/temp1_input" ]] || continue
  name="$(cat "$path/name")"
  [[ "$name" =~ ^gpuss_[0-9]+_thermal$ ]] || continue
  value="$(cat "$path/temp1_input")"
  awk -v name="$name" -v value="$value" 'BEGIN {printf "%-23s %.1f C\n",name,value/1000}'
done

printf '\n== Qualcomm compute DSP (not NPU load) ==\n'
for path in /sys/class/remoteproc/remoteproc*; do
  [[ -r "$path/name" && -r "$path/state" ]] || continue
  name="$(cat "$path/name")"
  [[ "$name" == cdsp ]] || continue
  printf 'Compute DSP: %s; state=%s\n' "$name" "$(cat "$path/state")"
done
for path in /dev/fastrpc-cdsp /dev/fastrpc-cdsp-secure; do
  [[ -e "$path" ]] && echo "FastRPC endpoint: $(basename "$path") present"
done

printf '\n== NSP thermal domains (not validated as NPU load) ==\n'
for path in /sys/class/hwmon/hwmon*; do
  [[ -r "$path/name" && -r "$path/temp1_input" ]] || continue
  name="$(cat "$path/name")"
  [[ "$name" =~ ^nsp[0-9]+_thermal$ ]] || continue
  value="$(cat "$path/temp1_input")"
  awk -v name="$name" -v value="$value" 'BEGIN {printf "%-23s %.1f C\n",name,value/1000}'
done

printf '\n== DRM accelerator support ==\n'
if compgen -G '/sys/class/accel/accel*' >/dev/null; then
  echo 'DRM accel devices are present; inspect driver before interpreting any metric.'
else
  echo 'No /sys/class/accel/accelN devices. Resources 51 cannot list a Qualcomm NPU.'
fi
echo 'No synthetic GPU/NPU utilization, TOPS, VRAM or NPU memory values are reported.'
