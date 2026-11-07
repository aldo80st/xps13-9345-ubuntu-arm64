#!/usr/bin/env python3
"""Read-only M3 Dell EC / SCMI / hibernation static compatibility gate.

NO_GO on missing evidence. REVIEW_REQUIRED means only the static checks passed;
it is NEVER permission to install a kernel, boot, hibernate, or modify firmware.
The output contains generic check labels only, not file contents or local paths.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

SCMI_REQUIRED = {
    "CONFIG_ARM_SCMI_CPUFREQ": "m",
    "CONFIG_CPU_FREQ": "y",
    "CONFIG_CPU_FREQ_GOV_ONDEMAND": "y",
    "CONFIG_CPU_FREQ_GOV_SCHEDUTIL": "y",
    "CONFIG_ARM_SCMI_PROTOCOL": "y",
}
PATCH_SHA256 = {
    "v8-1.diff": "c73f41f2e3c91afd388aa442b616f82c0be0f39b9a3185391da387cd099ea6e0",
    "v8-2.diff": "5eaba144c037a94d700e73b248883246494683b4aa8a36d71c17a3625a5c5938",
    "v8-3.diff": "8a25b419d57694ceceaa024f3152c4363268d2faf9fffe0ec1531a4f64f05620",
}
MAX_READ = 2 * 1024 * 1024
_SYMBOL = re.compile(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$")
_UNSET = re.compile(r"^# (CONFIG_[A-Za-z0-9_]+) is not set$")


def _read(path: Path):
    try:
        if path.stat().st_size > MAX_READ:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _kconfig(path: Path):
    raw = _read(path)
    if raw is None:
        return None
    relevant = set(SCMI_REQUIRED) | {"CONFIG_HIBERNATION", "CONFIG_EC_DELL_XPS"}
    config = {}
    for line in raw.splitlines():
        m = _SYMBOL.fullmatch(line)
        n = _UNSET.fullmatch(line) if not m else None
        if not (m or n):
            continue
        name = (m or n).group(1)
        if name in relevant:
            if name in config:
                return None  # Duplicate relevant symbol: fail closed.
            config[name] = m.group(2) if m else "n"
    return config


def _patches_match(directory: Path, reference: dict):
    for name, expected_sha in reference.items():
        try:
            file = directory / name
            if file.stat().st_size > MAX_READ:
                return False
            actual = hashlib.sha256(file.read_bytes()).hexdigest()
        except OSError:
            return False
        if actual != expected_sha:
            return False
    return True


def inspect(source_tree: Path, baseline: Path, candidate: Path,
            patches_dir: Path, expected_patch_hashes: dict | None = None) -> dict:
    """Inspect untrusted candidate artifacts, never mutate them."""
    reference = PATCH_SHA256 if expected_patch_hashes is None else expected_patch_hashes
    base_cfg, cand_cfg = _kconfig(Path(baseline)), _kconfig(Path(candidate))
    source_tree, patches_dir = Path(source_tree), Path(patches_dir)

    driver = _read(source_tree / "drivers/platform/arm64/dell-xps-ec.c")
    kconfig = _read(source_tree / "drivers/platform/arm64/Kconfig")
    makefile = _read(source_tree / "drivers/platform/arm64/Makefile")
    dts = _read(source_tree / "arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts")
    binding = _read(source_tree / "Documentation/devicetree/bindings/embedded-controller/dell,xps13-9345-ec.yaml")

    scmi_valid = (base_cfg is not None and cand_cfg is not None
                  and all(base_cfg.get(k) == v and cand_cfg.get(k) == v
                          for k, v in SCMI_REQUIRED.items()))
    checks = {
        "hibernation_config_enabled": cand_cfg is not None and cand_cfg.get("CONFIG_HIBERNATION") == "y",
        "scmi_cpufreq_preserved": scmi_valid,
        "ec_config_enabled": cand_cfg is not None and cand_cfg.get("CONFIG_EC_DELL_XPS") in ("m", "y"),
        "ec_driver_present": driver is not None and "dell_xps_ec" in driver,
        "ec_power_management_callbacks_present": driver is not None and
            "SYSTEM_SLEEP_PM_OPS(dell_xps_ec_suspend, dell_xps_ec_resume)" in driver,
        "ec_binding_present": binding is not None and "Dell XPS" in binding,
        "ec_kconfig_present": kconfig is not None and "config EC_DELL_XPS" in kconfig,
        "ec_build_wiring_present": makefile is not None and "obj-$(CONFIG_EC_DELL_XPS)" in makefile
            and "dell-xps-ec.o" in makefile,
        "ec_dts_node_present": dts is not None and
            "embedded-controller@3b" in dts and
            'compatible = "dell,xps13-9345-ec"' in dts and
            'status = "okay"' in dts,
        "ec_patch_provenance_valid": _patches_match(patches_dir, reference),
    }
    reasons = {
        "hibernation_config_enabled": "hibernation_config_disabled",
        "scmi_cpufreq_preserved": "scmi_cpufreq_regression",
        "ec_config_enabled": "ec_config_disabled",
        "ec_driver_present": "ec_driver_missing",
        "ec_power_management_callbacks_present": "ec_power_management_unreviewed",
        "ec_binding_present": "ec_binding_missing",
        "ec_kconfig_present": "ec_kconfig_missing",
        "ec_build_wiring_present": "ec_build_wiring_missing",
        "ec_dts_node_present": "ec_dts_node_missing",
        "ec_patch_provenance_valid": "ec_patch_provenance_mismatch",
    }
    blockers = [reasons[k] for k, v in checks.items() if not v]
    return {
        "status": "NO_GO" if blockers else "REVIEW_REQUIRED",
        "checks": checks,
        "blockers": blockers,
        "approval": "not_authorized",
        "note": ("Las comprobaciones estaticas nunca prueban recuperacion del EC, "
                 "suspension, hibernacion ni estabilidad de SCMI; se requiere "
                 "revision Qualcomm/EC, pruebas reales y recuperacion BitLocker."),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--ec-patches", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = inspect(args.source_tree, args.baseline, args.candidate, args.ec_patches)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("M3 compatibility:", result["status"])
        print("Blockers:", ", ".join(result["blockers"]) or "none")
        print("Approval:", result["approval"])
    return 1 if result["status"] == "NO_GO" else 0


if __name__ == "__main__":
    raise SystemExit(main())
