"""Acceptance tests for the read-only Kconfig hibernation audit (fixtures only)."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit-hibernate-config.py"
spec = importlib.util.spec_from_file_location("audit_hibernate_config", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

BASE = "# Linux/arm64 Kernel Configuration\nCONFIG_SWAP=y\n# CONFIG_HIBERNATION is not set\nCONFIG_ARCH_HIBERNATION_POSSIBLE=y\n"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def audit(self, base, cand):
        b, c = self.root / "base.config", self.root / "cand.config"
        if base is not None:
            b.write_text(base)
        if cand is not None:
            c.write_text(cand)
        return module.audit(b, c)

    def test_clean_with_only_hibernation_delta(self):
        cand = BASE.replace("# CONFIG_HIBERNATION is not set", "CONFIG_HIBERNATION=y") + \
            "CONFIG_HIBERNATE_CALLBACKS=y\nCONFIG_HIBERNATION_COMP_LZO=y\nCONFIG_HIBERNATION_DEF_COMP=\"lzo\"\n"
        r = self.audit(BASE, cand)
        self.assertEqual(r["status"], "CLEAN")
        self.assertEqual(r["expected_changed"],
                         ["CONFIG_HIBERNATE_CALLBACKS", "CONFIG_HIBERNATION",
                          "CONFIG_HIBERNATION_COMP_LZO", "CONFIG_HIBERNATION_DEF_COMP"])
        self.assertEqual(r["unrelated_changed"], [])
        self.assertTrue(r["hibernation_evidence"])

    def test_no_change_is_clean_without_evidence(self):
        r = self.audit(BASE, BASE)
        self.assertEqual(r["status"], "CLEAN")
        self.assertFalse(r["hibernation_evidence"])
        self.assertTrue(any("no evidence" in n for n in r["notes"]))

    def test_kernel_symbol_names_can_contain_lowercase_letters(self):
        """Real Ubuntu 7.3 Kconfig uses x in CONFIG_MT76x02_LIB and 8x8."""
        base = BASE + "CONFIG_MT76x02_LIB=m\nCONFIG_FONT_8x8=y\n"
        result = self.audit(base, base)
        self.assertEqual(result["status"], "CLEAN")
        self.assertEqual(result["errors"], [])

    def test_unrelated_drift(self):
        r = self.audit(BASE, BASE + "CONFIG_FOO=y\n")
        self.assertEqual(r["status"], "UNRELATED_DRIFT")
        self.assertEqual(r["unrelated_changed"], ["CONFIG_FOO"])

    def test_value_change_and_removal_detected(self):
        r = self.audit(BASE, "# CONFIG_SWAP is not set\n# CONFIG_HIBERNATION is not set\n")
        self.assertEqual(r["status"], "UNRELATED_DRIFT")
        self.assertEqual(r["unrelated_changed"], ["CONFIG_ARCH_HIBERNATION_POSSIBLE", "CONFIG_SWAP"])

    def test_mixed_expected_and_unrelated_is_drift(self):
        cand = BASE.replace("# CONFIG_HIBERNATION is not set", "CONFIG_HIBERNATION=y") + "CONFIG_BAR=m\n"
        r = self.audit(BASE, cand)
        self.assertEqual(r["status"], "UNRELATED_DRIFT")
        self.assertEqual(r["expected_changed"], ["CONFIG_HIBERNATION"])

    def test_toolchain_flags(self):
        base = BASE + "CONFIG_RUST=y\nCONFIG_BPF_SYSCALL=y\nCONFIG_PAHOLE_VERSION=130\nCONFIG_GCC_VERSION=150000\nCONFIG_DEBUG_INFO_BTF=y\n"
        cand = BASE + "# CONFIG_RUST is not set\n# CONFIG_BPF_SYSCALL is not set\nCONFIG_PAHOLE_VERSION=0\nCONFIG_GCC_VERSION=0\n# CONFIG_DEBUG_INFO_BTF is not set\n"
        r = self.audit(base, cand)
        self.assertEqual(r["status"], "UNRELATED_DRIFT")
        self.assertEqual(r["flags"]["rust"], ["CONFIG_RUST"])
        self.assertEqual(r["flags"]["bpf"], ["CONFIG_BPF_SYSCALL", "CONFIG_DEBUG_INFO_BTF"])
        self.assertEqual(r["flags"]["pahole"], ["CONFIG_PAHOLE_VERSION"])
        self.assertEqual(r["flags"]["gcc"], ["CONFIG_GCC_VERSION"])

    def test_duplicates_unknown(self):
        r = self.audit(BASE + "CONFIG_SWAP=n\n", BASE)
        self.assertEqual(r["status"], "UNKNOWN")

    def test_malformed_unknown(self):
        for bad in ("garbage line\n", "CONFIG_X = y\n", "# CONFIG_X is maybe set\n", "CONFIG_lower =y\n"):
            with self.subTest(bad=bad):
                self.assertEqual(self.audit(BASE, BASE + bad)["status"], "UNKNOWN")

    def test_unreadable_unknown(self):
        r = module.audit(self.root / "missing", self.root / "also-missing")
        self.assertEqual(r["status"], "UNKNOWN")

    def test_empty_file_unknown(self):
        self.assertEqual(self.audit("", BASE)["status"], "UNKNOWN")

    def test_output_has_no_values_or_paths(self):
        secret = "CONFIG_DEFAULT_HOSTNAME=\"s3cret-host\"\n"
        r = self.audit(BASE, BASE + secret)
        text = json.dumps(r)
        self.assertNotIn("s3cret", text)
        self.assertNotIn(str(self.root), text)
        self.assertIn("CONFIG_DEFAULT_HOSTNAME", text)

    def test_error_output_has_no_paths(self):
        r = module.audit(self.root / "missing", self.root / "x")
        self.assertNotIn(str(self.root), json.dumps(r))

    def test_inputs_not_modified(self):
        self.audit(BASE, BASE + "CONFIG_FOO=y\n")
        self.assertEqual((self.root / "base.config").read_text(), BASE)

    def run_cli(self, base, cand, *extra):
        (self.root / "b").write_text(base)
        (self.root / "c").write_text(cand)
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--baseline", str(self.root / "b"),
                               "--candidate", str(self.root / "c"), *extra],
                              capture_output=True, text=True)

    def test_cli_exit_codes_and_json(self):
        ok = self.run_cli(BASE, BASE.replace("# CONFIG_HIBERNATION is not set", "CONFIG_HIBERNATION=y"), "--json")
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(json.loads(ok.stdout)["status"], "CLEAN")
        drift = self.run_cli(BASE, BASE + "CONFIG_FOO=y\n", "--json")
        self.assertNotEqual(drift.returncode, 0)
        self.assertEqual(json.loads(drift.stdout)["status"], "UNRELATED_DRIFT")
        unk = self.run_cli(BASE, "junk\n", "--json")
        self.assertNotEqual(unk.returncode, 0)
        self.assertEqual(json.loads(unk.stdout)["status"], "UNKNOWN")
        self.assertNotEqual(drift.returncode, unk.returncode)

    def test_cli_text_mode(self):
        r = self.run_cli(BASE, BASE)
        self.assertEqual(r.returncode, 0)
        self.assertIn("CLEAN", r.stdout)


if __name__ == "__main__":
    unittest.main()
