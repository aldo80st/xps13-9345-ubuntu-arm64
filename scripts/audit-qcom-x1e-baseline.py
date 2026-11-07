#!/usr/bin/env python3
"""Read-only gate for comparing installed generic and Canonical qcom-x1e configs.

This is NOT a hibernate-resume test and never authorizes installing/booting.
"""
import argparse
import json
from pathlib import Path
import re
import sys

CRITICAL = (
    "HIBERNATION",
    "SUSPEND",
    "ARCH_HIBERNATION_POSSIBLE",
    "ARM_SCMI_CPUFREQ",
    "PCIE_QCOM",
    "QCOM_SMP2P",
    "QCOM_PDC",
    "SWAP",
    "CPU_FREQ",
    "PM_SLEEP",
    "HOTPLUG_CPU",
)
OPTIONAL = ("EC_DELL_XPS",)
CONFIG_VALUE = re.compile(r"^CONFIG_([A-Z0-9_]+)=([^\s]+)$")
DISABLED = re.compile(r"^# CONFIG_([A-Z0-9_]+) is not set$")
RELEASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,127}$")


class InvalidConfig(ValueError):
    pass


def parse_config(path: Path) -> dict:
    """Parse Kconfig booleans; fail closed on ambiguous/missing critical keys."""
    try:
        if not path.is_file() or path.stat().st_size > 6_000_000:
            raise InvalidConfig("MISSING_OR_OVERSIZED_CONFIG")
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise InvalidConfig("UNREADABLE_CONFIG") from error
    symbols = {}
    tracked = set(CRITICAL) | set(OPTIONAL)
    for raw in content.splitlines():
        line = raw.strip()
        positive = CONFIG_VALUE.fullmatch(line)
        negative = DISABLED.fullmatch(line)
        if positive:
            key, value = positive.group(1), positive.group(2)
        elif negative:
            key, value = negative.group(1), "n"
        else:
            continue
        if key not in tracked:
            continue
        if value not in ("y", "m", "n"):
            raise InvalidConfig("INVALID_SYMBOL_VALUE")
        if key in symbols:
            raise InvalidConfig("DUPLICATE_SYMBOL")
        symbols[key] = value
    if set(CRITICAL) - set(symbols):
        raise InvalidConfig("MISSING_CRITICAL_SYMBOL")
    return {key: symbols.get(key, "UNKNOWN") for key in (*CRITICAL, *OPTIONAL)}


def evaluate(current: dict, candidate: dict, release: str) -> dict:
    blockers = []
    if candidate["HIBERNATION"] != "y":
        blockers.append("HIBERNATION_NOT_ENABLED")
    for key in CRITICAL:
        if key == "HIBERNATION":
            continue
        if current[key] in ("y", "m") and candidate[key] == "n":
            blockers.append("REGRESSION_" + key)
    return {
        "status": "NO_GO" if blockers else "REVIEW_REQUIRED",
        "candidate_release": release,
        "blockers": blockers,
        "boot_authorized": False,
        "device_restore_verified": False,
        "observed": {"current": current, "candidate": candidate},
        "note": "Only Kconfig comparison: Dell EC/SCMI/PCIe/remoteproc/PDC/clock resume remain hardware gates.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-config", type=Path, required=True)
    parser.add_argument("--candidate-config", type=Path, required=True)
    parser.add_argument("--candidate-release", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if not RELEASE.fullmatch(args.candidate_release):
            raise InvalidConfig("INVALID_RELEASE")
        outcome = evaluate(
            parse_config(args.current_config),
            parse_config(args.candidate_config),
            args.candidate_release,
        )
    except InvalidConfig as error:
        outcome = {
            "status": "ERROR",
            "error_code": str(error),
            "boot_authorized": False,
            "device_restore_verified": False,
        }
        code = 2
    else:
        code = 1 if outcome["status"] == "NO_GO" else 0
    if args.json:
        print(json.dumps(outcome, sort_keys=True))
    else:
        print(f"{outcome['status']}: {', '.join(outcome.get('blockers', [])) or outcome.get('error_code', 'static review only')}")
    return code


if __name__ == "__main__":
    sys.exit(main())
