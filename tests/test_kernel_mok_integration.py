"""Execute the exact patched Ubuntu Linux C file against simulated EFI services.

Kernel source fixture is from Ubuntu 7.3.0-10.10 with SHA-256 pinning.
These are isolated userspace tests, NOT validation of kernel-trust security.
No real Secure Boot, bootloader, EFI, MOK, modules, or keyrings are changed.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED_SOURCE = ROOT / "tests/fixtures/ubuntu-linux-7.3.0-10.10/load_uefi.c"
PATCH = ROOT / "patches/0001-RFC-efi-mokvar-without-runtime.patch"
MOCK = ROOT / "tests/mok_runtime_harness.c"
EXPECTED_SHA = "2abff60cd5d5fcbdd5dfde3da3ca38bd9a16dbb6b1b3b822c38596ac7128424d"

LINUX_INCLUDES = (
    "linux/kernel.h", "linux/sched.h", "linux/cred.h", "linux/dmi.h",
    "linux/err.h", "linux/efi.h", "linux/slab.h", "linux/ima.h",
    "keys/asymmetric-type.h", "keys/system_keyring.h",
)


class NativeKernelMockTests(unittest.TestCase):
    def _run_real_c_harness(self, extra_flags, sanitized=False):
        self.assertTrue(PINNED_SOURCE.is_file(), "Pinned source fixture missing")
        self.assertEqual(hashlib.sha256(PINNED_SOURCE.read_bytes()).hexdigest(),
                         EXPECTED_SHA)
        if shutil.which("gcc") is None or shutil.which("patch") is None:
            self.skipTest("Native C compiler and patch required")
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
                ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(PATCH)],
                cwd=base, capture_output=True, text=True, timeout=10)
            self.assertEqual(patch.returncode, 0, patch.stdout + patch.stderr)
            output = base / "mok_harness"
            compile_cmd = [
                "gcc", "-std=gnu11", "-Wall", "-Wextra",
                "-Wno-unused-function", "-Wno-unused-variable",
                *extra_flags, "-I", str(includes), "-I", str(base),
                str(MOCK), "-o", str(output),
            ]
            compiled = subprocess.run(
                compile_cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0,
                             compiled.stdout + compiled.stderr)
            env = os.environ.copy()
            if sanitized:
                env["ASAN_OPTIONS"] = "detect_leaks=1:halt_on_error=1"
                env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
            executed = subprocess.run(
                [str(output)], capture_output=True, text=True,
                timeout=15, env=env)
            self.assertEqual(executed.returncode, 0,
                             executed.stdout + executed.stderr)
            for number in range(1, 8):
                self.assertIn(f"MOCK_CASE_{number}=PASS", executed.stdout)

    def test_actual_kernel_source_execution_path(self):
        self._run_real_c_harness(["-O0"])

    def test_address_and_undefined_sanitizers(self):
        self._run_real_c_harness(
            ["-O1", "-g", "-fsanitize=address,undefined",
             "-fno-omit-frame-pointer"],
            sanitized=True,
        )


if __name__ == "__main__":
    unittest.main()
