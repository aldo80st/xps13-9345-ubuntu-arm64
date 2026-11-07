#!/usr/bin/env python3
"""Read-only Kconfig audit: is the candidate delta only hibernation symbols?

Only symbol NAMES are reported; values and file paths are never emitted.
Exit code: 0 CLEAN, 1 UNRELATED_DRIFT, 2 UNKNOWN.
"""
import argparse
import json
from pathlib import Path
import re
import sys

EXPECTED = frozenset({
    "CONFIG_HIBERNATION", "CONFIG_HIBERNATE_CALLBACKS", "CONFIG_HIBERNATION_SNAPSHOT_DEV",
    "CONFIG_HIBERNATION_COMP_LZO", "CONFIG_HIBERNATION_COMP_LZ4", "CONFIG_HIBERNATION_DEF_COMP",
    "CONFIG_PM_STD_PARTITION", "CONFIG_ARCH_HIBERNATION_HEADER",
})
MAX_BYTES = 16 * 1024 * 1024
EXIT = {"CLEAN": 0, "UNRELATED_DRIFT": 1, "UNKNOWN": 2}

_ASSIGN = re.compile(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$")
_UNSET = re.compile(r"^# (CONFIG_[A-Za-z0-9_]+) is not set$")

# Substring heuristics on symbol names (see docs/hibernate-config-audit.md).
_FLAGS = {
    "rust": ("RUST", "BINDGEN"),
    "bpf": ("BPF", "BTF"),
    "pahole": ("PAHOLE",),
    "gcc": ("GCC", "CC_VERSION", "CC_IS_", "CLANG", "AS_VERSION", "AS_IS_", "LD_VERSION",
            "LD_IS_", "LLD_VERSION", "TOOLS_SUPPORT", "CC_HAS_", "CC_CAN_"),
}


def parse(path: Path) -> tuple[dict | None, list[str]]:
    """Return ({symbol: value|None}, errors). None value means 'is not set'."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None, ["unreadable: file too large"]
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, ["unreadable"]
    symbols: dict = {}
    errors: list[str] = []
    for no, line in enumerate(raw.splitlines(), 1):
        line = line.rstrip()
        if not line:
            continue
        m = _ASSIGN.match(line)
        n = _UNSET.match(line) if not m else None
        if m or n:
            name = (m or n).group(1)
            if name in symbols:
                errors.append(f"duplicate symbol {name} (line {no})")
            symbols[name] = m.group(2) if m else None
        elif line.startswith("#") and not line.startswith("# CONFIG_"):
            continue  # free-form comment / section header
        else:
            errors.append(f"malformed line {no}")
    if not symbols and not errors:
        errors.append("no Kconfig symbols found")
    return symbols, errors


def _flags(names: list[str]) -> dict:
    out = {}
    for key, needles in _FLAGS.items():
        out[key] = [n for n in names if any(s in n for s in needles)]
    return out


def audit(baseline: Path, candidate: Path) -> dict:
    base, berr = parse(Path(baseline))
    cand, cerr = parse(Path(candidate))
    errors = [f"baseline: {e}" for e in berr] + [f"candidate: {e}" for e in cerr]
    result = {
        "status": "UNKNOWN", "expected_changed": [], "dependency_changed": [],
        "unrelated_changed": [],
        "flags": {k: [] for k in _FLAGS}, "hibernation_evidence": False,
        "errors": errors, "notes": [],
    }
    if errors or base is None or cand is None:
        return result
    changed = sorted(s for s in set(base) | set(cand) if base.get(s, "\0absent") != cand.get(s, "\0absent"))
    expected = [s for s in changed if s in EXPECTED]

    # Ubuntu 7.3 kernel/power/Kconfig: HIBERNATION selects CRYPTO_LZ4,
    # crypto/Kconfig: CRYPTO_LZ4 selects LZ4_COMPRESS. The baseline has both
    # as modules; built-in hibernation promotes them to built-in. Restrict
    # this exception to the exact m -> y transition and the selector chain.
    hibernation_activated = (base.get("CONFIG_HIBERNATION") is None
                            and cand.get("CONFIG_HIBERNATION") == "y")
    lz4_selected = (hibernation_activated
                    and base.get("CONFIG_CRYPTO_LZ4") == "m"
                    and cand.get("CONFIG_CRYPTO_LZ4") == "y")
    deps = []
    if lz4_selected and "CONFIG_CRYPTO_LZ4" in changed:
        deps.append("CONFIG_CRYPTO_LZ4")
    if (lz4_selected and base.get("CONFIG_LZ4_COMPRESS") == "m"
            and cand.get("CONFIG_LZ4_COMPRESS") == "y"
            and "CONFIG_LZ4_COMPRESS" in changed):
        deps.append("CONFIG_LZ4_COMPRESS")

    unrelated = [s for s in changed if s not in EXPECTED and s not in deps]
    result["expected_changed"] = expected
    result["dependency_changed"] = deps
    result["unrelated_changed"] = unrelated
    result["flags"] = _flags(unrelated)
    result["hibernation_evidence"] = bool(expected)
    result["status"] = "UNRELATED_DRIFT" if unrelated else "CLEAN"
    if not changed:
        result["notes"].append("no changes: no evidence of hibernation in candidate")
    elif not expected:
        result["notes"].append("no hibernation symbol changed: no evidence of hibernation")
    if unrelated:
        result["notes"].append("symbol names only; values intentionally not reported")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    result = audit(args.baseline, args.candidate)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"status: {result['status']}")
        print(f"expected hibernation symbols changed: {len(result['expected_changed'])}")
        print(f"required LZ4 dependencies changed: {len(result['dependency_changed'])}")
        print(f"unrelated symbols changed: {len(result['unrelated_changed'])}")
        for key, names in result["flags"].items():
            if names:
                print(f"  {key} deviations: {len(names)}")
        for e in result["errors"]:
            print(f"error: {e}")
        for n in result["notes"]:
            print(f"note: {n}")
    return EXIT[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
