#!/usr/bin/env python3
"""Validate pinned upstream sources for XPS hibernation, without fetching code.

Local validation is metadata-only. --check-remote reads Git advertisements;
neither command installs, builds, downloads sources, updates pins or allows boot.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "docs/hibernate-upstream-projects.lock.json"
PIN = re.compile(r"^[0-9a-f]{40}$")

# Trust boundaries are explicit: changing an upstream or its role requires review.
SOURCES = {
    "ubuntu-concept-qcom-x1e": (
        "build_base",
        "https://git.launchpad.net/~ubuntu-concept/ubuntu/+source/linux/+git/resolute",
        "refs/heads/resolute-x1e",
        "source_review_only",
    ),
    "dell-xps-9345-tributo": (
        "device_reference",
        "https://github.com/alexVinarskis/linux-x1e80100-dell-tributo",
        "refs/heads/master",
        "delta_review_only",
    ),
    "omarchy": (
        "comparative_reference",
        "https://github.com/omacom/omarchy",
        "HEAD",
        "evidence_only",
    ),
    "x1e-nixos-config": (
        "comparative_reference",
        "https://github.com/kuruczgy/x1e-nixos-config",
        "HEAD",
        "evidence_only",
    ),
}
GATES = frozenset({
    "canonical_exact_source_identity", "dell_dt_ec_delta_review",
    "upstream_pcie_restore", "upstream_remoteproc_restore",
    "upstream_pdc_restore", "upstream_clock_restore",
    "thermal_scmi_compatibility", "backup_bitlocker_rollback",
})


class LockInvalid(ValueError):
    pass


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LockInvalid("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict:
    try:
        if not path.is_file() or path.stat().st_size > 131072:
            raise LockInvalid("MISSING_OR_OVERSIZED_MANIFEST")
        obj = json.loads(path.read_text(encoding="utf-8"),
                         object_pairs_hook=reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise LockInvalid("INVALID_MANIFEST") from exc
    if not isinstance(obj, dict):
        raise LockInvalid("INVALID_ROOT")
    if (obj.get("schema_version") != 1 or obj.get("epic") != "XPS-HIB-01"
            or obj.get("source_policy") != "upstream-first-no-automatic-upgrades"
            or obj.get("release_equivalence") != "unverified"
            or obj.get("launch_or_install_authorized") is not False):
        raise LockInvalid("UNSAFE_MANIFEST_POLICY")
    if not isinstance(obj.get("required_gates"), list) or (
            len(obj["required_gates"]) != len(GATES) or set(obj["required_gates"]) != GATES):
        raise LockInvalid("REQUIRED_GATES_MISSING_OR_CHANGED")
    projects = obj.get("projects")
    if not isinstance(projects, list) or len(projects) != len(SOURCES):
        raise LockInvalid("SOURCE_SET_CHANGED")
    seen = set()
    for project in projects:
        if not isinstance(project, dict):
            raise LockInvalid("BAD_SOURCE_ENTRY")
        key = project.get("id")
        if key not in SOURCES or key in seen:
            raise LockInvalid("UNTRUSTED_OR_DUPLICATE_SOURCE")
        seen.add(key)
        role, remote, ref, handling = SOURCES[key]
        if ((project.get("role"), project.get("remote"),
             project.get("ref"), project.get("handling")) !=
                (role, remote, ref, handling)):
            raise LockInvalid("SOURCE_IDENTITY_CHANGED")
        if not isinstance(project.get("commit"), str) or not PIN.fullmatch(project["commit"]):
            raise LockInvalid("INVALID_COMMIT_PIN")
        if role == "comparative_reference":
            if (project.get("license_status") != "not_importing"
                    or project.get("package_provenance") != "not_applicable"):
                raise LockInvalid("REFERENCE_PROMOTED")
        elif project.get("license_status") != "pending_review":
            raise LockInvalid("UNREVIEWED_LICENSE_PROMOTION")
    return obj


def _remote_commit(project):
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", project["remote"], project["ref"]],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    refs = [
        line.split("\t", 1)[0] for line in result.stdout.splitlines()
        if "\t" in line and line.split("\t", 1)[1] == project["ref"]
        and PIN.fullmatch(line.split("\t", 1)[0])
    ]
    return refs[0] if len(refs) == 1 else None


def evaluate(manifest: dict, check_remote: bool = False) -> dict:
    projects = manifest["projects"]
    outcome = {
        "status": "LOCAL_LOCK_VALID",
        "install_authorized": False,
        "release_equivalence_verified": False,
        "source_code_downloaded": False,
        "projects": [
            {"id": project["id"], "role": project["role"],
             "ref": project["ref"], "commit": project["commit"]}
            for project in projects
        ],
        "drift": [],
        "unverified": [],
    }
    if not check_remote:
        return outcome
    for project in projects:
        actual = _remote_commit(project)
        if actual is None:
            outcome["unverified"].append(project["id"])
        elif actual != project["commit"]:
            outcome["drift"].append(project["id"])
    if outcome["unverified"]:
        outcome["status"] = "REMOTE_UNVERIFIED"
    elif outcome["drift"]:
        outcome["status"] = "DRIFT_DETECTED"
    else:
        outcome["status"] = "PIN_MATCH"
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT)
    parser.add_argument("--check-remote", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        outcome = evaluate(load_manifest(args.manifest), args.check_remote)
    except LockInvalid as exc:
        outcome = {
            "status": "INVALID", "error_code": str(exc),
            "install_authorized": False, "release_equivalence_verified": False,
        }
    status = outcome["status"]
    if args.json:
        print(json.dumps(outcome, sort_keys=True))
    else:
        print(f"{status}: metadata and commit comparison only; no boot authorization")
    return 0 if status in ("LOCAL_LOCK_VALID", "PIN_MATCH") else (1 if status == "DRIFT_DETECTED" else 2)


if __name__ == "__main__":
    sys.exit(main())
