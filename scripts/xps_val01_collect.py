#!/usr/bin/env python3
"""XPS-VAL-01: one-shot, privacy-by-allowlist hardware inventory (no sudo or writes).

Without --root the script reads existing sysfs and a few bounded commands.
--root points to a synthetic fixture with sys/, etc/ and proc/ directories.
No raw logs, interfaces, addresses, serials, paths, or personal IDs are emitted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import platform
import re
import subprocess
from typing import Any

SCHEMA = "xps-val01.v1"
ALLOWED_MODULES = ("evdi", "qcom_iris", "dell_xps_ec", "qcom_spmi_adc_tm5_gen3")
ERROR_KINDS = {
    "dell_ec": r"dell[-_]xps[-_]ec",
    "adc5": r"qcom[-_]spmi[-_]adc5[-_]gen3",
    "pmic_glink": r"pmic[-_]glink",
    "gpu": r"\b(adreno|msm.*gpu)\b",
    "watchdog": r"watchdog",
    "panic": r"kernel panic",
}


def read_text(path: Path, limit: int = 256) -> str | None:
    try:
        if not path.is_file():
            return None
        raw = path.read_text(encoding="utf-8", errors="replace")[:limit].strip()
        return raw or None
    except (OSError, UnicodeError):
        return None


def cmd(*args: str, seconds: float = 3.0) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=seconds,
                                check=False, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                                                  "LC_ALL": "C"})
        if result.returncode == 0:
            return result.stdout[:250000]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def integer(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def safe_enum(value: str | None, valid: set[str]) -> str | None:
    return value if value in valid else None


def kind_of_network(name: str) -> str | None:
    if name.startswith(("wl", "wlan")):
        return "wifi"
    if name.startswith(("en", "eth")):
        return "ethernet"
    return None


def read_release(root: Path) -> str | None:
    value = read_text(root / "etc/os-release", 3000) or ""
    match = re.search(r'^PRETTY_NAME="?(.*?)"?$', value, re.M)
    if not match:
        return None
    # No arbitrary OS metadata is copied to the evidence bundle.
    text = match.group(1)
    return text if re.fullmatch(r"[a-zA-Z0-9 ._()+-]{1,80}", text) else None


def inventory(root: Path, allow_commands: bool) -> dict[str, Any]:
    sys = root / "sys"
    release = platform.release() if allow_commands else None
    policy = []
    for p in sorted((sys / "devices/system/cpu/cpufreq").glob("policy*")):
        if not p.name[6:].isdigit():
            continue
        policy.append({
            "cluster": p.name,
            "driver": safe_enum(read_text(p / "scaling_driver"), {"scmi", "cppc_cpufreq", "qcom-cpufreq-hw", "acpi-cpufreq"}),
            "governor": safe_enum(read_text(p / "scaling_governor"), {"ondemand", "schedutil", "powersave", "performance", "conservative"}),
            "min_khz": integer(read_text(p / "scaling_min_freq")),
            "max_khz": integer(read_text(p / "scaling_max_freq")),
        })

    supply = []
    for p in sorted((sys / "class/power_supply").glob("*")):
        kind = read_text(p / "type")
        if kind not in {"Mains", "USB", "USB_C", "Battery", "Wireless"}:
            continue
        supply.append({
            "type": kind,
            "online": integer(read_text(p / "online")),
            "status": safe_enum(read_text(p / "status"),
                                {"Charging", "Not charging", "Discharging", "Full", "Unknown"}),
        })
    screens = []
    for p in sorted((sys / "class/drm").glob("card*-*")):
        status = read_text(p / "status")
        if status != "connected":
            continue
        # Emit only a generic output class and whitelisted mode, never EDID/serial.
        output = p.name.split("-", 1)[1] if "-" in p.name else "other"
        cls = "internal" if output.startswith("eDP") else "external"
        mode = read_text(p / "mode")
        if mode and not re.fullmatch(r"\d{2,5}x\d{2,5}", mode):
            mode = None
        screens.append({"class": cls, "mode": mode})

    video = []
    for p in sorted((sys / "class/video4linux").glob("video*")):
        name = read_text(p / "name")
        if name in ("qcom-iris-decoder", "qcom-iris-encoder"):
            video.append(name)

    network: dict[str, dict[str, int]] = {}
    for p in sorted((sys / "class/net").glob("*")):
        kind = kind_of_network(p.name)
        if not kind:
            continue
        totals = network.setdefault(kind, {"interfaces": 0, "rx_packets": 0, "rx_dropped": 0,
                                           "rx_errors": 0})
        totals["interfaces"] += 1
        for key in ("rx_packets", "rx_dropped", "rx_errors"):
            totals[key] += integer(read_text(p / "statistics" / key)) or 0

    thermal = []
    for p in sorted((sys / "class/thermal").glob("thermal_zone*")):
        temp = integer(read_text(p / "temp"))
        if temp is None or not (-40000 <= temp <= 150000):
            continue
        # No bespoke names; avoid identifying device-private sensor strings.
        thermal.append(temp / 1000)
    power_profile = (cmd("powerprofilesctl", "get") or "").strip() if allow_commands else None
    modules = {m: (sys / "module" / m).exists() for m in ALLOWED_MODULES}
    # lsusb -d checks for the vendor/device only; never records bus/device or serial.
    dock = None
    if allow_commands:
        dock = bool(cmd("lsusb", "-d", "17e9:6006"))
    journal_counts = None
    if allow_commands:
        raw = cmd("journalctl", "-k", "-b", "--no-pager", "-p", "warning", seconds=4.0)
        if raw is not None:
            journal_counts = {name: len(re.findall(pattern, raw, flags=re.I)) for name, pattern in ERROR_KINDS.items()}

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    bios = read_text(sys / "class/dmi/id/bios_version")
    if bios and not re.fullmatch(r"[0-9A-Za-z._-]{1,30}", bios):
        bios = None
    return {
        "schema": SCHEMA,
        "captured_utc": now,
        "classification": "OBSERVADO",
        "source": "sysfs + bounded tools" if allow_commands else "fixture/sysfs only",
        "os": {"release": read_release(root), "kernel": release, "architecture": platform.machine() if allow_commands else None},
        "hardware": {"model": "Dell XPS 13 9345" if "9345" in (read_text(sys / "class/dmi/id/product_name") or "") else "unknown",
                     "bios": bios},
        "cpu": {"policies": policy},
        "power": {"profile": safe_enum(power_profile, {"balanced", "power-saver", "performance"}),
                  "supplies": supply},
        "display": {"connected": screens, "d6000_present": dock},
        "video": {"iris_devices": sorted(set(video)),
                  "chrome_vaapi_validated": False},
        "thermal": {"valid_sensors": len(thermal),
                    "min_c": min(thermal) if thermal else None,
                    "max_c": max(thermal) if thermal else None},
        "modules": modules,
        "network": network,
        "kernel_warning_keyword_counts": journal_counts,
        "limitations": [
            "Snapshot does not establish cause of reboot, throttling, media stutter or stable hardware behavior.",
            "Kernel log patterns are counters, not proof of faults or attribution.",
            "No raw journal, serial, SSID, IP, MAC, UID, paths, or service names exported.",
            "Does not change kernel, firmware, thermal controls, boot settings, or network routes.",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("/"),
                   help="root of synthetic fixture (requires --no-commands)")
    p.add_argument("--no-commands", action="store_true",
                   help="sysfs-only snapshot, no external commands")
    args = p.parse_args()
    if args.root != Path("/") and not args.no_commands:
        p.error("fixture --root requires --no-commands")
    try:
        result = inventory(args.root, not args.no_commands)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (PermissionError, OSError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "ERROR", "kind": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
