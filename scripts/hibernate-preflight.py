#!/usr/bin/env python3
"""Unprivileged read-only ARM64 hibernation readiness checks.

No system changes, raw cmdline, swap path, UUID, serial, or user information
are returned. Readiness is not evidence that resume actually works.
"""
import argparse
import json
from pathlib import Path
import platform
import re


def _read(root: Path, relative: str) -> str | None:
    try:
        return (root / relative).read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return None


def _config_flag(raw: str | None, key: str) -> bool | None:
    if raw is None:
        return None
    if re.search(rf"(?m)^{re.escape(key)}=y\s*$", raw):
        return True
    if re.search(rf"(?m)^# {re.escape(key)} is not set\s*$", raw):
        return False
    return None


def _swap_total_kib(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    lines = raw.strip().splitlines()
    if not lines[0].startswith("Filename"):
        return None
    total = 0
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 5:
            return None
        try:
            total += int(parts[2])
        except ValueError:
            return None
    return total


def _memory_kib(raw: str | None) -> int | None:
    if raw is None:
        return None
    match = re.search(r"(?m)^MemTotal:\s+(\d+)\s+kB", raw)
    return int(match.group(1)) if match else None


def _noruntime_configured(raw: str | None) -> bool | None:
    if raw is None:
        return None
    return any("efi=noruntime" in line for line in raw.splitlines()
               if line.strip() and not line.lstrip().startswith("#"))


def inspect(root: Path, kernel: str) -> dict:
    """Inspect a host or filesystem fixture without executing any commands."""
    valid_kernel = bool(re.fullmatch(r"[A-Za-z0-9.+_~-]{1,100}", kernel))
    config = _read(root, f"boot/config-{kernel}") if valid_kernel else None
    states = _read(root, "sys/power/state")
    cmdline = _read(root, "proc/cmdline")
    grub = _read(root, "etc/default/grub.d/ubuntu-x1e-settings.cfg")
    bios = _read(root, "sys/class/dmi/id/bios_version")
    model = _read(root, "sys/class/dmi/id/product_name")
    bios_value = bios.strip() if bios else None

    return {
        "kernel": kernel if valid_kernel else "unreported",
        "kernel_hibernation": _config_flag(config, "CONFIG_HIBERNATION"),
        "arch_hibernation_possible": _config_flag(config, "CONFIG_ARCH_HIBERNATION_POSSIBLE"),
        "disk_state": ("disk" in states.split()) if states and states.strip() else None,
        "mem_kib": _memory_kib(_read(root, "proc/meminfo")),
        "swap_kib": _swap_total_kib(_read(root, "proc/swaps")),
        "efi_noruntime_active": ("efi=noruntime" in cmdline.split()) if cmdline is not None else None,
        "efi_noruntime_configured": _noruntime_configured(grub),
        "bios_version": bios_value if bios_value and re.fullmatch(r"\d+(?:\.\d+){1,3}", bios_value) else None,
        "model_family": "Dell XPS 13 9345" if model and model.strip() == "XPS 13 9345" else "unknown_or_other",
        "dracut_binary_present": (root / "usr/bin/dracut").exists(),
    }


def assess(observation: dict) -> dict:
    """Fail closed and distinguish unsupported kernel from unmeasured inputs."""
    blocked = []
    warnings = []
    if observation["kernel_hibernation"] is False:
        blocked.append("kernel_config_disabled")
    if observation["disk_state"] is False:
        blocked.append("disk_state_unavailable")
    if observation["swap_kib"] == 0:
        blocked.append("no_swap")
    ram, swap = observation["mem_kib"], observation["swap_kib"]
    if ram is not None and swap is not None and 0 < swap < ram:
        warnings.append("swap_below_ram_conservative_target")
    if observation["efi_noruntime_active"] is True:
        warnings.append("efi_runtime_disabled_at_boot")
    cfg = observation["efi_noruntime_configured"]
    active = observation["efi_noruntime_active"]
    if cfg is not None and active is not None and cfg != active:
        warnings.append("grub_and_boot_efi_flags_differ")
    if observation["dracut_binary_present"] is False:
        warnings.append("dracut_binary_not_found")

    critical = ("kernel_hibernation", "disk_state", "swap_kib", "mem_kib")
    if blocked:
        status = "BLOCKED"
    elif any(observation[key] is None for key in critical):
        status = "UNKNOWN"
    else:
        status = "READY_FOR_EVALUATION"

    return {"status": status, "blockers": blocked, "warnings": warnings,
            "observed": observation, "note": "No prueba hibernacion ni restauracion real."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="fixture root (default /)")
    parser.add_argument("--kernel", default=platform.release(), help="kernel config version")
    parser.add_argument("--json", action="store_true", help="machine-readable redacted output")
    args = parser.parse_args()
    result = assess(inspect(args.root, args.kernel))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Hibernation readiness: {result['status']}")
        print("Blockers:", ", ".join(result["blockers"]) or "none")
        print("Warnings:", ", ".join(result["warnings"]) or "none")
        print(result["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
