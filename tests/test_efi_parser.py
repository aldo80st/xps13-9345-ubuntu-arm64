"""Execute the genuine Ubuntu EFI signature-list parser against synthetic buffers.

The parser source is pinned to the Linux 7.3.0-10.10 source package.
Only isolated userspace binaries are executed, never live EFI services.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/ubuntu-linux-7.3.0-10.10/efi_parser.c"
HARNESS = ROOT / "tests/efi_parser_harness.c"
SHA256 = "ceec33b9e14193ad9ef7e191f17bbdb1c6c43f252f07dce1cfb8cdcf877fa1e7"


class EfiSignatureParserTests(unittest.TestCase):
    def _execute_parser(self, sanitizer):
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SHA256)
        if not shutil.which("gcc"):
            self.skipTest("GCC unavailable")
        with tempfile.TemporaryDirectory(prefix="efi-signature-parser-") as folder:
            base = Path(folder)
            source = base / "security/integrity/platform_certs/efi_parser.c"
            source.parent.mkdir(parents=True)
            source.write_bytes(SOURCE.read_bytes())
            inc = base / "include/linux"
            inc.mkdir(parents=True)
            for header in ("module.h", "printk.h", "err.h", "efi.h"):
                (inc / header).write_text("")
            output = base / "efi_parser_test"
            cmd = [
                "gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                "-O1" if sanitizer else "-O0",
                *(
                    ["-g", "-fsanitize=address,undefined",
                     "-fno-omit-frame-pointer"] if sanitizer else []
                ),
                "-I", str(base / "include"), "-I", str(base),
                str(HARNESS), "-o", str(output),
            ]
            compiled = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0,
                             compiled.stdout + compiled.stderr)
            env = os.environ.copy()
            if sanitizer:
                env["ASAN_OPTIONS"] = "detect_leaks=1:halt_on_error=1"
                env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
            executed = subprocess.run(
                [str(output)], capture_output=True, text=True,
                timeout=15, env=env)
            self.assertEqual(executed.returncode, 0,
                             executed.stdout + executed.stderr)
            for case in ("single_and_double", "unknown_guid", "truncations",
                         "malformed_lengths", "deterministic_mutations"):
                self.assertIn(f"EFI_PARSER_{case}=PASS", executed.stdout)

    def test_real_kernel_efi_parser(self):
        self._execute_parser(sanitizer=False)

    def test_real_kernel_efi_parser_with_asan_ubsan(self):
        self._execute_parser(sanitizer=True)


if __name__ == "__main__":
    unittest.main()
