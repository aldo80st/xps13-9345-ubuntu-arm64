"""Offline admission tests; none simulates or verifies remote firmware."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/hibernate-remoteproc-h1.py'
CONTRACT = ROOT / 'docs/hibernate-remoteproc-h1.json'


class LifecycleGateTests(unittest.TestCase):
    def run_gate(self, path=CONTRACT):
        p = subprocess.run([sys.executable, '-I', str(SCRIPT), '--contract', str(path)],
                           capture_output=True, text=True)
        self.assertEqual(p.stderr, '', 'gate must handle input without traceback')
        self.assertEqual(p.returncode, 1, 'unknown lifecycle must deny admission')
        r = json.loads(p.stdout)
        self.assertEqual(r['verdict'], 'NO_GO')
        self.assertIs(r['admitted'], False)
        return r

    def test_checked_in_contract_is_valid_but_blocks(self):
        r = self.run_gate()
        self.assertEqual(r['errors'], [])
        self.assertEqual(len(r['blockers']), 6)
        self.assertEqual(set(r), {'verdict', 'admitted', 'errors', 'blockers'})

    def test_missing_input_denies(self):
        self.assertTrue(self.run_gate(ROOT / 'absent-contract.json')['errors'])

    def test_malformed_and_non_object_inputs_deny(self):
        for raw in ('{', 'null', '[]', '1', '{}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as d:
                p = Path(d) / 'contract.json'
                p.write_text(raw)
                self.assertTrue(self.run_gate(p)['errors'])

    def test_mutations_cannot_unlock_or_drop_blockers(self):
        original = json.loads(CONTRACT.read_text())
        mutations = [dict(original, verdict='GO'), dict(original, schema_version=True),
                     dict(original, requirements={}), dict(original, dell_verified=True),
                     dict(original, requirements={k: 'VERIFIED' for k in original['requirements']}),
                     dict(original, requirements={k: True for k in original['requirements']}),
                     dict(original, unexpected='ignored evidence')]
        for data in mutations:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as d:
                p = Path(d) / 'contract.json'
                p.write_text(json.dumps(data))
                self.assertTrue(self.run_gate(p)['errors'])

    def test_read_only(self):
        before = CONTRACT.read_bytes()
        self.run_gate()
        self.assertEqual(before, CONTRACT.read_bytes())


if __name__ == '__main__':
    unittest.main()
