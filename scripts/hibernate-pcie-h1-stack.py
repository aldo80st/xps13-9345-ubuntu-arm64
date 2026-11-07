#!/usr/bin/env python3
"""Fail-closed H1 PCIe stack checker (P2 freeze v2 on top of shutdown series).

`check`: evaluates docs/hibernate-pcie-h1-stack.json (+ optional staged series dir and
Linux source root) and prints GO or NO_GO. GO requires every condition proven; anything
missing/unknown is NO_GO. Exit 0 only for GO.
`stage`: downloads patch emails (text only) from lore.kernel.org into a directory
(use an ignored path such as .local/) and prints sha256 values. Never builds or applies.
Stdlib only.
"""
import argparse
import gzip
import hashlib
import json
import mailbox
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

DEFAULT = Path(__file__).resolve().parents[1] / "docs" / "hibernate-pcie-h1-stack.json"
FIXED_IDS = ["S7-1", "S7-2", "S7-3", "P2"]
CALL = re.compile(r"dw_pcie_suspend_noirq\(")
DECL = re.compile(r"^\+\s*(static inline\s+)?int\s+dw_pcie_suspend_noirq\(")
HEX64 = re.compile(r"[0-9a-f]{64}")


def sha256_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def split_mbox(data):
    """bytes mbox -> {(version, n): text}; only '[PATCH vN n/m]' originals (no Re:)."""
    out = {}
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "x.mbox"
        f.write_bytes(data)
        mb = mailbox.mbox(str(f))
        try:
            for msg in mb:
                s = " ".join((msg["Subject"] or "").split())
                k = re.match(r"\[PATCH (v\d+) (\d+)/\d+\]", s)
                if k:
                    body = msg.get_payload(decode=True).decode("utf-8", "replace")
                    out[(k.group(1), int(k.group(2)))] = f"Subject: {s}\nMessage-Id: {msg['Message-Id']}\n\n{body}"
        finally:
            mb.close()
    return out


def single_patch(data):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "x.mbox"
        f.write_bytes(data)
        mb = mailbox.mbox(str(f))
        try:
            for msg in mb:
                s = " ".join((msg["Subject"] or "").split())
                body = msg.get_payload(decode=True).decode("utf-8", "replace")
                if s.startswith("[PATCH") and "diff --git" in body:
                    return f"Subject: {s}\nMessage-Id: {msg['Message-ID'] or msg['Message-Id']}\n\n{body}"
        finally:
            mb.close()
    return None


def sections(text):
    """file -> list of diff lines (+/-)"""
    cur, out = None, {}
    for line in text.splitlines():
        m = re.match(r"diff --git a/(\S+) b/\S+", line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, [])
        elif cur and line[:1] in "+-" and not line.startswith(("+++", "---")):
            out[cur].append(line)
    return out


def callsites(text):
    """file -> force arg for '+' call lines (declarations excluded)."""
    res = {}
    for f, lines in sections(text).items():
        for ln in lines:
            if ln.startswith("+") and CALL.search(ln) and not DECL.match(ln):
                m = re.search(r"dw_pcie_suspend_noirq\([^,]+,\s*(\w+)\)", ln)
                res[f] = m.group(1) if m else "?"
    return res


def norm(l):
    return re.sub(r"\s+", " ", l[1:]).strip()


