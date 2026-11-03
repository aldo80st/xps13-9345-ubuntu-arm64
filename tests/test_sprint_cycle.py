"""Behavioral tests: never exercise real hardware from unittest."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts/sprint_cycle.py'
if MODULE.exists():
    spec = importlib.util.spec_from_file_location('sprint_cycle', MODULE)
    cycle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cycle)
else:
    cycle = None


class DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(cycle, 'missing sprint_cycle implementation (expected RED)')

    def issues(self, facts):
        return {i['issue']: i for i in cycle.evaluate(facts)}

    def test_unknown_evidence_never_verifies(self):
        result = self.issues({})
        self.assertEqual(set(result), set(range(1, 9)))
        self.assertNotIn('VERIFIED', [i['state'] for i in result.values()])
        self.assertEqual(result[8]['state'], 'NOT_PLANNED')

    def test_unresolved_research_is_not_mislabeled_as_external_blocker(self):
        items = self.issues({})
        for number in (1, 2, 3, 4, 7):
            self.assertEqual(items[number]['state'], 'INVESTIGATION_NEEDED')
            self.assertEqual(items[number]['next_owner'], 'ASSISTANT')
        self.assertEqual(items[5]['next_owner'], 'USER')
        self.assertEqual(items[6]['next_owner'], 'USER')
        self.assertEqual(items[8]['next_owner'], 'NONE')

    def test_dock_and_signature_do_not_prove_two_displays(self):
        issue = self.issues({'dock_present': True, 'evdi_signed': True,
                             'secure_boot': True})[1]
        self.assertEqual(issue['state'], 'INVESTIGATION_NEEDED')
        self.assertIn('hipótesis', issue['reason'])
        self.assertTrue(issue['acceptance'])

    def test_iris_enumeration_is_not_decode(self):
        self.assertEqual(self.issues({'video_nodes': 1})[2]['state'], 'INVESTIGATION_NEEDED')
        self.assertEqual(self.issues({'iris_decode': 'passed'})[2]['state'], 'VERIFIED')
        self.assertEqual(self.issues({'iris_decode': 'failed'})[2]['state'], 'INVESTIGATION_NEEDED')
        self.assertEqual(self.issues({'iris_decode': 'permission'})[2]['state'], 'BLOCKED_USER')

    def test_pd_mapper_regression_has_all_four_gates(self):
        good = {'pd_active': True, 'pd_maps': True, 'pd_overlay': False,
                'iris_sha_official': True}
        self.assertEqual(self.issues(good)[7]['state'], 'VERIFIED')
        for key in good:
            missing = dict(good)
            del missing[key]
            self.assertNotEqual(self.issues(missing)[7]['state'], 'VERIFIED')

    def test_unsafe_functional_checks_remain_blocked(self):
        issues = self.issues({'audio_cards': 2, 'ec_sensors': 4,
                              'dc_active': True, 'dc_processes': 1})
        self.assertEqual(issues[3]['state'], 'INVESTIGATION_NEEDED')
        self.assertEqual(issues[4]['state'], 'INVESTIGATION_NEEDED')
        self.assertEqual(issues[5]['state'], 'BLOCKED_USER')
        self.assertEqual(issues[6]['state'], 'BLOCKED_USER')

    def test_iris_probe_dimensions_respect_decoder_minimum(self):
        # V4L2 IRIS advertises NV12 capture min 96x96 (observed 2026-11-03).
        # This is a static test: it must NEVER open the actual codec device.
        for name in ('decode_stateful', 'decode_stateless'):
            command = cycle.COMMANDS[name]
            caps = next(arg for arg in command if arg.startswith('video/x-raw,width='))
            import re
            match = re.search(r'width=(\d+),height=(\d+)', caps)
            self.assertIsNotNone(match)
            self.assertGreaterEqual(int(match.group(1)), 96)
            self.assertGreaterEqual(int(match.group(2)), 96)

    def test_command_whitelist_rejects_arbitrary_actions(self):
        for name in ('sudo', 'restart', 'modprobe', 'uname -a'):
            with self.assertRaises(ValueError):
                cycle.command(name)

    def test_missing_tool_is_unknown(self):
        with patch.object(cycle.subprocess, 'Popen', side_effect=FileNotFoundError):
            self.assertEqual(cycle.command('secure_boot')['status'], 'unavailable')

    def test_timeout_kills_only_own_command_group(self):
        with patch.object(cycle.subprocess, 'Popen') as start, \
                patch.object(cycle.os, 'killpg') as kill:
            process = start.return_value
            process.pid = 123456
            process.communicate.side_effect = [subprocess.TimeoutExpired('mokutil', 20),
                                               (b'', None)]
            result = cycle.command('secure_boot')
            self.assertEqual(result['status'], 'timeout')
            self.assertEqual(start.call_args.kwargs['start_new_session'], True)
            self.assertEqual(process.communicate.call_args_list[0].kwargs['timeout'], 20)
            kill.assert_called_once_with(123456, cycle.signal.SIGKILL)

    def test_collect_never_returns_raw_outputs(self):
        secret = 'secret-token host-private /home/person UUID=private serial=private'
        with patch.object(cycle, 'command', return_value={
                'status': 'failed', 'output': secret, 'returncode': 1}):
            facts = cycle.collect()
        self.assertNotIn(secret, json.dumps(facts))
        self.assertNotIn('/home/person', json.dumps(facts))
        self.assertFalse(facts.get('iris_decode') == 'passed')


if __name__ == '__main__':
    unittest.main()


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(cycle, 'run'), 'missing bounded runner (expected RED)')
        boundary = patch.object(cycle, 'command', return_value={
            'status': 'unavailable', 'output': '', 'returncode': None})
        boundary.start()
        self.addCleanup(boundary.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in ('docs/superpowers/specs', 'docs/sprint-cycles'):
            (self.root / path).mkdir(parents=True)
        (self.root / 'docs/superpowers/specs/2026-11-01-sprint-cycle.md').write_text('spec')
        (self.root / 'docs/sprint-2026-11-01-upstream-solutions-review.md').write_text('gate')
        self.output = self.root / '.local/sprint-cycles'

    def run_cycle(self, **kwargs):
        return cycle.run(self.root, self.output, collector=lambda: {}, **kwargs)

    def test_pending_assistant_investigations_cannot_masquerade_as_user_blockers(self):
        result = self.run_cycle()
        self.assertEqual(result['stop_reason'], 'assistant_work_pending')
        self.assertEqual(result['rounds'], 1)
        snapshots = list((self.output / 'iterations').glob('*.json'))
        data = json.loads(snapshots[0].read_text())
        self.assertEqual(len(data['issues']), 8)
        self.assertEqual(data['stages'], ['BASELINE', 'DISCOVER', 'DECIDE', 'PLAN',
                                         'EXECUTE', 'VERIFY', 'PERSIST', 'LOOP_GATE'])
        self.assertEqual(data['stop_reason'], 'assistant_work_pending')
        self.assertEqual(snapshots[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        self.assertEqual(len(data['spec_sha256']), 64)
        self.assertIn('checked_at', data['issues'][0])

    def pending(self, action):
        issues = cycle.evaluate({})
        issues[1]['state'] = 'READY_SAFE_ACTION'
        issues[1]['safe_actions'] = [action]
        return issues

    def test_loop_repeats_for_new_safe_work_then_converges(self):
        ready = self.pending('decode_stateful')
        with patch.object(cycle, 'evaluate', side_effect=[ready, cycle.evaluate({})]):
            result = self.run_cycle()
        self.assertEqual(result['rounds'], 2)
        self.assertEqual(result['stop_reason'], 'assistant_work_pending')

    def test_once_does_not_enter_second_round(self):
        with patch.object(cycle, 'evaluate', return_value=self.pending('decode_stateful')):
            result = self.run_cycle(once=True)
        self.assertEqual(result['rounds'], 1)
        self.assertEqual(result['stop_reason'], 'once')

    def test_no_progress_stops_in_two_rounds_without_repeating_action(self):
        with patch.object(cycle, 'evaluate', return_value=self.pending('decode_stateful')):
            result = self.run_cycle()
        self.assertEqual(result['rounds'], 2)
        self.assertEqual(result['stop_reason'], 'no_progress')
        self.assertEqual(result['actions_attempted'], ['decode_stateful'])

    def test_invalid_limits_rejected_and_cap_enforced(self):
        for limit in (0, 7, -1):
            with self.assertRaises(ValueError):
                self.run_cycle(max_rounds=limit)
        with patch.object(cycle, 'evaluate', return_value=self.pending('decode_stateful')):
            result = self.run_cycle(max_rounds=1)
        self.assertEqual(result['stop_reason'], 'max_rounds')

    def test_resume_preserves_iterations(self):
        self.run_cycle()
        first = (self.output / 'iterations/000001.json').read_bytes()
        result = self.run_cycle()
        self.assertEqual(result['last_sequence'], 2)
        self.assertEqual((self.output / 'iterations/000001.json').read_bytes(), first)
        self.assertTrue((self.root / 'docs/sprint-cycles/iteration-000002.md').exists())

    def test_corrupt_checkpoint_fails_without_overwriting(self):
        self.run_cycle()
        checkpoint = self.output / 'iterations/000001.json'
        checkpoint.write_text('{corrupt')
        with self.assertRaises(ValueError):
            self.run_cycle()
        self.assertEqual(checkpoint.read_text(), '{corrupt')

    def test_output_outside_worktree_or_symlink_rejected(self):
        with self.assertRaises(ValueError):
            cycle.run(self.root, self.root.parent / 'escape', collector=lambda: {})
        (self.root / '.local').symlink_to(self.root / 'docs', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.run_cycle()

    def test_report_identifies_who_owns_next_action(self):
        self.run_cycle()
        report = (self.root / 'docs/sprint-cycles/iteration-000001.md').read_text()
        self.assertIn('| #1 | INVESTIGATION_NEEDED | ASSISTANT |', report)
        self.assertIn('| #5 | BLOCKED_USER | USER |', report)
        self.assertIn('Responsable: ASSISTANT', report)
        self.assertNotIn('Acción humana/upstream:', report)

    def test_public_report_is_positive_allowlist_not_blacklist(self):
        secrets = {'raw_journal': 'secret HOST-internal /home/person UUID=x',
                   'kernel': 'host-secret', 'bios_version': '/home/person',
                   'iris_decode': 'token-secret'}
        cycle.run(self.root, self.output, collector=lambda: secrets)
        public = (self.root / 'docs/sprint-cycles/iteration-000001.md').read_text()
        private = (self.output / 'iterations/000001.json').read_text()
        for value in secrets.values():
            self.assertNotIn(value, public)
            self.assertNotIn(value, private)

    def test_cli_modes_and_bounds(self):
        for argv in (['--once', '--run'], ['--max-rounds', '7']):
            with self.assertRaises(SystemExit) as result:
                cycle.main(argv)
            self.assertEqual(result.exception.code, 2)


class ReadOnlyBootVerifierTests(unittest.TestCase):
    def test_boot_verifier_never_modifies_security_or_boot_state(self):
        source = (MODULE.parents[1] / 'scripts/verify-evdi-after-oneboot.sh').read_text()
        import re
        self.assertIsNone(re.search(r'\b(sudo|pkexec|reboot|modprobe|insmod|grub-editenv|update-grub)\b', source))
        self.assertIn('mokutil --sb-state', source)
        self.assertIn('EFI_NORUNTIME=NO', source)
        self.assertIn('MOK_IMPORT_LOG=FOUND', source)
        self.assertIn('NOTE=DRM connections are NOT proof', source)


class SafetyRegressionTests(unittest.TestCase):
    def test_tool_cache_and_home_stay_in_worktree(self):
        with patch.object(cycle.subprocess, 'Popen') as start:
            start.return_value.communicate.return_value = (b'', None)
            start.return_value.returncode = 0
            cycle.command('gst_parser')
        env = start.call_args.kwargs['env']
        root = MODULE.parents[1]
        self.assertTrue(Path(env.get('HOME', '/outside')).is_relative_to(root / '.local'))
        self.assertTrue(Path(env.get('GST_REGISTRY', '/outside')).is_relative_to(root / '.local'))
        self.assertTrue(Path(env.get('XDG_CACHE_HOME', '/outside')).is_relative_to(root / '.local'))

    def test_gstreamer_can_generate_private_plugin_registry(self):
        with patch.object(cycle.subprocess, 'Popen') as start:
            start.return_value.communicate.return_value = (b'', None)
            start.return_value.returncode = 0
            cycle.command('gst_stateful')
        env = start.call_args.kwargs['env']
        self.assertNotEqual(env.get('GST_REGISTRY_UPDATE'), 'no',
                            'A new private registry must permit plugin discovery')

    def test_default_collection_never_retries_unstable_iris_decoder(self):
        def fake_command(name):
            return {'status': 'ok', 'returncode': 0,
                    'output': 'qcom-iris' if name == 'v4l2' else 'available'}
        with patch.object(cycle, 'command', side_effect=fake_command) as calls:
            cycle.collect()
        invoked = [call.args[0] for call in calls.call_args_list]
        self.assertNotIn('decode_stateful', invoked,
                         'Repeated hardware decode probes can destabilize IRIS')
        self.assertNotIn('decode_stateless', invoked)
