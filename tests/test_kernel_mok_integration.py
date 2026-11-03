"""Compile the exact patched Ubuntu kernel source into a native mock-UEFI harness.

Uses an immutable GPL-2.0 Linux source fixture with validated SHA-256.
The harness NEVER touches real kernel keyrings, EFI variables or the boot.
CI executes the same C paths as the XPS without requiring APT downloads.
"""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED_SOURCE = ROOT / "tests/fixtures/ubuntu-linux-7.3.0-10.10/load_uefi.c"
PATCH = ROOT / "patches/0001-RFC-efi-mokvar-without-runtime.patch"
MOCK = ROOT / "tests/mok_runtime_harness.c"

LINUX_INCLUDES = (
    "linux/kernel.h", "linux/sched.h", "linux/cred.h", "linux/dmi.h",
    "linux/err.h", "linux/efi.h", "linux/slab.h", "linux/ima.h",
    "keys/asymmetric-type.h", "keys/system_keyring.h",
)


class NativeKernelMockTests(unittest.TestCase):
    def test_actual_kernel_source_execution_path(self):
        self.assertTrue(PINNED_SOURCE.is_file(), "Pinned source fixture missing")
        self.assertEqual(hashlib.sha256(PINNED_SOURCE.read_bytes()).hexdigest(),
                         "2abff60cd5d5fcbdd5dfde3da3ca38bd9a16dbb6b1b3b822c38596ac7128424d")
        if shutil.which("gcc") is None or shutil.which("patch") is None:
            self.skipTest("Native C compiler/patch missing")
        with tempfile.TemporaryDirectory(prefix="mok-uefi-test-") as folder:
            base = Path(folder)
            source = base / "security/integrity/platform_certs/load_uefi.c"
            source.parent.mkdir(parents=True)
            source.write_bytes(PINNED_SOURCE.read_bytes())
            (source.parent / "keyring_handler.h").write_text("")
            (source.parent.parent / "integrity.h").write_text("")
            includes = base / "fakeinclude"
            for name in LINUX_INCLUDES:
                header = includes / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text("")
            patch = subprocess.run(
                ["patch", "-p1", "-i", str(PATCH)], cwd=base,
                capture_output=True, text=True, timeout=10)
            self.assertEqual(patch.returncode, 0, patch.stdout + patch.stderr)
            output = base / "mock_harness"
            compile_cmd = [
                "gcc", "-std=gnu11", "-O0", "-Wall", "-Wextra",
                "-Wno-unused-function", "-Wno-unused-variable",
                "-I", str(includes), "-I", str(base),
                str(MOCK), "-o", str(output),
            ]
            compiled = subprocess.run(
                compile_cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            executed = subprocess.run(
                [str(output)], capture_output=True, text=True, timeout=10)
            self.assertEqual(
                executed.returncode, 0,
                executed.stdout + executed.stderr)
            self.assertIn("MOCK_CASE_7=PASS", executed.stdout)


if __name__ == "__main__":
    unittest.main()
