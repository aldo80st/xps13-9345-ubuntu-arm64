"""Tests for the offline, fail-closed Canonical qcom-x1e config comparison."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit-qcom-x1e-baseline.py"

BASE = {
    "HIBERNATION": "n",
    "SUSPEND": "y",
    "ARCH_HIBERNATION_POSSIBLE": "y",
    "ARM_SCMI_CPUFREQ": "m",
    "PCIE_QCOM": "y",
    "QCOM_SMP2P": "m",
    "QCOM_PDC": "y",
    "SWAP": "y",
    "CPU_FREQ": "y",
    "PM_SLEEP": "y",
    "HOTPLUG_CPU": "y",
}


def render(config):
    return "".join(
        f"# CONFIG_{key} is not set\n" if value == "n" else
        f"CONFIG_{key}={value}\n"
        for key, value in sorted(config.items())
    )


class QcomBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.current = self.root / "current.config"
        self.candidate = self.root / "candidate.config"
        self.current.write_text(render(BASE))
        self.candidate.write_text(render(BASE))

    def run_cli(self, extra=()):
        p = subprocess.run(
            [sys.executable, str(SCRIPT), "--current-config", str(self.current),
             "--candidate-config", str(self.candidate),
             "--candidate-release", "7.3.0-31-qcom-x1e", "--json", *extra],
            capture_output=True, text=True, timeout=10,
        )
        return p, json.loads(p.stdout)

    def test_both_kernels_disabled_is_no_go(self):
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(output["status"], "NO_GO")
        self.assertIn("HIBERNATION_NOT_ENABLED", output["blockers"])
        self.assertFalse(output["boot_authorized"])
        self.assertEqual(output["observed"]["candidate"]["HIBERNATION"], "n")

    def test_candidate_hibernation_enabled_requires_review_not_boot(self):
        self.candidate.write_text(render({**BASE, "HIBERNATION": "y"}))
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 0)
        self.assertEqual(output["status"], "REVIEW_REQUIRED")
        self.assertFalse(output["boot_authorized"])

    def test_disabled_scmi_blocks(self):
        self.candidate.write_text(render({**BASE, "ARM_SCMI_CPUFREQ": "n"}))
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 1)
        self.assertIn("REGRESSION_ARM_SCMI_CPUFREQ", output["blockers"])

    def test_disabled_pcie_blocks(self):
        self.candidate.write_text(render({**BASE, "PCIE_QCOM": "n"}))
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 1)
        self.assertIn("REGRESSION_PCIE_QCOM", output["blockers"])

    def test_missing_critical_symbol_fails_closed(self):
        invalid = {k: v for k, v in BASE.items() if k != "QCOM_PDC"}
        self.candidate.write_text(render(invalid))
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 2)
        self.assertEqual(output["status"], "ERROR")
        self.assertFalse(output["boot_authorized"])

    def test_invalid_config_duplicate_rejected(self):
        self.candidate.write_text(render(BASE) + "CONFIG_HIBERNATION=y\n")
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 2)
        self.assertEqual(output["status"], "ERROR")

    def test_missing_file_is_error(self):
        self.candidate.unlink()
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 2)
        self.assertEqual(output["status"], "ERROR")

    def test_malformed_symbol_value_is_error(self):
        self.candidate.write_text(render(BASE).replace("CONFIG_SWAP=y", "CONFIG_SWAP=oops"))
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 2)
        self.assertEqual(output["status"], "ERROR")

    def test_undefined_dell_ec_remains_unknown(self):
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(output["observed"]["candidate"]["EC_DELL_XPS"], "UNKNOWN")
        self.assertFalse(output["boot_authorized"])

    def test_no_sensitive_local_paths_in_json(self):
        p, output = self.run_cli()
        self.assertEqual(p.returncode, 1)
        self.assertNotIn(str(self.root), p.stdout)

    def test_never_mutates_files(self):
        before = (self.current.read_bytes(), self.candidate.read_bytes())
        self.run_cli()
        self.assertEqual(before, (self.current.read_bytes(), self.candidate.read_bytes()))


if __name__ == "__main__":
    unittest.main()
