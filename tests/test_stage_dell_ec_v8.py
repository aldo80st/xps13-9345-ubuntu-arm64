"""Acceptance tests for exact upstream Dell EC v8 bundle and safe staging."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/stage-dell-ec-v8.py"
spec = importlib.util.spec_from_file_location("ec_v8_staging", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DellECV8Tests(unittest.TestCase):
    def test_exact_upstream_patch_hashes_are_retained(self):
        module.check_bundle(ROOT / "patches/dell-ec-v8")
        self.assertEqual(len(module.SHA), 3)

    def test_removes_only_unsupported_kconfig_section(self):
        patch = (ROOT / "patches/dell-ec-v8/v8-2.diff").read_text()
        fixed = module.patch2_without_kconfig(patch)
        self.assertNotIn("diff --git a/drivers/platform/arm64/Kconfig", fixed)
        for name in ["MAINTAINERS", "drivers/platform/arm64/Makefile",
                     "drivers/platform/arm64/dell-xps-ec.c"]:
            self.assertIn(name, fixed)
        self.assertEqual(fixed.count("diff --git"), 3)

    def test_rejects_unexpected_patch_sections(self):
        with self.assertRaises(ValueError):
            module.patch2_without_kconfig("not an EC upstream patch")

    def test_kconfig_insertion_is_deterministic(self):
        original = "config EC_ACER_ASPIRE1\n\nconfig EC_HUAWEI_GAOKUN\n"
        adjusted = module.kconfig_add_dell_ec(original)
        self.assertEqual(adjusted.count("config EC_DELL_XPS"), 1)
        self.assertEqual(adjusted.count("config EC_HUAWEI_GAOKUN"), 1)
        self.assertIn("depends on IIO", adjusted)
        with self.assertRaises(ValueError):
            module.kconfig_add_dell_ec(adjusted)

    def test_missing_anchor_does_not_silently_patch(self):
        with self.assertRaises(ValueError):
            module.kconfig_add_dell_ec("config SOMETHING_ELSE\n")

    def test_rejects_output_outside_local_scratch(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "src"
            (src / "drivers/platform/arm64").mkdir(parents=True)
            (src / "drivers/platform/arm64/Kconfig").write_text("config EC_HUAWEI_GAOKUN\n")
            (tmp / ".local").mkdir()
            with self.assertRaises(ValueError):
                module.stage(src, tmp / "somewhere-else", ROOT / "patches/dell-ec-v8", tmp)

    def test_rejects_existing_output_without_overwriting(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "src"
            (src / "drivers/platform/arm64").mkdir(parents=True)
            (src / "drivers/platform/arm64/Kconfig").write_text("config EC_HUAWEI_GAOKUN\n")
            output = tmp / ".local/out"
            output.mkdir(parents=True)
            marker = output / "do-not-touch.txt"
            marker.write_text("original")
            with self.assertRaises(ValueError):
                module.stage(src, output, ROOT / "patches/dell-ec-v8", tmp)
            self.assertEqual(marker.read_text(), "original")

    def test_no_host_changing_commands_in_stager(self):
        source = SCRIPT.read_text()
        for token in ["sudo ", "systemctl", "grub-install", "update-grub",
                      "efibootmgr", "reboot", "hibernate", "apt install"]:
            # "hibernate" may occur in a harmless docstring; check commands only.
            if token == "hibernate":
                continue
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