def evaluate(mf, series_dir=None, source_root=None):
    F, U = [], []  # failures (contradictions), unmet (insufficient evidence)
    res = lambda: {"verdict": "NO_GO" if (F or U) else "GO", "failures": F, "unmet": U}
    if not isinstance(mf, dict) or not isinstance(mf.get("patches"), list):
        F.append("BAD_MANIFEST: not an object with patches list")
        return res()
    byid = {}
    for p in mf["patches"]:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not isinstance(p.get("requires"), list):
            F.append("BAD_MANIFEST: patch entry needs id and requires list")
            return res()
        if p["id"] in byid:
            F.append(f"BAD_MANIFEST: duplicate {p['id']}")
        byid[p["id"]] = p
    for i in FIXED_IDS:
        if i not in byid:
            F.append(f"MISSING_PATCH_ENTRY: {i}")
    for p in byid.values():
        u = urlparse(str(p.get("url", "")))
        if u.scheme != "https" or not u.netloc:
            F.append(f"BAD_URL: {p['id']} must be https")
        for r in p["requires"]:
            if r not in byid:
                F.append(f"DANGLING_DEPENDENCY: {p['id']} -> {r}")
    # cycle detection
    state = {}

    def visit(n, stack):
        if state.get(n) == 2:
            return
        if state.get(n) == 1:
            F.append("DEPENDENCY_CYCLE: " + " -> ".join(stack + [n]))
            return
        state[n] = 1
        for r in byid[n]["requires"]:
            if r in byid:
                visit(r, stack + [n])
        state[n] = 2
    for n in byid:
        visit(n, [])
    if F:
        return res()
    rec = mf.get("reconciliation") if isinstance(mf.get("reconciliation"), dict) else {}
    rec_ok = rec.get("status") == "verified" and bool(rec.get("evidence"))
    for p in byid.values():
        for r in p["requires"]:
            want = p.get("built_against_version")
            have = byid[r].get("version")
            if want and have and want != have and not rec_ok:
                U.append(f"VERSION_MISMATCH: {p['id']} built against {want} but stack provides {r}@{have}; reconciliation not verified")
    # series / hashes / content
    texts = {}
    if series_dir is None:
        U.append("SERIES_DIR: patch series not staged; hashes/content unverified")
    else:
        for i in FIXED_IDS:
            p = byid.get(i)
            if not p:
                continue
            f = Path(series_dir) / str(p.get("file", ""))
            if not f.is_file():
                F.append(f"MISSING_PATCH: {i} ({p.get('file')})")
                continue
            t = f.read_text(encoding="utf-8", errors="replace")
            texts[i] = t
            exp = p.get("sha256")
            if not (isinstance(exp, str) and HEX64.fullmatch(exp)):
                U.append(f"NO_SHA256: {i} has no validated hash in manifest")
            elif sha256_text(t) != exp:
                F.append(f"SHA_MISMATCH: {i}")
            sv = p.get("version")
            first = t.splitlines()[0] if t else ""
            if sv and not re.search(rf"\[PATCH {re.escape(sv)}[ \]]", first):
                F.append(f"WRONG_VERSION: {i} subject '{first[:60]}' is not {sv}")
    s2, s3, p2 = texts.get("S7-2"), texts.get("S7-3"), texts.get("P2")
    expected = mf.get("expected_force_callsites")
    if s2 is not None:
        if "dw_pcie_suspend_noirq(struct dw_pcie *pci, bool force)" not in s2:
            F.append("S7-2: force parameter signature absent")
        if "!force" not in s2:
            F.append("S7-2: force bypass of D3cold check absent")
        got = callsites(s2)
        if not isinstance(expected, dict) or not expected:
            U.append("EXPECTED_CALLSITES: manifest lacks expected_force_callsites")
        else:
            for f in expected:
                if f not in got:
                    F.append(f"MISSING_CALLSITE: {f} not converted by S7-2")
                elif got[f] != expected[f]:
                    F.append(f"CALLSITE_ARG: {f} passes {got[f]}, expected {expected[f]}")
            for f in got:
                if f not in expected:
                    F.append(f"UNEXPECTED_CALLSITE: {f}")
    if s3 is not None:
        for need in ("qcom_pcie_shutdown", ".shutdown = qcom_pcie_shutdown", "dw_pcie_suspend_noirq(pcie->pci, true)"):
            if need not in s3:
                F.append(f"S7-3: missing '{need}'")
    if p2 is not None:
        for need in (".freeze_noirq", "dw_pcie_suspend_noirq(pcie->pci, force)", "qcom_pcie_suspend(dev, true)"):
            if need not in p2.replace("return qcom_pcie_suspend(dev, true);", "qcom_pcie_suspend(dev, true)"):
                F.append(f"P2: missing '{need}'")
        if s2 is not None:
            added = {norm(l) for ls in sections(s2).values() for l in ls if l.startswith("+")}
            pre = [norm(l) for ls in sections(p2).values() for l in ls if l.startswith("-") and CALL.search(l)]
            if not pre:
                F.append("P2_PREIMAGE: no dw_pcie_suspend_noirq pre-image line in P2")
            for l in pre:
                if l not in added:
                    F.append(f"P2_PREIMAGE: '{l}' not produced by S7-2")
    # tree callers
    if source_root is None:
        U.append("SOURCE_ROOT: no Linux source root scanned; caller completeness unverified")
    elif isinstance(expected, dict) and expected:
        root = Path(source_root)
        d = root / "drivers" / "pci" / "controller" / "dwc"
        if not d.is_dir():
            F.append("SOURCE_ROOT: drivers/pci/controller/dwc not found")
        else:
            for c in sorted(root.glob("drivers/**/*.c")):
                rel = c.relative_to(root).as_posix()
                if rel.endswith("pcie-designware-host.c"):
                    continue
                if CALL.search(c.read_text(encoding="utf-8", errors="replace")) and rel not in expected:
                    F.append(f"UNCOVERED_TREE_CALLER: {rel}")
    # defects and hardware evidence
    for dfc in mf.get("known_defects", []) if isinstance(mf.get("known_defects"), list) else []:
        if not (isinstance(dfc, dict) and dfc.get("resolved") is True):
            U.append(f"UNRESOLVED_DEFECT: {dfc.get('id') if isinstance(dfc, dict) else dfc}")
    if rec.get("status") != "verified":
        U.append("RECONCILIATION: P2-on-v7 reconciliation not verified")
    de = mf.get("dell_evidence")
    if not (isinstance(de, dict) and "XPS" in str(de.get("machine", "")) and "9345" in str(de.get("machine", ""))
            and de.get("nvme_resume") is True and de.get("wifi_resume") is True):
        U.append("DELL_EVIDENCE: no Dell XPS 9345 NVMe+Wi-Fi resume evidence (Lenovo results do not count)")
    return res()


