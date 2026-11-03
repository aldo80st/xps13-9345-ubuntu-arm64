#!/usr/bin/env bash
set -euo pipefail

echo '=== Sistema ==='
uname -r
uname -m
if command -v resources >/dev/null 2>&1; then resources --version; fi

echo '=== Topologia (idioma estandar) ==='
LC_ALL=C lscpu | grep -E 'Architecture:|Vendor ID:|Model name:|CPU\(s\):|Thread\(s\) per core:|Core\(s\) per (socket|cluster):|Cluster\(s\):|Socket\(s\):|CPU max MHz:' || true

echo '=== Sensores de CPU Qualcomm ==='
found=0
for dir in /sys/class/hwmon/hwmon*; do
  [[ -d "$dir" && -r "$dir/name" && -r "$dir/temp1_input" ]] || continue
  name=$(cat "$dir/name")
  if [[ "$name" =~ ^cpuss[0-9]+_(top|btm)_thermal$ ]]; then
    temp=$(cat "$dir/temp1_input")
    awk -v sensor="$name" -v v="$temp" 'BEGIN { printf "%-25s %.1f °C\n", sensor, v/1000 }'
    found=1
  fi
done
if (( found == 0 )); then echo 'No se encontraron sensores cpuss en hwmon'; fi

echo '=== Politicas cpufreq ==='
if [[ -d /sys/devices/system/cpu/cpufreq/policy0 ]]; then
  for policy in /sys/devices/system/cpu/cpufreq/policy*; do
    printf '%s ' "$(basename "$policy")"
    if [[ -r "$policy/scaling_driver" ]]; then cat "$policy/scaling_driver"; else echo N/A; fi
  done
else
  echo 'No existen politicas cpufreq'
fi

echo '=== Modulo SCMI CPUFreq (solo lectura) ==='
if [[ -x /usr/sbin/modinfo ]]; then
  /usr/sbin/modinfo -F filename scmi-cpufreq 2>/dev/null || echo 'No disponible'
else
  echo 'modinfo no disponible'
fi
if grep -q '^scmi_cpufreq ' /proc/modules; then
  echo 'scmi_cpufreq: cargado'
else
  echo 'scmi_cpufreq: no detectado en /proc/modules'
fi
