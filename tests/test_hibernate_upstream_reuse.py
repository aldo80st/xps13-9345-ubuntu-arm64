"""Offline review contract: no kernel or machine state is exercised."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'docs/hibernate-upstream-reuse-manifest.json'
SCRIPT = ROOT / 'scripts/validate-hibernate-upstream-reuse.py'


class UpstreamReuseTests(unittest.TestCase):
    def run_gate(self, path=MANIFEST):
        p = subprocess.run([sys.executable, '-I', str(SCRIPT), '--manifest', str(path), '--json'],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stderr, '')
        result = json.loads(p.stdout)
        self.assertEqual(result['verdict'], 'NO_GO')
        self.assertIs(result['admitted'], False)
        return result

    def test_snapshot_is_valid_and_blocked(self):
        r = self.run_gate()
        self.assertEqual(r['errors'], [])
        for gate in ('pdc_restore', 'clock_restore', 'ppa_hibernation', 'review_lock'):
            self.assertIn(gate, r['blockers'])

    def test_missing(self):
        self.assertTrue(self.run_gate(ROOT / 'missing-reuse.json')['errors'])

    def test_bad_json_and_shapes(self):
        for raw in ('{', 'null', '[]', 'true', '{}', '{"schema_version":1,"schema_version":1}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as d:
                path = Path(d) / 'input.json'
                path.write_text(raw)
                self.assertTrue(self.run_gate(path)['errors'])

    def test_mutations_fail_closed(self):
        original = json.loads(MANIFEST.read_text())
        mutations = []
        for key, value in [('schema_version', True), ('components', []), ('gates', {}),
                           ('ppa', {}), ('unexpected', 'GO')]:
            m = copy.deepcopy(original)
            m[key] = value
            mutations.append(m)
        for key, value in [('id', 'bogus'), ('accepted', 'mainline'), ('mainline', True),
                           ('sources', ['http://example.com']), ('commit', '123abc'),
                           ('decision', 'install'), ('dell_restore', True)]:
            m = copy.deepcopy(original)
            m['components'][0][key] = value
            mutations.append(m)
        for key, value in [('pdc_restore', 'resolved'), ('clock_restore', True)]:
            m = copy.deepcopy(original)
            m['gates'][key] = value
            mutations.append(m)
        m = copy.deepcopy(original)
        m['components'].append(m['components'][0])
        mutations.append(m)
        m = copy.deepcopy(original)
        m['ppa']['hibernation'] = 'enabled'
        mutations.append(m)
        for m in mutations:
            with self.subTest(m=m), tempfile.TemporaryDirectory() as d:
                path = Path(d) / 'input.json'
                path.write_text(json.dumps(m))
                self.assertTrue(self.run_gate(path)['errors'])

    def test_read_only_and_cwd_independent(self):
        before = MANIFEST.read_bytes()
        self.run_gate()
        p = subprocess.run([sys.executable, '-I', str(SCRIPT), '--json'], cwd='/tmp',
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)['errors'], [])
        self.assertEqual(before, MANIFEST.read_bytes())


if __name__ == '__main__':
    unittest.main()
