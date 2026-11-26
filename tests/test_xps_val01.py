"""Synthetic, hermetic tests for XPS-VAL-01 evidence collection and comparison."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
COLLECTOR = REPO / "scripts/xps_val01_collect.py"
COMPARE = REPO / "scripts/xps_val01_compare.py"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class XpsVal01Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file("etc/os-release", 'PRETTY_NAME="Ubuntu 26.10"\n')
        self.file("sys/class/dmi/id/product_name", "XPS 13 9345\n")
        self.file("sys/class/dmi/id/bios_version", "2.14.0\n")
        for cluster in (0, 4, 8):
            for k, v in {"scaling_driver": "scmi", "scaling_governor": "ondemand",
                         "scaling_min_freq": "710400", "scaling_max_freq": "3417600"}.items():
                self.file(f"sys/devices/system/cpu/cpufreq/policy{cluster}/{k}", v)
        self.file("sys/class/thermal/thermal_zone0/temp", "56000")
        self.file("sys/class/video4linux/video16/name", "qcom-iris-decoder")
        self.file("sys/class/video4linux/video17/name", "qcom-iris-encoder")
        self.file("sys/class/drm/card5-eDP-1/status", "connected")
        self.file("sys/class/drm/card5-eDP-1/mode", "2880x1800")
        self.file("sys/class/net/wlP4p1s0/statistics/rx_packets", "300")
        self.file("sys/class/net/wlP4p1s0/statistics/rx_dropped", "1")
        self.file("sys/class/net/wlP4p1s0/statistics/rx_errors", "0")
        self.file("sys/class/power_supply/usb/type", "USB")
        self.file("sys/class/power_supply/usb/online", "1")
        self.collector = load_module(COLLECTOR, "xps_val01_collect")
        self.analyzer = load_module(COMPARE, "xps_val01_compare")

    def file(self, relative, content):
        p = self.root / relative
        p.parent.mkdir(exist_ok=True, parents=True)
        p.write_text(content)

    def test_isolated_fixture_disables_host_probes(self):
        p = subprocess.run([sys.executable, str(COLLECTOR), "--root", str(self.root),
                            "--no-commands"], text=True, capture_output=True, timeout=8)
        self.assertEqual(p.returncode, 0, p.stderr)
        x = json.loads(p.stdout)
        self.assertEqual(x["os"]["kernel"], None)
        self.assertEqual(x["hardware"]["bios"], "2.14.0")
        self.assertEqual(len(x["cpu"]["policies"]), 3)
        self.assertEqual(x["video"]["iris_devices"], ["qcom-iris-decoder", "qcom-iris-encoder"])
        self.assertEqual(x["display"]["connected"][0]["class"], "internal")
        self.assertFalse(x["video"]["chrome_vaapi_validated"])

    def test_fixture_without_no_commands_is_rejected(self):
        p = subprocess.run([sys.executable, str(COLLECTOR), "--root", str(self.root)],
                           capture_output=True, timeout=8)
        self.assertNotEqual(p.returncode, 0)

    def test_no_sensitive_identifiers_or_paths_exported(self):
        self.file("sys/class/net/wlP4p1s0/ssid", "SENSITIVE_NETWORK")
        self.file("sys/class/dmi/id/product_serial", "SENSITIVE_SERIAL")
        self.file("sys/class/drm/card5-eDP-1/edid", "SENSITIVE_EDID")
        out = json.dumps(self.collector.inventory(self.root, False))
        for forbidden in ("SENSITIVE_NETWORK", "SENSITIVE_SERIAL", "SENSITIVE_EDID",
                          "wlP4p1s0", str(self.root), "192.168", "user_name"):
            self.assertNotIn(forbidden, out)
        self.assertIn('"wifi"', out)

    def test_bogus_temperature_and_bios_do_not_escape_allowlist(self):
        self.file("sys/class/thermal/thermal_zone1/temp", "9999999")
        self.file("sys/class/dmi/id/bios_version", "SECRET/..\nBAD")
        x = self.collector.inventory(self.root, False)
        self.assertEqual(x["thermal"]["valid_sensors"], 1)
        self.assertIsNone(x["hardware"]["bios"])

    def test_missing_sysfs_is_observational_not_success(self):
        x = self.collector.inventory(self.root / "absent", False)
        self.assertEqual(x["cpu"]["policies"], [])
        self.assertEqual(x["video"]["iris_devices"], [])
        self.assertFalse(x["video"]["chrome_vaapi_validated"])

    def test_snapshots_never_authorize_adoption(self):
        x = self.collector.inventory(self.root, False)
        result = self.analyzer.compare(x, x)
        self.assertEqual(result["decision"], "REVIEW_REQUIRED")
        self.assertFalse(result["adoption_authorized"])
        self.assertFalse(result["cause_confirmed"])
        self.assertEqual(result["changes"], [])

    def test_network_counter_and_kernel_delta_are_not_causality(self):
        x = self.collector.inventory(self.root, False)
        y = json.loads(json.dumps(x))
        x["os"]["kernel"], y["os"]["kernel"] = "7.3.0-10", "7.3.0-11"
        y["network"]["wifi"]["rx_dropped"] = 4
        result = self.analyzer.compare(x, y)
        self.assertIn("KERNEL_CHANGED_REQUIRES_BASELINE", [f["kind"] for f in result["findings"]])
        self.assertIn("NETWORK_COUNTER_INCREASE", [f["kind"] for f in result["findings"]])
        self.assertFalse(result["cause_confirmed"])

    def test_missing_iris_is_flagged_not_auto_fixed(self):
        x = self.collector.inventory(self.root, False)
        y = json.loads(json.dumps(x))
        y["video"]["iris_devices"] = []
        result = self.analyzer.compare(x, y)
        self.assertIn("IRIS_DECODER_NOT_ENUMERATED", [f["kind"] for f in result["findings"]])

    def test_invalid_schema_fails_closed(self):
        with self.assertRaises(ValueError):
            self.analyzer.compare({"schema": "invalid"}, {"schema": "invalid"})

    def test_counter_reset_not_mistaken_as_improvement(self):
        x = self.collector.inventory(self.root, False)
        y = json.loads(json.dumps(x))
        y["network"]["wifi"]["rx_packets"] = 1
        result = self.analyzer.compare(x, y)
        self.assertIn("COUNTER_RESET_OR_REBOOT", [f["kind"] for f in result["findings"]])


if __name__ == "__main__":
    unittest.main()
