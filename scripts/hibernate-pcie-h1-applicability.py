#!/usr/bin/env python3
"""Read-only, fail-closed applicability harness: PCIe shutdown v7 + freeze v2 vs an exact kernel source.

Requires --source-root to be an existing git work tree root (e.g. extracted Ubuntu 7.3.0-10.10
committed or imported into git) and every patch to be a git-format patch ("diff --git" headers).
Nothing is ever applied to the source: only the files the patches touch are copied into a
temporary scratch git repo, where `git apply --check` / `git apply` run sequentially. A hash of
the touched source files and `git status` are compared before/after as a mutation guard.
This tool NEVER prints GO: applicability is necessary, not sufficient (see the stack checker,
known defects and Dell evidence). Exit: 2 rejected input, 1 anything else. Stdlib only.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE.parent / "docs" / "hibernate-pcie-h1-stack.json"
ORDER = ["S7-1", "S7-2", "S7-3", "P2"]


class Reject(Exception):
    pass


def _git(cwd, *args, inp=None):
    return subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(cwd), *args],
                          capture_output=True, text=True, input=inp, timeout=120)


def require_git_source(root):
    if not root:
        raise Reject("SOURCE_ROOT_REQUIRED: pass --source-root (exact kernel tree)")
    p = Path(root)
    if not p.is_dir():
        raise Reject(f"SOURCE_MISSING: {root} is not a directory (needs XPS validation host)")
    r = _git(p, "rev-parse", "--show-toplevel")
    if r.returncode != 0 or Path(r.stdout.strip()).resolve() != p.resolve():
        raise Reject("SOURCE_NOT_GIT: source root is not the top of a git work tree; "
                     "`git apply --check` in a non-git tree silently skips patches and is not evidence")
    if not (p / "drivers/pci/controller/dwc").is_dir():
        raise Reject("SOURCE_INCOMPLETE: drivers/pci/controller/dwc missing")
    return p.resolve()


def split_files(text):
    """Return {path: [diff lines]} for 'diff --git' sections; reject non-git patches."""
    if not re.search(r"^diff --git a/\S+ b/\S+$", text, re.M):
        raise Reject("PATCH_NOT_GIT: no 'diff --git' header")
    out, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r"diff --git a/(\S+) b/(\S+)$", ln)
        if m:
            if m.group(1) != m.group(2):
                raise Reject(f"PATCH_RENAME_UNSUPPORTED: {m.group(1)}")
            cur = m.group(1)
            out[cur] = []
        elif cur is None and re.match(r"(---|\+\+\+) ", ln):
            raise Reject("PATCH_NOT_GIT: file header before any 'diff --git'")
        elif cur is not None:
            out[cur].append(ln)
    for f, ls in out.items():
        if not any(l.startswith("@@") for l in ls):
            raise Reject(f"PATCH_NO_HUNKS: {f}")
        if any(l.startswith("new file mode") for l in ls):
            raise Reject(f"PATCH_NEW_FILE_UNSUPPORTED: {f}")
    return out


def parse_hunks(lines):
    hunks, cur = [], None
    for ln in lines:
        m = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", ln)
        if m:
            cur = {"header": ln, "old_start": int(m.group(1)), "pre": []}
            hunks.append(cur)
        elif cur is not None:
            if ln.startswith((" ", "-")):
                cur["pre"].append(ln[1:])
            elif ln.startswith("+") or ln.startswith("\\"):
                pass
            else:
                cur = None  # trailer (signature, base-commit)
    return hunks


def diagnose_hunk(src_lines, h):
    """Exact (whitespace-sensitive) preimage search. Read-only characterization, no fuzz."""
    pre, n = h["pre"], len(h["pre"])
    for i in range(len(src_lines) - n + 1):
        if src_lines[i:i + n] == pre:
            return {"header": h["header"], "status": "PREIMAGE_FOUND", "line": i + 1,
                    "offset": i + 1 - h["old_start"]}
    best, at = 0, 0
    for i in range(len(src_lines)):
        k = 0
        while k < n and i + k < len(src_lines) and src_lines[i + k] == pre[k]:
            k += 1
        if k > best:
            best, at = k, i
    d = {"header": h["header"], "status": "PREIMAGE_MISSING", "matched_prefix_lines": best}
    if best < n:
        d["first_mismatch_expected"] = pre[best]
        if at + best < len(src_lines):
            d["first_mismatch_found"] = src_lines[at + best]
            d["near_line"] = at + best + 1
    return d


def lint_patch(pid, text):
    """Static semantic findings that persist regardless of applicability."""
    f = []
    if pid == "S7-3":
        body = text
        if re.search(r"struct qcom_pcie \*pcie;", body) and "firmware_managed" in body \
                and re.search(r"if \(pcie\)\s*\n\+\s*dw_pcie_suspend_noirq\(pcie->pci, true\)", body):
            f.append("S7-3_UNINITIALISED_PCIE: `pcie` is never assigned on the firmware_managed "
                     "branch but tested/used after it (robot+Sashiko; unresolved upstream)")
    return f


def tree_state(root, files):
    h = hashlib.sha256()
    for f in sorted(files):
        p = root / f
        h.update(f.encode() + b"\0")
        h.update(p.read_bytes() if p.is_file() else b"<absent>")
    st = _git(root, "status", "--porcelain=v1", "-uno").stdout
    return h.hexdigest(), st


def run(source_root, series_dir, manifest_path=DEFAULT_MANIFEST):
    root = require_git_source(source_root)
    if not series_dir or not Path(series_dir).is_dir():
        raise Reject("SERIES_DIR_MISSING: pass --series-dir with staged patches")
    mf = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    byid = {p["id"]: p for p in mf["patches"]}
    texts, files = {}, {}
    for pid in ORDER:
        if pid not in byid:
            raise Reject(f"MANIFEST_MISSING: {pid}")
        f = Path(series_dir) / byid[pid]["file"]
        if not f.is_file():
            raise Reject(f"PATCH_MISSING: {f}")
        texts[pid] = f.read_text(encoding="utf-8", errors="replace")
        exp = byid[pid].get("sha256")
        if hashlib.sha256(texts[pid].encode()).hexdigest() != exp:
            raise Reject(f"PATCH_SHA_MISMATCH: {pid}")
        files[pid] = split_files(texts[pid])
    touched = sorted({f for fs in files.values() for f in fs})
    head = _git(root, "rev-parse", "HEAD")
    dirty = _git(root, "status", "--porcelain=v1", "--", *touched).stdout.strip()
    before = tree_state(root, touched)
    report = {"source_root": str(root), "source_head": head.stdout.strip() or None,
              "touched_files": touched, "patches": {}, "failures": [], "mutation_guard": None}
    if dirty:
        report["failures"].append("SOURCE_DIRTY: touched files differ from HEAD; evidence invalid")
    with tempfile.TemporaryDirectory(prefix="h1-scratch-") as td:
        scratch = Path(td)
        _git(scratch, "init", "-q")

        def fill(d):
            for f in touched:
                if (root / f).is_file():
                    (d / f).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(root / f, d / f)
        fill(scratch)
        pristine = Path(td + "-pristine")
        pristine.mkdir()
        try:
            _git(pristine, "init", "-q")
            fill(pristine)
            blocked = None
            for pid in ORDER:
                pf = Path(td) / f"{pid}.patch"
                pf.write_text(texts[pid])
                # isolated: against the pristine source copy
                iso = _git(pristine, "apply", "--check", str(pf))
                entry = {"isolated": "APPLIES" if iso.returncode == 0 else "FAILS",
                         "isolated_stderr": iso.stderr.strip().splitlines()[:12], "hunks": {}}
                for f, ls in files[pid].items():
                    sp = root / f
                    if not sp.is_file():
                        entry["hunks"][f] = [{"status": "FILE_MISSING_IN_SOURCE"}]
                        continue
                    src = sp.read_text(encoding="utf-8", errors="replace").split("\n")
                    entry["hunks"][f] = [diagnose_hunk(src, h) for h in parse_hunks(ls)]
                # sequential: cumulative scratch copy
                if blocked:
                    entry["sequential"] = f"BLOCKED_BY_{blocked}"
                else:
                    seq = _git(scratch, "apply", "--check", str(pf))
                    if seq.returncode == 0:
                        _git(scratch, "apply", str(pf))
                        entry["sequential"] = "APPLIES"
                    else:
                        entry["sequential"] = "FAILS"
                        entry["sequential_stderr"] = seq.stderr.strip().splitlines()[:12]
                        blocked = pid
                bad = sorted({f for f, hs in entry["hunks"].items() for h in hs if h["status"] != "PREIMAGE_FOUND"})
                entry["unmatched_files_vs_pristine"] = bad
                if entry["sequential"] != "APPLIES":
                    report["failures"].append(f"NOT_APPLICABLE: {pid} sequential={entry['sequential']}"
                                              f" (hunk diagnostics are against the pristine source; unmatched: {bad})")
                entry["lint"] = lint_patch(pid, texts[pid])
                report["failures"] += entry["lint"]
                report["patches"][pid] = entry
        finally:
            shutil.rmtree(pristine, ignore_errors=True)
    after = tree_state(root, touched)
    report["mutation_guard"] = "UNCHANGED" if after == before else "SOURCE_MUTATED"
    if after != before:
        report["failures"].append("SOURCE_MUTATED: guard tripped (should be impossible)")
    seq_ok = all(e["sequential"] == "APPLIES" for e in report["patches"].values())
    report["verdict"] = "NO_GO"  # never GO from this tool
    report["applicability"] = "SERIES_APPLIES_STRUCTURALLY" if (seq_ok and not report["failures"]) else "NOT_APPLICABLE"
    report["note"] = ("Applicability is necessary, not sufficient. Admission stays NO_GO until the "
                      "stack checker's defects, reconciliation and Dell XPS 9345 evidence are met.")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", required=True, help="exact kernel source root (git work tree top)")
    ap.add_argument("--series-dir", required=True)
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = run(a.source_root, a.series_dir, a.manifest)
    except Reject as ex:
        print(f"REJECTED: {ex}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"{r['verdict']} ({r['applicability']}) head={r['source_head']} guard={r['mutation_guard']}")
        for pid, e in r["patches"].items():
            print(f" {pid}: isolated={e['isolated']} sequential={e['sequential']}")
        for x in r["failures"]:
            print(" -", x)
    return 1


if __name__ == "__main__":
    sys.exit(main())
