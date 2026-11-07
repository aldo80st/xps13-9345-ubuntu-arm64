"""Offline tests for the applicability harness (synthetic git trees, no kernel)."""
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("appl", ROOT / "scripts" / "hibernate-pcie-h1-applicability.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

D = "drivers/pci/controller/dwc/"
A = D + "pcie-a.c"
SRC = "int f(void)\n{\n\treturn g(x);\n}\n"
PATCH = f"""Subject: [PATCH v7 1/1] t

diff --git a/{A} b/{A}
--- a/{A}
+++ b/{A}
@@ -1,4 +1,4 @@
 int f(void)
 {{
-\treturn g(x);
+\treturn g(x, 1);
 }}
"""


def git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def mk_tree(td, text=SRC, as_git=True):
    r = Path(td) / "src"
    (r / D).mkdir(parents=True)
    (r / A).write_text(text)
    if as_git:
        git(r, "init", "-q")
        git(r, "add", "-A")
        git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x")
    return r


def mk_series(td, texts):
    s = Path(td) / "series"
    s.mkdir()
    pats = []
    for pid, f in zip(m.ORDER, ["a", "b", "c", "d"]):
        t = texts.get(pid, PATCH if pid == "S7-1" else PATCH.replace("g(x)", "g(x, 1)").replace("g(x, 1, 1)", "g(x,1,1)"))
        (s / f"{f}.patch").write_text(t)
        pats.append({"id": pid, "file": f"{f}.patch", "sha256": hashlib.sha256(t.encode()).hexdigest()})
    mf = Path(td) / "mf.json"
    mf.write_text(json.dumps({"patches": pats}))
    return s, mf


class T(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def test_rejects_missing_source(self):
        with self.assertRaisesRegex(m.Reject, "SOURCE_MISSING"):
            m.require_git_source(self.td + "/nope")

    def test_rejects_missing_arg(self):
        with self.assertRaisesRegex(m.Reject, "SOURCE_ROOT_REQUIRED"):
            m.require_git_source(None)

    def test_rejects_non_git_tree(self):
        r = mk_tree(self.td, as_git=False)
        with self.assertRaisesRegex(m.Reject, "SOURCE_NOT_GIT"):
            m.require_git_source(r)

    def test_rejects_subdir_of_git_repo(self):
        r = mk_tree(self.td)
        with self.assertRaisesRegex(m.Reject, "SOURCE_NOT_GIT"):
            m.require_git_source(r / "drivers")

    def test_non_git_tree_silent_skip_is_why(self):
        """git apply --check inside a non-git dir exits 0 for a non-matching patch (skips it)."""
        r = mk_tree(self.td, text="totally different\n", as_git=False)
        p = Path(self.td) / "p.patch"
        p.write_text(PATCH)
        res = subprocess.run(["git", "-C", str(r), "apply", "--check", str(p)], capture_output=True, text=True)
        # outside a repo git apply does not honour the tree: documents the hazard; harness must refuse.
        with self.assertRaises(m.Reject):
            m.require_git_source(r)
        self.assertIn(res.returncode, (0, 1))

    def test_rejects_non_git_patch(self):
        with self.assertRaisesRegex(m.Reject, "PATCH_NOT_GIT"):
            m.split_files("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n")

    def test_rejects_patch_without_hunks(self):
        with self.assertRaisesRegex(m.Reject, "PATCH_NO_HUNKS"):
            m.split_files("diff --git a/x b/x\nindex 1..2 100644\n")

    def test_sha_mismatch_rejected(self):
        r = mk_tree(self.td)
        s, mf = mk_series(self.td, {})
        (s / "a.patch").write_text(PATCH + "\n#\n")
        with self.assertRaisesRegex(m.Reject, "PATCH_SHA_MISMATCH"):
            m.run(r, s, mf)

    def test_applies_but_never_go_and_no_mutation(self):
        r = mk_tree(self.td)
        # chain: S7-1 g(x)->g(x, 1); S7-2 g(x, 1)->g(x, 1, 2); S7-3 ->3; P2 ->4
        def step(a, b):
            return PATCH.replace("-\treturn g(x);", "-\treturn " + a + ";").replace("+\treturn g(x, 1);", "+\treturn " + b + ";")
        texts = {"S7-1": step("g(x)", "g(x, 1)"), "S7-2": step("g(x, 1)", "g(x, 2)"),
                 "S7-3": step("g(x, 2)", "g(x, 3)"), "P2": step("g(x, 3)", "g(x, 4)")}
        s, mf = mk_series(self.td, texts)
        before = (r / A).read_bytes()
        rep = m.run(r, s, mf)
        self.assertEqual(rep["verdict"], "NO_GO")
        self.assertEqual(rep["applicability"], "SERIES_APPLIES_STRUCTURALLY")
        self.assertEqual(rep["mutation_guard"], "UNCHANGED")
        self.assertEqual((r / A).read_bytes(), before)
        self.assertEqual(subprocess.run(["git", "-C", str(r), "status", "--porcelain"], capture_output=True, text=True).stdout, "")
        self.assertEqual(main_rc(r, s, mf), 1)  # never 0 / GO

    def test_failing_hunk_blocks_later_and_is_diagnosed(self):
        r = mk_tree(self.td, text="int f(void)\n{\n\tbool x = d3cold();\n}\n")
        s, mf = mk_series(self.td, {})
        rep = m.run(r, s, mf)
        self.assertEqual(rep["applicability"], "NOT_APPLICABLE")
        e = rep["patches"]["S7-1"]
        self.assertEqual(e["sequential"], "FAILS")
        self.assertEqual(rep["patches"]["S7-2"]["sequential"], "BLOCKED_BY_S7-1")
        h = e["hunks"][A][0]
        self.assertEqual(h["status"], "PREIMAGE_MISSING")
        self.assertEqual(h["first_mismatch_found"], "\tbool x = d3cold();")

    def test_dirty_source_flagged(self):
        r = mk_tree(self.td)
        (r / A).write_text(SRC + "// dirty\n")
        s, mf = mk_series(self.td, {})
        rep = m.run(r, s, mf)
        self.assertTrue(any(x.startswith("SOURCE_DIRTY") for x in rep["failures"]))
        self.assertNotEqual(rep["applicability"], "SERIES_APPLIES_STRUCTURALLY")

    def test_missing_file_in_source_reported(self):
        r = mk_tree(self.td)
        (r / A).unlink()
        git(r, "add", "-A")
        git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "rm")
        s, mf = mk_series(self.td, {})
        rep = m.run(r, s, mf)
        self.assertEqual(rep["patches"]["S7-1"]["hunks"][A][0]["status"], "FILE_MISSING_IN_SOURCE")

    def test_whitespace_exact_preimage(self):
        h = m.parse_hunks(PATCH.splitlines())[0]
        d = m.diagnose_hunk(["int f(void)", "{", "    return g(x);", "}"], h)
        self.assertEqual(d["status"], "PREIMAGE_MISSING")  # no fuzz / whitespace tolerance

    def test_s7_3_uninitialised_pcie_lint(self):
        p = ("+\tstruct qcom_pcie *pcie;\n+\tif (pcie_cfg && pcie_cfg->firmware_managed) {\n"
             "+\tif (pcie)\n+\t\tdw_pcie_suspend_noirq(pcie->pci, true);\n")
        self.assertTrue(m.lint_patch("S7-3", p))
        self.assertFalse(m.lint_patch("S7-2", p))

    def test_real_staged_series_lint_if_present(self):
        f = ROOT / ".local/h1-pcie/stack/s7-3.patch"
        if not f.is_file():
            self.skipTest("staged series absent")
        self.assertTrue(m.lint_patch("S7-3", f.read_text()))


def main_rc(r, s, mf):
    return m.main(["--source-root", str(r), "--series-dir", str(s), "--manifest", str(mf)])


if __name__ == "__main__":
    unittest.main()
