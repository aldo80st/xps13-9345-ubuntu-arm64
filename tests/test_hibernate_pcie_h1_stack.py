"""TDD tests for the fail-closed H1 PCIe stack checker (offline, synthetic fixtures)."""
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hibernate-pcie-h1-stack.py"
MANIFEST = ROOT / "docs" / "hibernate-pcie-h1-stack.json"
spec = importlib.util.spec_from_file_location("pcie_h1", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

CALLERS = ["pci-imx6.c", "pci-layerscape.c", "pcie-eswin.c", "pcie-nxp-s32g.c", "pcie-qcom.c",
           "pcie-rcar-gen4.c", "pcie-stm32.c", "pcie-ultrarisc.c"]
D = "drivers/pci/controller/dwc/"

S2 = "Subject: [PATCH v7 2/3] PCI: dwc: Force L2\n\n" + "".join(
    f"diff --git a/{D}{c} b/{D}{c}\n-\tx = dw_pcie_suspend_noirq(pci);\n+\tx = dw_pcie_suspend_noirq(pci, false);\n"
    for c in CALLERS) + (
    f"diff --git a/{D}pcie-designware.h b/{D}pcie-designware.h\n"
    "+int dw_pcie_suspend_noirq(struct dw_pcie *pci, bool force);\n"
    f"diff --git a/{D}pcie-designware-host.c b/{D}pcie-designware-host.c\n"
    "+\tif (!d3cold_possible && !force && !pci->pp.suspend_poweroff)\n")
S2 = S2.replace("dw_pcie_suspend_noirq(pci, false);\n+", "dw_pcie_suspend_noirq(pci, false);\n+", 1)
# qcom call site uses pcie->pci
S2 = S2.replace(f"diff --git a/{D}pcie-qcom.c b/{D}pcie-qcom.c\n-\tx = dw_pcie_suspend_noirq(pci);\n+\tx = dw_pcie_suspend_noirq(pci, false);",
                f"diff --git a/{D}pcie-qcom.c b/{D}pcie-qcom.c\n-\tret = dw_pcie_suspend_noirq(pcie->pci);\n+\tret = dw_pcie_suspend_noirq(pcie->pci, false);")
S1 = "Subject: [PATCH v7 1/3] PCI: host-common: Fix early bus-walk\n\n+\t\t\t*flags &= ~PCI_HOST_D3COLD_ALLOWED;\n"
S3 = ("Subject: [PATCH v7 3/3] PCI: qcom: Implement shutdown() callback\n\n"
      "+static void qcom_pcie_shutdown(struct platform_device *pdev)\n"
      "+\t\tdw_pcie_suspend_noirq(pcie->pci, true);\n+\t.shutdown = qcom_pcie_shutdown,\n")
P2 = ("Subject: [PATCH v2] PCI: qcom: Power the controller down when hibernating\n\n"
      f"diff --git a/{D}pcie-qcom.c b/{D}pcie-qcom.c\n"
      "-\tret = dw_pcie_suspend_noirq(pcie->pci, false);\n+\tret = dw_pcie_suspend_noirq(pcie->pci, force);\n"
      "+\treturn qcom_pcie_suspend(dev, true);\n+\t.freeze_noirq = pm_sleep_ptr(qcom_pcie_freeze_noirq),\n")
FILES = {"s7-1.patch": S1, "s7-2.patch": S2, "s7-3.patch": S3, "p2-v2.patch": P2}


def sha(t):
    return hashlib.sha256(t.encode()).hexdigest()


def fixture_manifest(resolved=False, with_sha=True):
    mf = json.loads(MANIFEST.read_text())
    for p in mf["patches"]:
        if p["file"] in FILES:
            p["sha256"] = sha(FILES[p["file"]]) if with_sha else None
    mf["expected_force_callsites"] = {D + c: "false" for c in CALLERS}
    if resolved:
        mf["reconciliation"]["status"] = "verified"
        mf["reconciliation"]["evidence"] = "fixture"
        for d in mf["known_defects"]:
            d["resolved"] = True
        mf["dell_evidence"] = {"machine": "Dell XPS 13 9345", "nvme_resume": True, "wifi_resume": True, "tested_kernel": "fixture"}
    return mf


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for k, v in FILES.items():
            (self.dir / k).write_text(v)
        self.src = self.dir / "tree"
        (self.src / "drivers/pci/controller/dwc").mkdir(parents=True)
        for c in CALLERS:
            (self.src / "drivers/pci/controller/dwc" / c).write_text("x = dw_pcie_suspend_noirq(pci);\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_(self, mf, series=True, src=True):
        return m.evaluate(mf, series_dir=self.dir if series else None, source_root=self.src if src else None)


class RealManifest(unittest.TestCase):
    def test_real_manifest_is_no_go_not_error(self):
        r = m.evaluate(json.loads(MANIFEST.read_text()))
        self.assertEqual(r["verdict"], "NO_GO")
        self.assertTrue(r["unmet"])

    def test_version_mismatch_flagged(self):
        r = m.evaluate(json.loads(MANIFEST.read_text()))
        self.assertTrue(any("VERSION_MISMATCH" in f for f in r["unmet"] + r["failures"]))

    def test_graph_consistent(self):
        mf = json.loads(MANIFEST.read_text())
        ids = {p["id"] for p in mf["patches"]}
        for p in mf["patches"]:
            for d in p["requires"]:
                self.assertIn(d, ids)

    def test_cli_exit_1(self):
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "check", "--json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(json.loads(r.stdout)["verdict"], "NO_GO")


class Checker(Base):
    def test_all_evidence_present_is_go(self):
        r = self.run_(fixture_manifest(resolved=True))
        self.assertEqual((r["verdict"], r["failures"], r["unmet"]), ("GO", [], []))

    def test_unresolved_reconciliation_never_go(self):
        mf = fixture_manifest(resolved=True)
        mf["reconciliation"]["status"] = "unresolved"
        self.assertEqual(self.run_(mf)["verdict"], "NO_GO")

    def test_wrong_version_in_series(self):
        mf = fixture_manifest(resolved=True)
        (self.dir / "s7-2.patch").write_text(S2.replace("v7", "v6"))
        mf["patches"][[p["id"] for p in mf["patches"]].index("S7-2")]["sha256"] = sha(S2.replace("v7", "v6"))
        r = self.run_(mf)
        self.assertEqual(r["verdict"], "NO_GO")
        self.assertTrue(any("WRONG_VERSION" in f for f in r["failures"]))

    def test_missing_patch_file(self):
        (self.dir / "s7-3.patch").unlink()
        r = self.run_(fixture_manifest(resolved=True))
        self.assertEqual(r["verdict"], "NO_GO")
        self.assertTrue(any("MISSING_PATCH" in f for f in r["failures"]))

    def test_sha_mismatch(self):
        (self.dir / "s7-1.patch").write_text(S1 + "tamper\n")
        r = self.run_(fixture_manifest(resolved=True))
        self.assertTrue(any("SHA_MISMATCH" in f for f in r["failures"]))

    def test_no_sha_in_manifest_is_not_go(self):
        self.assertEqual(self.run_(fixture_manifest(resolved=True, with_sha=False))["verdict"], "NO_GO")

    def test_missing_callsite_in_patch(self):
        bad = S2.replace(f"diff --git a/{D}pcie-stm32.c b/{D}pcie-stm32.c\n-\tx = dw_pcie_suspend_noirq(pci);\n+\tx = dw_pcie_suspend_noirq(pci, false);\n", "")
        (self.dir / "s7-2.patch").write_text(bad)
        mf = fixture_manifest(resolved=True)
        next(p for p in mf["patches"] if p["id"] == "S7-2")["sha256"] = sha(bad)
        r = self.run_(mf)
        self.assertEqual(r["verdict"], "NO_GO")
        self.assertTrue(any("MISSING_CALLSITE" in f and "pcie-stm32.c" in f for f in r["failures"]))

    def test_tree_caller_not_covered(self):
        (self.src / "drivers/pci/controller/dwc/pcie-extra.c").write_text("dw_pcie_suspend_noirq(pci);\n")
        r = self.run_(fixture_manifest(resolved=True))
        self.assertTrue(any("UNCOVERED_TREE_CALLER" in f and "pcie-extra.c" in f for f in r["failures"]))

    def test_no_source_root_not_go(self):
        r = self.run_(fixture_manifest(resolved=True), src=False)
        self.assertEqual(r["verdict"], "NO_GO")
        self.assertTrue(any("SOURCE_ROOT" in u for u in r["unmet"]))

    def test_no_series_dir_not_go(self):
        self.assertEqual(self.run_(fixture_manifest(resolved=True), series=False)["verdict"], "NO_GO")

    def test_p2_preimage_not_in_series(self):
        bad = P2.replace("pcie->pci, false", "pcie->pci, 0")
        (self.dir / "p2-v2.patch").write_text(bad)
        mf = fixture_manifest(resolved=True)
        next(p for p in mf["patches"] if p["id"] == "P2")["sha256"] = sha(bad)
        r = self.run_(mf)
        self.assertTrue(any("P2_PREIMAGE" in f for f in r["failures"]))

    def test_unresolved_defect_blocks(self):
        mf = fixture_manifest(resolved=True)
        mf["known_defects"][0]["resolved"] = False
        self.assertEqual(self.run_(mf)["verdict"], "NO_GO")

    def test_no_dell_evidence_blocks(self):
        mf = fixture_manifest(resolved=True)
        mf["dell_evidence"] = None
        self.assertEqual(self.run_(mf)["verdict"], "NO_GO")

    def test_lenovo_evidence_not_dell(self):
        mf = fixture_manifest(resolved=True)
        mf["dell_evidence"] = {"machine": "Lenovo Yoga Slim 7x", "nvme_resume": True, "wifi_resume": True}
        self.assertEqual(self.run_(mf)["verdict"], "NO_GO")

    def test_cycle_and_dangling_dependency(self):
        mf = fixture_manifest(resolved=True)
        next(p for p in mf["patches"] if p["id"] == "S7-1")["requires"] = ["P2"]
        self.assertEqual(self.run_(mf)["verdict"], "NO_GO")
        mf = fixture_manifest(resolved=True)
        next(p for p in mf["patches"] if p["id"] == "P2")["requires"].append("NOPE")
        self.assertEqual(self.run_(mf)["verdict"], "NO_GO")

    def test_bad_input_types(self):
        for bad in (None, [], {}, {"patches": "x"}):
            self.assertEqual(m.evaluate(bad)["verdict"], "NO_GO")

    def test_non_lore_url_rejected(self):
        mf = fixture_manifest(resolved=True)
        mf["patches"][0]["url"] = "http://example.com/x"
        self.assertEqual(self.run_(mf)["verdict"], "NO_GO")


STAGED = ROOT / ".local" / "h1-pcie" / "stack"


@unittest.skipUnless(STAGED.is_dir(), "staged series absent (run `stage --out .local/h1-pcie/stack`)")
class RealStaged(unittest.TestCase):
    def test_real_series_has_no_contradictions_but_stays_no_go(self):
        r = m.evaluate(json.loads(MANIFEST.read_text()), series_dir=STAGED)
        self.assertEqual(r["failures"], [])
        self.assertEqual(r["verdict"], "NO_GO")


class Split(unittest.TestCase):
    def test_split_mbox_extracts_numbered_patches(self):
        mb = ("From a Mon Jan 1 00:00:00 2001\nSubject: [PATCH v7 2/3] x\nMessage-Id: <a@b>\n\nbody2\n\n"
              "From a Mon Jan 1 00:00:00 2001\nSubject: Re: [PATCH v7 2/3] x\nMessage-Id: <c@d>\n\nreply\n").encode()
        out = m.split_mbox(mb)
        self.assertEqual(list(out), [("v7", 2)])
        self.assertIn("body2", out[("v7", 2)])


if __name__ == "__main__":
    unittest.main()
