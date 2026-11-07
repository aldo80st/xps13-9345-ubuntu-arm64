"""Static + flag-validation tests for the M2 Kconfig harness. No docker is run."""
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "hibernate-m2-config.sh"
DOCKERFILE = ROOT / "container" / "Dockerfile.hibernate-kconfig"
DOC = ROOT / "docs" / "hibernate-m2-toolchain.md"


def run(*args, env=None):
    e = {"PATH": "/usr/bin:/bin"}
    e.update(env or {})
    return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, env=e)


class ScriptStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SCRIPT.read_text()

    def test_executable_and_syntax(self):
        self.assertTrue(SCRIPT.stat().st_mode & stat.S_IXUSR)
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_strict_mode(self):
        self.assertIn("set -euo pipefail", self.text)

    def test_no_privilege_or_system_mutation(self):
        code = "\n".join(l for l in self.text.splitlines() if not l.lstrip().startswith("#"))
        for bad in ("--privileged", "sudo", "--network host", "--net=host", "--pid=host",
                    "docker.sock", "eval ", "apt-get", "apt install", "--cap-add"):
            self.assertNotIn(bad, code)

    def test_no_host_boot_etc_mounts(self):
        for m in re.findall(r"(?:-v|--volume|--mount)[ =]\S+", self.text):
            self.assertNotRegex(m, r"[:=](/boot|/etc|/sys|/proc|/dev)\b")

    def test_hardening_flags(self):
        for flag in ("--cap-drop ALL", "--network none", "--read-only",
                     "no-new-privileges", "--user ", "--pids-limit", "--rm"):
            self.assertIn(flag, self.text)

    def test_mount_modes(self):
        self.assertRegex(self.text, r"/src:ro")
        self.assertRegex(self.text, r"/baseline/config:ro")
        self.assertNotRegex(self.text, r"/src(:rw|\")?\s*$" )

    def test_kbuild_invocation(self):
        for s in ("olddefconfig", "CC=aarch64-linux-gnu-gcc", "RUST_LIB_SRC",
                  "LIBCLANG_PATH", "BINDGEN", "RUSTC", "O=/out"):
            self.assertIn(s, self.text)

    def test_required_versions_checked(self):
        for s in ("15.3", "1.97.1", "0.72.1", "1.31", "22"):
            self.assertIn(s, self.text)

    def test_audit_not_suppressed(self):
        self.assertNotRegex(self.text, r"audit[^\n]*\|\|\s*(true|:)")

    def test_original_baseline_preserved(self):
        self.assertIn("sha256sum", self.text)


class ReviewFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SCRIPT.read_text()
        cls.docker = DOCKERFILE.read_text()
        cls.doc = DOC.read_text()

    def test_audit_exact_invocation(self):
        self.assertIn(
            'python3 -I -- "$AUDIT" --baseline "$BASELINE" --candidate "$OUT_RESOLVED/.config" --json',
            self.text)
        self.assertNotIn('"$AUDIT" "$BASELINE"', self.text)

    def test_audit_nonzero_not_swallowed(self):
        self.assertIn("die 7", self.text)
        self.assertIn("PIPESTATUS[0]", self.text)

    def test_hibernation_enabled_in_staging_only(self):
        self.assertIn("# CONFIG_HIBERNATION is not set", self.text)
        self.assertIn("CONFIG_HIBERNATION=y", self.text)
        self.assertIn("/out/.config", self.text)
        # edit must target the staging copy, never baseline or source
        for l in self.text.splitlines():
            if "sed" in l and "CONFIG_HIBERNATION" in l:
                self.assertIn("/out/.config", l)
                self.assertNotIn("/baseline", l)
                self.assertNotIn("/src", l)
                self.assertNotIn("-i.bak /boot", l)

    def test_hibernation_edit_before_make_and_fail_closed(self):
        i_edit = self.text.index("CONFIG_HIBERNATION=y")
        i_make = self.text.index("olddefconfig >")
        self.assertLess(i_edit, i_make)
        self.assertIn("grep -c", self.text)
        self.assertRegex(self.text, r"-eq 1|!= 1|-ne 1")

    def test_no_live_boot_mount_or_inplace(self):
        code = "\n".join(l for l in self.text.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotRegex(code, r"-v [\"$]*/boot")
        self.assertIn("cp /baseline/config /out/.config", code)

    def test_pahole_package_name(self):
        self.assertRegex(self.docker, r"(?m)^\s+pahole\b")
        self.assertNotRegex(self.docker, r"(?m)^\s+dwarves\b")

    def test_docs_source_path_and_no_overclaim(self):
        self.assertIn(".local/kernel-source/tree/linux-source-7.3.0", self.doc)
        self.assertNotIn('--source   "$PWD/.local/kernel-source"', self.doc)
        self.assertIn("--baseline FILE --candidate FILE --json", self.doc)
        self.assertIn("verificados en el XPS", self.doc)
        self.assertIn("not proof", self.doc)

    def test_nonroot_and_ro_preserved(self):
        self.assertIn("USER 10001", self.docker)
        self.assertIn("/src:ro", self.text)
        self.assertIn("/baseline/config:ro", self.text)

    def test_rust_src_validated_before_use(self):
        self.assertIn('[ -d "$RUST_LIB_SRC/core" ]', self.text)


class DockerfileStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOCKERFILE.read_text()

    def test_base_image(self):
        self.assertRegex(self.text, r"(?m)^FROM ubuntu:26\.10")

    def test_packages_and_pins(self):
        for s in ("gcc", "rust-src", "bindgen", "clang", "llvm", "libclang",
                  "pahole", "bison", "flex", "m4", "libssl-dev", "libelf-dev",
                  "1.97.1", "0.72.1", "1.31"):
            self.assertIn(s, self.text)

    def test_no_sudo_nonroot_default(self):
        self.assertNotIn("sudo", self.text)
        self.assertNotIn("--privileged", self.text)

    def test_build_time_version_checks(self):
        self.assertIn("exit 1", self.text)
        self.assertIn("provenance", self.text.lower())


class FlagValidation(unittest.TestCase):
    def test_no_args_usage_exit_2(self):
        r = run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("--source", r.stderr)

    def test_help_exit_0(self):
        self.assertEqual(run("--help").returncode, 0)

    def test_unknown_flag(self):
        self.assertEqual(run("--bogus").returncode, 2)

    def test_missing_one_required(self):
        r = run("--source", "/tmp", "--baseline", "/tmp/x")
        self.assertEqual(r.returncode, 2)

    def test_missing_value(self):
        self.assertEqual(run("--source").returncode, 2)

    def test_output_must_be_under_dot_local(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "src"); src.mkdir()
            base = Path(d, "config"); base.write_text("CONFIG_A=y\n")
            out = Path(d, "out")  # not under .local
            r = run("--source", str(src), "--baseline", str(base),
                    "--output", str(out), "--image", "img:1")
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertFalse(out.exists())

    def test_rejects_forbidden_output_and_metachar_paths(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "src"); src.mkdir()
            base = Path(d, "config"); base.write_text("x\n")
            for out in ("/boot/.local/o", "/etc/.local/o", f"{d}/.local/a;touch pwned"):
                r = run("--source", str(src), "--baseline", str(base),
                        "--output", out, "--image", "img:1")
                self.assertEqual(r.returncode, 3, (out, r.stderr))
            self.assertFalse(Path("pwned").exists())

    def test_rejects_bad_image_name(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "src"); src.mkdir()
            base = Path(d, "config"); base.write_text("x\n")
            r = run("--source", str(src), "--baseline", str(base),
                    "--output", f"{d}/.local/o", "--image", "x; id")
            self.assertEqual(r.returncode, 3)

    def test_missing_source_or_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("--source", f"{d}/nope", "--baseline", f"{d}/nope2",
                    "--output", f"{d}/.local/o", "--image", "img:1")
            self.assertEqual(r.returncode, 3)

    def test_missing_docker_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "src"); src.mkdir()
            base = Path(d, "config"); base.write_text("CONFIG_A=y\n")
            r = run("--source", str(src), "--baseline", str(base),
                    "--output", f"{d}/.local/o", "--image", "img:1",
                    env={"PATH": "/usr/bin:/bin", "HIBERNATE_M2_DOCKER": "/nonexistent/docker"})
            self.assertEqual(r.returncode, 4, r.stderr)

    def test_missing_audit_script_fails(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "src"); src.mkdir()
            base = Path(d, "config"); base.write_text("x\n")
            r = run("--source", str(src), "--baseline", str(base),
                    "--output", f"{d}/.local/o", "--image", "img:1",
                    "--audit", f"{d}/missing.py")
            self.assertEqual(r.returncode, 3)


class DocStatic(unittest.TestCase):
    def test_doc(self):
        t = DOC.read_text()
        for s in ("Exit codes", "Manifest", "hibernate-m2-config.sh", "--source",
                  "RUST_LIB_SRC", "not proof"):
            self.assertIn(s, t)
        self.assertNotRegex(t, r"(?i)hibernation (is|now) working")


if __name__ == "__main__":
    unittest.main()