def fetch(url):
    if urlparse(url).netloc != "lore.kernel.org":
        raise ValueError("only lore.kernel.org allowed")
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def stage(out, mf):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    u7 = "https://lore.kernel.org/all/20261029-shutdown-v7-0-3fd7a76a6991@oss.qualcomm.com/t.mbox.gz"
    s7 = split_mbox(fetch(u7))
    for n in (1, 2, 3):
        t = s7[("v7", n)]
        p = next(x for x in mf["patches"] if x["id"] == f"S7-{n}")
        (out / p["file"]).write_text(t)
        res[p["id"]] = sha256_text(t)
    t = single_patch(fetch("https://lore.kernel.org/all/179181074907.22199.10556821368232442334@pm.me/t.mbox.gz"))
    p = next(x for x in mf["patches"] if x["id"] == "P2")
    (out / p["file"]).write_text(t)
    res["P2"] = sha256_text(t)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--manifest", default=str(DEFAULT))
    c.add_argument("--series-dir")
    c.add_argument("--source-root")
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("stage")
    s.add_argument("--manifest", default=str(DEFAULT))
    s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        mf = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        mf = None
        if a.cmd == "stage":
            print("cannot load manifest", file=sys.stderr)
            return 2
    if a.cmd == "stage":
        print(json.dumps(stage(a.out, mf), indent=2))
        return 0
    r = evaluate(mf, a.series_dir, a.source_root)
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(r["verdict"])
        for x in r["failures"] + r["unmet"]:
            print(" -", x)
    return 0 if r["verdict"] == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
