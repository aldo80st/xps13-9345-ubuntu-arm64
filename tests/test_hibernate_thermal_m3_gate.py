"""M3 compatibility gate: static, no live firmware/kernel operations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hibernate-thermal-m3-gate.py"
spec = importlib.util.spec_from_file_location("m3_thermal_gate", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SCMI = {
    "CONFIG_ARM_SCMI_CPUFREQ": "m",
    "CONFIG_CPU_FREQ": "y",
    "CONFIG_CPU_FREQ_GOV_ONDEMAND": "y",
    "CONFIG_CPU_FREQ_GOV_SCHEDUTIL": "y",
    "CONFIG_ARM_SCMI_PROTOCOL": "y",
}


class CompatibilityGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.src = self.root / "tree"
        self.patches = self.root / "patches"
        self.base = self.root / "baseline.config"
        self.cand = self.root / "candidate.config"
        self.write(self.base, "\n".join(f"{k}={v}" for k, v in SCMI.items()) + "\n# CONFIG_HIBERNATION is not set\n")
        self.write(self.cand, "\n".join(f"{k}={v}" for k, v in SCMI.items()) + "\nCONFIG_HIBERNATION=y\nCONFIG_EC_DELL_XPS=m\n")
        self.write(self.src / "drivers/platform/arm64/dell-xps-ec.c",
                   "static const struct dev_pm_ops dell_xps_ec_pm_ops = { "
                   "SYSTEM_SLEEP_PM_OPS(dell_xps_ec_suspend, dell_xps_ec_resume) };\n")
        self.write(self.src / "drivers/platform/arm64/Kconfig", "config EC_DELL_XPS\n tristate \"Dell XPS 9345 EC\"\n")
        self.write(self.src / "drivers/platform/arm64/Makefile",
                   "obj-$(CONFIG_EC_DELL_XPS) += dell-xps-ec.o\n")
        self.write(self.src / "arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts",
                   "&i2c5 { status = \"okay\"; embedded-controller@3b { compatible = \"dell,xps13-9345-ec\"; }; };\n")
        self.write(self.src / "Documentation/devicetree/bindings/embedded-controller/dell,xps13-9345-ec.yaml",
                   "title: Dell XPS 13 9345 EC\n")
        self.expected_hashes = {}
        for i in (1, 2, 3):
            name = f"v8-{i}.diff"
            payload = f"diff --git a/x b/x\npatch {i}\n"
            self.write(self.patches / name, payload)
            self.expected_hashes[name] = hashlib.sha256(payload.encode()).hexdigest()

    def write(self, dest, value):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(value, encoding="utf-8")

    def inspect(self):
        return module.inspect(self.src, self.base, self.cand, self.patches, self.expected_hashes)

    def test_fully_present_static_artifacts_only_require_review(self):
        result = self.inspect()
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["blockers"], [])
        self.assertNotIn("GO", result.get("approval", ""))

    def test_missing_ec_driver_is_no_go_even_if_hibernation_and_scmi_pass(self):
        (self.src / "drivers/platform/arm64/dell-xps-ec.c").unlink()
        result = self.inspect()
        self.assertEqual(result["status"], "NO_GO")
        self.assertIn("ec_driver_missing", result["blockers"])
        self.assertTrue(result["checks"]["scmi_cpufreq_preserved"])

    def test_ec_disabled_in_candidate_is_no_go(self):
        self.write(self.cand, self.cand.read_text().replace("CONFIG_EC_DELL_XPS=m", "# CONFIG_EC_DELL_XPS is not set"))
        self.assertIn("ec_config_disabled", self.inspect()["blockers"])

    def test_scmi_frequency_driver_regression_is_no_go(self):
        self.write(self.cand, self.cand.read_text().replace("CONFIG_ARM_SCMI_CPUFREQ=m", "# CONFIG_ARM_SCMI_CPUFREQ is not set"))
        result = self.inspect()
        self.assertEqual(result["status"], "NO_GO")
        self.assertIn("scmi_cpufreq_regression", result["blockers"])

    def test_patch_hash_mismatch_is_no_go(self):
        self.write(self.patches / "v8-2.diff", "tampered patch content\n")
        self.assertIn("ec_patch_provenance_mismatch", self.inspect()["blockers"])

    def test_missing_patch_is_no_go(self):
        (self.patches / "v8-3.diff").unlink()
        self.assertIn("ec_patch_provenance_mismatch", self.inspect()["blockers"])

    def test_missing_device_tree_node_is_no_go(self):
        self.write(self.src / "arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts", "&i2c5 { status = \"disabled\"; };")
        self.assertIn("ec_dts_node_missing", self.inspect()["blockers"])

    def test_missing_pm_callbacks_is_no_go(self):
        self.write(self.src / "drivers/platform/arm64/dell-xps-ec.c", "int initialized;")
        self.assertIn("ec_power_management_unreviewed", self.inspect()["blockers"])

    def test_missing_binding_or_build_wiring_is_no_go(self):
        (self.src / "Documentation/devicetree/bindings/embedded-controller/dell,xps13-9345-ec.yaml").unlink()
        self.assertIn("ec_binding_missing", self.inspect()["blockers"])
        self.write(self.src / "drivers/platform/arm64/Makefile", "# no EC module\n")
        self.assertIn("ec_build_wiring_missing", self.inspect()["blockers"])

    def test_hibernation_not_enabled_is_no_go(self):
        self.write(self.cand, self.cand.read_text().replace("CONFIG_HIBERNATION=y", "# CONFIG_HIBERNATION is not set"))
        self.assertIn("hibernation_config_disabled", self.inspect()["blockers"])

    def test_missing_config_is_no_go_not_unknown_approval(self):
        self.base.unlink()
        result = self.inspect()
        self.assertEqual(result["status"], "NO_GO")
        self.assertIn("scmi_cpufreq_regression", result["blockers"])

    def test_duplicate_relevant_config_fails_closed(self):
        self.write(self.cand, self.cand.read_text() + "\nCONFIG_ARM_SCMI_CPUFREQ=m\n")
        self.assertIn("scmi_cpufreq_regression", self.inspect()["blockers"])

    def test_no_sensitive_path_or_content_in_json(self):
        self.write(self.cand, self.cand.read_text() + "# token=very-secret-123 password=mysecret\n")
        data = json.dumps(self.inspect())
        for sensitive in ("very-secret-123", "mysecret", str(self.root), "UUID=", "/home/"):
            self.assertNotIn(sensitive, data)

    def test_inspection_does_not_modify_inputs(self):
        paths = [self.base, self.cand, self.patches / "v8-1.diff"]
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        self.inspect()
        after = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
