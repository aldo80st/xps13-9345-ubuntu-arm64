#!/usr/bin/env python3
"""Compare two allowlisted XPS-VAL-01 snapshots without declaring hardware fixed."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

SCHEMA = "xps-val01.v1"


def compare(before: dict, after: dict) -> dict:
    if before.get("schema") != SCHEMA or after.get("schema") != SCHEMA:
        raise ValueError("unsupported snapshot schema")
    changes = []
    findings = []

    def changed(label: str, left, right):
        if left != right:
            changes.append({"field": label, "before": left, "after": right})

    b_os, a_os = before.get("os", {}), after.get("os", {})
    changed("os.kernel", b_os.get("kernel"), a_os.get("kernel"))
    changed("hardware.bios", before.get("hardware", {}).get("bios"), after.get("hardware", {}).get("bios"))
    bp, ap = before.get("cpu", {}).get("policies", []), after.get("cpu", {}).get("policies", [])
    bpol = {p.get("cluster"): p for p in bp}
    apol = {p.get("cluster"): p for p in ap}
    for cluster in sorted(set(bpol) | set(apol)):
        changed("cpu." + str(cluster), bpol.get(cluster), apol.get(cluster))
    bdev = before.get("video", {}).get("iris_devices", [])
    adev = after.get("video", {}).get("iris_devices", [])
    changed("video.iris_devices", bdev, adev)
    changed("display.connected", before.get("display", {}).get("connected"), after.get("display", {}).get("connected"))
    for iface in sorted(set(before.get("network", {})) & set(after.get("network", {}))):
        first = before["network"][iface]
        last = after["network"][iface]
        for key in ("rx_dropped", "rx_errors", "rx_packets"):
            b, a = first.get(key), last.get(key)
            if isinstance(b, int) and isinstance(a, int):
                if a < b:
                    findings.append({"kind": "COUNTER_RESET_OR_REBOOT", "interface_class": iface,
                                     "counter": key})
                elif a > b and key != "rx_packets":
                    findings.append({"kind": "NETWORK_COUNTER_INCREASE", "interface_class": iface,
                                     "counter": key, "delta": a - b})

    if before.get("os", {}).get("kernel") != after.get("os", {}).get("kernel"):
        findings.append({"kind": "KERNEL_CHANGED_REQUIRES_BASELINE"})
    if not {"qcom-iris-decoder"}.issubset(set(adev)):
        findings.append({"kind": "IRIS_DECODER_NOT_ENUMERATED"})
    if len(apol) < len(bpol):
        findings.append({"kind": "SCMI_CLUSTER_COUNT_DECREASED_REVIEW"})
    return {
        "schema": SCHEMA,
        "decision": "REVIEW_REQUIRED",
        "adoption_authorized": False,
        "cause_confirmed": False,
        "changes": changes,
        "findings": findings,
        "note": "Observational delta only. No automatic ADOPTAR, repaired or root-cause conclusion.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", required=True, type=Path)
    p.add_argument("--after", required=True, type=Path)
    a = p.parse_args()
    try:
        result = compare(json.loads(a.before.read_text()), json.loads(a.after.read_text()))
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(json.dumps({"decision": "NO_GO", "kind": type(exc).__name__,
                          "adoption_authorized": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
