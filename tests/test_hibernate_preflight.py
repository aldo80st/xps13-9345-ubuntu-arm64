"""Read-only hibernation preflight acceptance tests (isolated fixtures only)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hibernate-preflight.py"
spec = importlib.util.spec_from_file_location("hibernate_preflight", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HibernatePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write("boot/config-test", "CONFIG_HIBERNATION=y\nCONFIG_ARCH_HIBERNATION_POSSIBLE=y\n")
        self.write("sys/power/state", "freeze mem disk\n")
        self.write("proc/meminfo", "MemTotal: 1024000 kB\n")
        self.write("proc/swaps", "Filename Type Size Used Priority\n/swap.img file 2097152 0 -1\n")
        self.write("proc/cmdline", "root=UUID=secret-uuid quiet\n")
        self.write("etc/default/grub.d/ubuntu-x1e-settings.cfg", "GRUB_CMDLINE_LINUX=\"clk_ignore_unused pd_ignore_unused\"\n")
        self.write("sys/class/dmi/id/bios_version", "2.14.0\n")
        self.write("sys/class/dmi/id/product_name", "XPS 13 9345\n")

    def write(self, path, value):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(value, encoding="utf-8")

    def result(self):
        return module.assess(module.inspect(self.root, "test"))

    def test_favorable_is_only_ready_for_evaluation(self):
        self.assertEqual(self.result()["status"], "READY_FOR_EVALUATION")
        self.assertNotIn("hibernation_working", self.result())

    def test_kernel_disabled_blocks_even_if_disk_exposed(self):
        self.write("boot/config-test", "# CONFIG_HIBERNATION is not set\n")
        res = self.result()
        self.assertEqual(res["status"], "BLOCKED")
        self.assertIn("kernel_config_disabled", res["blockers"])

    def test_disk_missing_blocks_even_if_config_enabled(self):
        self.write("sys/power/state", "freeze mem\n")
        res = self.result()
        self.assertEqual(res["status"], "BLOCKED")
        self.assertIn("disk_state_unavailable", res["blockers"])

    def test_missing_swaps_unknown_not_fabricated(self):
        (self.root / "proc/swaps").unlink()
        res = self.result()
        self.assertEqual(res["status"], "UNKNOWN")
        self.assertIsNone(res["observed"]["swap_kib"])

    def test_swap_smaller_than_ram_warning_not_definitive_block(self):
        self.write("proc/swaps", "Filename Type Size Used Priority\n/swap.img file 20480 0 -1\n")
        res = self.result()
        self.assertEqual(res["status"], "READY_FOR_EVALUATION")
        self.assertIn("swap_below_ram_conservative_target", res["warnings"])

    def test_kernel_and_state_unknown_fail_closed(self):
        (self.root / "boot/config-test").unlink()
        (self.root / "sys/power/state").unlink()
        self.assertEqual(self.result()["status"], "UNKNOWN")

    def test_grub_and_boot_efi_flags_are_separate(self):
        self.write("etc/default/grub.d/ubuntu-x1e-settings.cfg", "GRUB_CMDLINE_LINUX=\"efi=noruntime\"\n")
        res = self.result()["observed"]
        self.assertTrue(res["efi_noruntime_configured"])
        self.assertFalse(res["efi_noruntime_active"])
        self.write("proc/cmdline", "root=UUID=secret efi=noruntime\n")
        self.assertTrue(self.result()["observed"]["efi_noruntime_active"])

    def test_no_sensitive_strings_leaked(self):
        self.write("proc/cmdline", "root=UUID=SENSITIVE-UUID token=SENSITIVE-TOKEN efi=noruntime\n")
        self.write("proc/swaps", "Filename Type Size Used Priority\n/home/secret-user/very-private-swap.img file 2097152 0 -1\n")
        self.write("etc/default/grub.d/ubuntu-x1e-settings.cfg", "GRUB_CMDLINE_LINUX=\"efi=noruntime passport=SENSITIVE-PASSPORT\"\n")
        raw = json.dumps(self.result(), sort_keys=True)
        for forbidden in ("SENSITIVE-", "secret-user", "very-private-swap", "passport", "UUID="):
            self.assertNotIn(forbidden, raw)

    def test_swap_header_only_is_zero_not_unknown(self):
        self.write("proc/swaps", "Filename Type Size Used Priority\n")
        res = self.result()
        self.assertEqual(res["status"], "BLOCKED")
        self.assertIn("no_swap", res["blockers"])


if __name__ == "__main__":
    unittest.main()
