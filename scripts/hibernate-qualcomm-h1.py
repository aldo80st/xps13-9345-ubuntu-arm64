#!/usr/bin/env python3
"""Read-only H1 Qualcomm hibernation manifest validator (stdlib only).

Never emits a GO verdict: valid manifests yield REVIEW_REQUIRED (exit 0),
anything invalid or contradictory yields NO_GO (exit 1).
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "docs" / "hibernate-qualcomm-manifest.json"
GROUPS = ["P1", "P2", "P2a", "P3", "P4", "P5"]
EVIDENCE = {"proposed", "accepted", "mainline", "ubuntu", "uncertain"}
ADMISSION = {"BLOCKED", "REVIEW_ONLY", "READY"}
RISK = {"low", "medium", "high", "unknown"}
REQUIRED = ["id", "url", "evidence_status", "ubuntu_7_3_10_present", "dependencies", "risk", "admission_status"]
MUST_BLOCK = {"P2", "P2a", "P3"}
SECRETS = [re.compile(p) for p in (
    r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"sk-[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S+")]


def scan_secrets(text):
    return [i for i, p in enumerate(SECRETS) if p.search(text)]


def evaluate(m):
    errors, blockers = [], []
    if not isinstance(m, dict):
        return _result(["manifest must be a JSON object"], blockers)
    if scan_secrets(json.dumps(m)):
        errors.append("secret-like content present (redacted)")
    if m.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    for k in ("evidence_date", "source_tree"):
        if not isinstance(m.get(k), str) or not m.get(k):
            errors.append(f"missing {k}")
    groups = m.get("groups")
    if not isinstance(groups, list):
        errors.append("groups must be a list")
        return _result(errors, blockers)
    seen = {}
    for g in groups:
        if not isinstance(g, dict) or not isinstance(g.get("id"), str):
            errors.append("group entry without string id")
            continue
        if g["id"] in seen:
            errors.append(f"duplicate group {g['id']}")
        seen[g["id"]] = g
    for gid in GROUPS:
        if gid not in seen:
            errors.append(f"missing group {gid}")
    for gid in seen:
        if gid not in GROUPS:
            errors.append(f"unexpected group {gid}")
    for gid, g in seen.items():
        e = lambda msg: errors.append(f"{gid}: {msg}")
        for k in REQUIRED:
            if k not in g:
                e(f"missing field {k}")
        if g.get("evidence_status") not in EVIDENCE:
            e("invalid evidence_status")
        if g.get("admission_status") not in ADMISSION:
            e("invalid admission_status")
        if g.get("risk") not in RISK:
            e("invalid risk")
        if g.get("ubuntu_7_3_10_present") not in (True, False, None):
            e("ubuntu_7_3_10_present must be boolean or null")
        url = g.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            e("url must be https")
        if g.get("abi_claim") not in (None, "UNKNOWN"):
            e("ABI claim not permitted without ABI evidence")
        sha = g.get("commit_sha")
        if sha is not None and not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)):
            e("commit_sha must be 40 lowercase hex or absent")
        deps = g.get("dependencies")
        unresolved = []
        if not isinstance(deps, list):
            e("dependencies must be a list")
        else:
            for d in deps:
                if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not isinstance(d.get("resolved"), bool):
                    e("dependency needs id and boolean resolved")
                elif not d["resolved"]:
                    unresolved.append(d["id"])
        adm = g.get("admission_status")
        if adm == "READY":
            e("READY is not permitted in H1 (no verified integration)")
        if gid in MUST_BLOCK and adm != "BLOCKED":
            e("must be BLOCKED")
        if gid == "P2" and "P2a" not in unresolved:
            e("P2 must keep unresolved dependency P2a (v6/v7 review)")
        if gid == "P3" and "remoteproc-lifecycle" not in unresolved:
            e("P3 must keep unresolved dependency remoteproc-lifecycle")
        if adm in ("BLOCKED", "REVIEW_ONLY"):
            blockers.append({"group": gid, "admission_status": adm, "unresolved_dependencies": unresolved,
                             "evidence_status": g.get("evidence_status"), "risk": g.get("risk")})
    return _result(errors, blockers)


def _result(errors, blockers):
    if errors:
        return {"verdict": "NO_GO", "errors": errors, "blockers": blockers}
    return {"verdict": "REVIEW_REQUIRED", "errors": [], "blockers": blockers}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=str(DEFAULT))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = evaluate(json.loads(Path(a.manifest).read_text(encoding="utf-8")))
    except (OSError, ValueError) as ex:
        r = {"verdict": "NO_GO", "errors": [f"cannot load manifest: {type(ex).__name__}"], "blockers": []}
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(r["verdict"])
        for x in r["errors"]:
            print("ERROR:", x)
        for b in r["blockers"]:
            print("BLOCKER:", b["group"], b["admission_status"], b["unresolved_dependencies"])
    return 0 if r["verdict"] == "REVIEW_REQUIRED" else 1


if __name__ == "__main__":
    sys.exit(main())
