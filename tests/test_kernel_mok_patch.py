"""Static regressions for the RFC Ubuntu EVDI/MOK kernel patch.

These tests intentionally do not load a kernel module, mutate EFI, or
change Secure Boot. A passing test is NOT a security audit of the patch.
"""
import hashlib
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "0001-RFC-efi-mokvar-without-runtime.patch"
CACHED = ROOT / ".local" / "kernel-mok-patch" / "extracted" / "linux-source-7.3.0"
ORIGINAL = ROOT / "tests" / "fixtures" / "ubuntu-linux-7.3.0-10.10" / "load_uefi.c"
EXPECTED_SHA = "2abff60cd5d5fcbdd5dfde3da3ca38bd9a16dbb6b1b3b822c38596ac7128424d"


class KernelMokRfcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = PATCH.read_text()

    def test_patch_explicitly_prohibits_deployment(self):
        self.assertIn("RFC is NOT approved for deployment", self.patch)
        self.assertIn("SECURITY BLOCKERS BEFORE UPSTREAM OR DEPLOYMENT", self.patch)
        self.assertIn("Ubuntu 26.10 linux-source-7.3.0 7.3.0-10.10", self.patch)
        self.assertIn(EXPECTED_SHA, self.patch)

    def test_no_efi_runtime_still_checks_secboot(self):
        body = self.patch
        self.assertRegex(body, r"(?s)\+\tif \(!efi_rt_services_supported"
                         r".*?\+\t\tif \(!efi_enabled\(EFI_SECURE_BOOT\)\)"
                         r".*?\+\t\t\treturn 0;"
                         r".*?\+\t\tgoto load_mok_table;")

    def test_runtime_variable_fallback_is_restricted(self):
        self.assertIn("+\tif (!efi_rt_services_supported(EFI_RT_SUPPORTED_GET_VARIABLE))", self.patch)
        self.assertIn("+\t\treturn mokvar_entry ? rc : 0;", self.patch)

    def test_existing_mok_and_revocation_handlers(self):
        self.assertIn("get_handler_for_guid)(const efi_guid_t *) = get_handler_for_mok;", self.patch)
        self.assertIn("/* Process revocations first; failure must block positive MOK trust. */", self.patch)
        self.assertIn("return -EINVAL", self.patch)
        self.assertIn('if (!efi_mokvar_entry_find("MokListTrustedRT"))', self.patch)
        self.assertIn('if (!efi_mokvar_entry_find("MokListXRT"))', self.patch)

    def test_reproducible_exact_source_when_local_cache_present(self):
        self.assertTrue(ORIGINAL.is_file(), "Pinned fixture must ship with tests")
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(), EXPECTED_SHA)
        self.assertIn("!efi_rt_services_supported", ORIGINAL.read_text())

    def test_dryrun_when_unmodified_source_present(self):
        # A copy of the original source is enough; do not run against the
        # local patched object file or any files under /usr/src.
        self.assertTrue(ORIGINAL.is_file(), "Pinned fixture must ship with tests")
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            dst = Path(root) / "security/integrity/platform_certs/load_uefi.c"
            dst.parent.mkdir(parents=True)
            dst.write_bytes(ORIGINAL.read_bytes())
            result = subprocess.run(
                ["patch", "--dry-run", "-p1", "-i", str(PATCH)],
                cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
