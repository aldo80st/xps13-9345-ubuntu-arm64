"""TDD acceptance tests for the H1 Qualcomm manifest validator (fixtures only)."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hibernate-qualcomm-h1.py"
MANIFEST = ROOT / "docs" / "hibernate-qualcomm-manifest.json"
spec = importlib.util.spec_from_file_location("h1", SCRIPT)
h1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h1)

GROUPS = ["P1", "P2", "P2a", "P3", "P4", "P5"]


def real():
    return json.loads(MANIFEST.read_text())


def group(m, gid):
    return next(g for g in m["groups"] if g["id"] == gid)


class ManifestTests(unittest.TestCase):
    def test_exact_groups(self):
        self.assertEqual([g["id"] for g in real()["groups"]], GROUPS)

    def test_real_manifest_review_required(self):
        r = h1.evaluate(real())
        self.assertEqual(r["verdict"], "REVIEW_REQUIRED")
        self.assertEqual(r["errors"], [])

    def test_no_fake_hashes_or_ready(self):
        for g in real()["groups"]:
            self.assertIn(g["admission_status"], ("BLOCKED", "REVIEW_ONLY"))
            if g.get("commit_sha"):
                self.assertEqual(g["id"], "P1")

    def test_pcie_blocked(self):
        m = real()
        self.assertEqual(group(m, "P2")["admission_status"], "BLOCKED")
        self.assertEqual(group(m, "P2a")["admission_status"], "BLOCKED")
        m2 = copy.deepcopy(m)
        group(m2, "P2")["admission_status"] = "REVIEW_ONLY"
        self.assertEqual(h1.evaluate(m2)["verdict"], "NO_GO")

    def test_remoteproc_risk(self):
        m = real()
        p3 = group(m, "P3")
        self.assertEqual(p3["admission_status"], "BLOCKED")
        self.assertTrue(any(d["id"] == "remoteproc-lifecycle" and not d["resolved"] for d in p3["dependencies"]))
        blockers = [b["group"] for b in h1.evaluate(m)["blockers"]]
        self.assertIn("P3", blockers)
        m2 = copy.deepcopy(m)
        group(m2, "P3")["dependencies"] = []
        self.assertEqual(h1.evaluate(m2)["verdict"], "NO_GO")

    def test_missing_group(self):
        m = real()
        m["groups"] = [g for g in m["groups"] if g["id"] != "P4"]
        r = h1.evaluate(m)
        self.assertEqual(r["verdict"], "NO_GO")
        self.assertTrue(any("P4" in e for e in r["errors"]))

    def test_duplicate_group(self):
        m = real()
        m["groups"].append(copy.deepcopy(m["groups"][0]))
        self.assertEqual(h1.evaluate(m)["verdict"], "NO_GO")

    def test_invalid_status(self):
        m = real()
        group(m, "P5")["evidence_status"] = "landed"
        self.assertEqual(h1.evaluate(m)["verdict"], "NO_GO")
        m = real()
        group(m, "P5")["admission_status"] = "MAYBE"
        self.assertEqual(h1.evaluate(m)["verdict"], "NO_GO")

    def test_ready_with_unresolved_deps(self):
        m = real()
        group(m, "P2")["admission_status"] = "READY"
        self.assertEqual(h1.evaluate(m)["verdict"], "NO_GO")

    def test_silent_abi_claim(self):
        m = real()
        group(m, "P1")["abi_claim"] = "compatible"
        self.assertEqual(h1.evaluate(m)["verdict"], "NO_GO")

    def test_ubuntu_present_must_be_bool_or_null(self):
        m = real()
        group(m, "P1")["ubuntu_7_3_10_present"] = "no"
        self.assertEqual(h1.evaluate(m)["verdict"], "NO_GO")

    def test_bad_sha(self):
        m = real()
        group(m, "P2")["commit_sha"] = "deadbeef"
        self.assertEqual(h1.evaluate(m)["verdict"], "NO_GO")

    def test_secret_rejected(self):
        m = real()
        group(m, "P1")["notes"] = "token ghp_" + "a" * 36
        r = h1.evaluate(m)
        self.assertEqual(r["verdict"], "NO_GO")
        self.assertNotIn("ghp_" + "a" * 36, json.dumps(r))

    def test_real_manifest_has_no_secrets(self):
        self.assertEqual(h1.scan_secrets(MANIFEST.read_text()), [])

    def test_zero_trust_non_object(self):
        for bad in (None, [], "x", {"groups": "x"}, {}):
            self.assertEqual(h1.evaluate(bad)["verdict"], "NO_GO")

    def test_unknown_url_scheme(self):
        m = real()
        group(m, "P1")["url"] = "file:///etc/passwd"
        self.assertEqual(h1.evaluate(m)["verdict"], "NO_GO")


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True)

    def test_default_manifest_exit_zero(self):
        p = self.run_cli("--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["verdict"], "REVIEW_REQUIRED")

    def test_missing_file(self):
        p = self.run_cli("--manifest", "/nonexistent/x.json", "--json")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["verdict"], "NO_GO")

    def test_invalid_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "m.json"
            f.write_text("{not json")
            p = self.run_cli("--manifest", str(f), "--json")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["verdict"], "NO_GO")

    def test_read_only(self):
        before = MANIFEST.read_bytes()
        self.run_cli("--json")
        self.assertEqual(MANIFEST.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
