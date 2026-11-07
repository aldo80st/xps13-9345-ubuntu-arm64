"""TDD regression tests for upstream source locking (no network in tests)."""
import importlib.util
import json
from pathlib import Path
from unittest import mock
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/verify-hibernate-upstream-lock.py"
spec = importlib.util.spec_from_file_location("upstream_lock", SOURCE)
lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lock)
ORIGINAL = ROOT / "docs/hibernate-upstream-projects.lock.json"


class SourceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "registry.json"
        self.data = json.loads(ORIGINAL.read_text())
        self.write()

    def write(self):
        self.file.write_text(json.dumps(self.data))

    def load(self):
        return lock.load_manifest(self.file)

    def test_offline_lock_valid_but_never_boot_authorized(self):
        x = lock.evaluate(self.load(), check_remote=False)
        self.assertEqual(x["status"], "LOCAL_LOCK_VALID")
        self.assertFalse(x["install_authorized"])
        self.assertFalse(x["release_equivalence_verified"])
        self.assertEqual(len(x["projects"]), 4)

    def test_missing_dell_reference_denied(self):
        self.data["projects"] = self.data["projects"][:1] + self.data["projects"][2:]
        self.write()
        with self.assertRaises(lock.LockInvalid):
            self.load()

    def test_duplicate_ids_rejected(self):
        self.data["projects"][2]["id"] = self.data["projects"][1]["id"]
        self.write()
        with self.assertRaises(lock.LockInvalid):
            self.load()

    def test_reject_invalid_commit_sha(self):
        self.data["projects"][0]["commit"] = "abc"
        self.write()
        with self.assertRaises(lock.LockInvalid):
            self.load()

    def test_reject_different_remote_to_block_supply_chain_swap(self):
        self.data["projects"][0]["remote"] = "https://github.com/attacker/kernel"
        self.write()
        with self.assertRaises(lock.LockInvalid):
            self.load()

    def test_reject_role_escalation(self):
        self.data["projects"][2]["role"] = "build_base"
        self.write()
        with self.assertRaises(lock.LockInvalid):
            self.load()

    def test_never_authorize_kernel_install(self):
        self.data["launch_or_install_authorized"] = True
        self.write()
        with self.assertRaises(lock.LockInvalid):
            self.load()

    def test_missing_restore_gate_denied(self):
        self.data["required_gates"].remove("upstream_pdc_restore")
        self.write()
        with self.assertRaises(lock.LockInvalid):
            self.load()

    def test_duplicate_json_keys_denied(self):
        self.file.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(lock.LockInvalid):
            self.load()

    def test_matching_remote_pins_are_verified_not_launch_ready(self):
        manifest = self.load()
        def lookup(command, **kwargs):
            project = next(p for p in manifest["projects"] if p["remote"] == command[-2])
            return mock.Mock(returncode=0, stdout=project["commit"] + "\t" + project["ref"] + "\n", stderr="")
        with mock.patch.object(lock.subprocess, "run", side_effect=lookup) as run:
            result = lock.evaluate(manifest, check_remote=True)
        self.assertEqual(result["status"], "PIN_MATCH")
        self.assertEqual(run.call_count, 4)
        self.assertFalse(result["install_authorized"])
        self.assertFalse(result["release_equivalence_verified"])

    def test_remote_branch_drift_blocks(self):
        manifest = self.load()
        def lookup(command, **kwargs):
            project = next(p for p in manifest["projects"] if p["remote"] == command[-2])
            sha = "a" * 40 if project["id"] == "ubuntu-concept-qcom-x1e" else project["commit"]
            return mock.Mock(returncode=0, stdout=sha + "\t" + project["ref"] + "\n", stderr="")
        with mock.patch.object(lock.subprocess, "run", side_effect=lookup):
            out = lock.evaluate(manifest, check_remote=True)
        self.assertEqual(out["status"], "DRIFT_DETECTED")
        self.assertIn("ubuntu-concept-qcom-x1e", out["drift"])
        self.assertFalse(out["install_authorized"])

    def test_unavailable_git_is_not_success(self):
        with mock.patch.object(lock.subprocess, "run", side_effect=FileNotFoundError()):
            out = lock.evaluate(self.load(), check_remote=True)
        self.assertEqual(out["status"], "REMOTE_UNVERIFIED")
        self.assertTrue(out["unverified"])

    def test_manifest_is_not_mutated(self):
        before = self.file.read_bytes()
        lock.evaluate(self.load(), check_remote=False)
        self.assertEqual(before, self.file.read_bytes())


if __name__ == "__main__":
    unittest.main()
