"""Synthetic lexical fixtures do not establish Linux or Dell correctness."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/remoteproc-source'
SMP = 'drivers/soc/qcom/smp2p.c'
PAS = 'drivers/remoteproc/qcom_q6v5_pas.c'
CORE = 'drivers/remoteproc/remoteproc_core.c'


class SourceCheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name) / 'linux'
        shutil.copytree(FIXTURES / 'base', self.tree)

    def run_gate(self, *extra):
        result = subprocess.run(
            [sys.executable, '-I', str(ROOT / 'scripts/hibernate-remoteproc-h1.py'),
             '--source-tree', str(self.tree), *extra], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, '')
        report = json.loads(result.stdout)
        self.assertEqual(report['verdict'], 'NO_GO')
        self.assertIs(report['admitted'], False)
        self.assertEqual(len(report['blockers']), 6)
        if extra:
            self.assertTrue(report['errors'])
        else:
            self.assertEqual(report['errors'], [])
        source = report['source_report']
        self.assertIn('PAS_LIFECYCLE_UNRECONCILED', source['reason_codes'])
        self.assertIn('C7_REMOTEPROC_SMP2P_EQUIVALENCE_UNPROVEN', source['reason_codes'])
        return source

    def patched(self):
        shutil.copyfile(FIXTURES / 'p3/smp2p.c', self.tree / SMP)

    def mutate(self, file, old, new):
        p = self.tree / file
        self.assertIn(old, p.read_text())
        p.write_text(p.read_text().replace(old, new))

    def test_missing_restore_and_local_pas_pm_absence(self):
        r = self.run_gate()
        self.assertIn('SMP2P_RESTORE_MISSING', r['reason_codes'])
        self.assertEqual(r['smp2p_restore'], 'missing')
        self.assertEqual(r['pas_driver_pm'], 'absent')
        self.assertEqual(r['pas_pm_hooks']['freeze'], 'not_registered')
        self.assertEqual(r['pas_pm_hooks']['restore_noirq'], 'not_registered')
        self.assertIn('PAS_DRIVER_PM_ABSENT', r['reason_codes'])
        self.assertEqual(r['files'][CORE]['missing_definitions'], [])

    def test_boolean_smp2p_check_ssr_definition_is_not_marked_missing(self):
        self.mutate(SMP, 'static void qcom_smp2p_check_ssr(struct qcom_smp2p *smp2p) {}',
                    'static bool qcom_smp2p_check_ssr(struct qcom_smp2p *smp2p) { return true; }')
        report = self.run_gate()
        self.assertEqual(report['files'][SMP]['missing_definitions'], [])
        self.assertEqual(report['files'][SMP]['definitions']['qcom_smp2p_check_ssr'],
                         ['struct qcom_smp2p *smp2p'])

    def test_proposal_shape_still_denies_and_fingerprints_without_writes(self):
        self.patched()
        before = {p.relative_to(self.tree): p.read_bytes()
                  for p in self.tree.rglob('*') if p.is_file()}
        r = self.run_gate()
        self.assertEqual(r['smp2p_restore'], 'expected_shape')
        self.assertIn('SMP2P_RESTORE_SHAPE_OBSERVED', r['reason_codes'])
        self.assertNotIn('SMP2P_RESTORE_MISSING', r['reason_codes'])
        self.assertEqual(r['files'][SMP]['sha256'], hashlib.sha256(before[Path(SMP)]).hexdigest())
        self.assertEqual(before, {p.relative_to(self.tree): p.read_bytes()
                                 for p in self.tree.rglob('*') if p.is_file()})

    def test_disconnected_or_incomplete_restore_is_unrecognized(self):
        for old, new in [('.pm = &qcom_smp2p_pm_ops', '.pm = &other_ops'),
                         ('pm_sleep_ptr(qcom_smp2p_restore_noirq)', 'other_restore'),
                         ('smp2p->ssr_ack = false;', ''),
                         ('list_for_each_entry_reverse', 'list_for_each_entry'),
                         ('if (ret < 0)\n  return ret;', ''),
                         ('static int qcom_smp2p_restore_noirq',
                          'static void qcom_smp2p_restore_noirq'),
                         ('struct device *dev)', 'struct rproc *dev)')]:
            with self.subTest(old=old):
                self.patched()
                self.mutate(SMP, old, new)
                self.assertEqual(self.run_gate()['smp2p_restore'], 'unrecognized')

    def test_comments_strings_prototypes_and_calls_are_not_definitions(self):
        p = self.tree / SMP
        p.write_text(p.read_text() + '\n/* static int qcom_smp2p_restore_noirq(struct device *dev) {} */\n'
                     'const char *noise = "qcom_smp2p_restore_noirq() { }";\n'
                     'static int qcom_smp2p_restore_noirq(struct device *dev);\n')
        self.assertEqual(self.run_gate()['smp2p_restore'], 'missing')
        self.mutate(CORE, 'int rproc_boot(struct rproc *rproc) { return 0; }',
                    'int rproc_boot(struct rproc *rproc);\nvoid test(void) { rproc_boot(rproc); }')
        r = self.run_gate()
        self.assertIn('rproc_boot', r['files'][CORE]['missing_definitions'])
        self.assertIn('EXPECTED_API_MISSING', r['reason_codes'])

    def test_pas_pm_presence_never_establishes_compensation(self):
        self.mutate(PAS, '.name = "qcom_q6v5_pas"',
                    '.name = "qcom_q6v5_pas", .pm = &invented_ops')
        r = self.run_gate()
        self.assertEqual(r['pas_driver_pm'], 'present')
        self.assertEqual(r['pas_pm_hooks']['restore'], 'unknown')

    def test_pas_exact_hook_expressions_and_macro_ambiguity(self):
        self.mutate(PAS, '.name = "qcom_q6v5_pas"',
                    '.name = "qcom_q6v5_pas", .pm = &pas_pm')
        p = self.tree / PAS
        original = p.read_text()
        p.write_text(original + '\nstatic const struct dev_pm_ops pas_pm = {\n'
                     ' .freeze = pas_freeze, .restore = pm_sleep_ptr(pas_restore),\n};\n')
        r = self.run_gate()
        self.assertEqual(r['pas_pm_hooks']['freeze'], 'pas_freeze')
        self.assertEqual(r['pas_pm_hooks']['restore'], 'pm_sleep_ptr(pas_restore)')
        self.assertEqual(r['pas_pm_hooks']['thaw'], 'absent')
        p.write_text(original + '\nstatic const struct dev_pm_ops pas_pm = {\n'
                     ' SET_SYSTEM_SLEEP_PM_OPS(pas_suspend, pas_resume)\n};\n')
        self.assertEqual(self.run_gate()['pas_pm_hooks']['freeze'], 'unknown')

    def test_unrecognized_driver_or_conditional_source_is_explicit(self):
        self.mutate(PAS, 'qcom_pas_driver =', 'historical_driver =')
        self.assertEqual(self.run_gate()['pas_driver_pm'], 'unknown')
        self.patched()
        p = self.tree / SMP
        p.write_text('#if 0\n' + p.read_text() + '\n#endif\n')
        r = self.run_gate()
        self.assertIn('PREPROCESSOR_NOT_EVALUATED', r['reason_codes'])

    def test_unreadable_invalid_or_escaping_sources_are_unknown(self):
        for kind in ('missing', 'encoding', 'directory', 'symlink', 'large'):
            with self.subTest(kind=kind):
                p = self.tree / SMP
                if p.exists() or p.is_symlink():
                    if p.is_dir():
                        p.rmdir()
                    else:
                        p.unlink()
                if kind == 'encoding':
                    p.write_bytes(b'\xff')
                elif kind == 'directory':
                    p.mkdir()
                elif kind == 'symlink':
                    p.symlink_to(FIXTURES / 'p3/smp2p.c')
                elif kind == 'large':
                    p.write_bytes(b' ' * (4 * 1024 * 1024 + 1))
                r = self.run_gate()
                self.assertEqual(r['smp2p_restore'], 'unknown')
                self.assertIn('SOURCE_INPUT_UNREADABLE', r['reason_codes'])

    def test_bad_contract_is_not_bypassed_by_source(self):
        self.patched()
        self.run_gate('--contract', str(self.tree / 'missing.json'))

    def test_missing_root_is_unknown_and_symlink_parent_is_not_followed(self):
        shutil.rmtree(self.tree)
        r = self.run_gate()
        self.assertTrue(all(f['status'] == 'unknown' for f in r['files'].values()))
        shutil.copytree(FIXTURES / 'base', self.tree)
        shutil.rmtree(self.tree / 'drivers/soc')
        (self.tree / 'drivers/soc').symlink_to(FIXTURES / 'base/drivers/soc',
                                              target_is_directory=True)
        self.assertEqual(self.run_gate()['smp2p_restore'], 'unknown')

    def test_duplicate_definition_and_unbalanced_source_are_not_positive(self):
        self.patched()
        p = self.tree / SMP
        original = p.read_text()
        p.write_text(original + '\nstatic int qcom_smp2p_restore_noirq(struct device *dev) {}\n')
        self.assertEqual(self.run_gate()['smp2p_restore'], 'unrecognized')
        p.write_text(original.replace('qcom_smp2p_kick(smp2p);', 'qcom_smp2p_kick(smp2p); {'))
        self.assertEqual(self.run_gate()['smp2p_restore'], 'unknown')


if __name__ == '__main__':
    unittest.main()
