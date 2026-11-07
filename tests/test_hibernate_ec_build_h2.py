"""H2 boundary tests; fake Docker records arguments and never executes a build."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/hibernate-ec-build-h2.sh'
CONFIG = ('CONFIG_HIBERNATION=y\nCONFIG_EC_DELL_XPS=m\n'
          'CONFIG_ARM_SCMI_CPUFREQ=m\nCONFIG_CPU_FREQ=y\n'
          'CONFIG_CPU_FREQ_GOV_ONDEMAND=y\nCONFIG_CPU_FREQ_GOV_SCHEDUTIL=y\n'
          'CONFIG_ARM_SCMI_PROTOCOL=y\n')


class H2(unittest.TestCase):
    def setUp(self):
        (ROOT / '.local').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.local')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / 'source'
        self.src.mkdir()
        for name in ('Makefile', 'drivers/platform/arm64/dell-xps-ec.c',
                     'arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts'):
            p = self.src / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('fixture\n')
        self.cfg = self.root / 'config'
        self.cfg.write_text(CONFIG)
        self.out = self.root / 'out'
        self.log = self.root / 'docker.jsonl'
        self.docker = self.root / 'docker'
        self.docker.write_text('''#!/usr/bin/python3
import json, os, sys
with open(os.environ['H2_LOG'], 'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
if sys.argv[1] == 'info': print(os.environ.get('H2_SECURITY', '["name=apparmor","name=seccomp","name=cgroupns"]'))
elif sys.argv[1:3] == ['image', 'inspect']: print('sha256:fixture')
elif sys.argv[1] == 'run': sys.exit(19)
''')
        self.docker.chmod(0o755)

    def test_writable_source_accepted_without_permission_changes(self):
        before = {str(p): (p.stat().st_mode, p.read_bytes() if p.is_file() else None)
                  for p in [self.src, *self.src.rglob('*')]}
        self.assertEqual(self.run_h2(*self.args()).returncode, 6)
        after = {str(p): (p.stat().st_mode, p.read_bytes() if p.is_file() else None)
                 for p in [self.src, *self.src.rglob('*')]}
        self.assertEqual(before, after)

    def run_h2(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], text=True, capture_output=True,
                              env={**os.environ, 'HIBERNATE_H2_DOCKER': str(self.docker),
                                   'H2_LOG': str(self.log)})

    def args(self):
        return ['--source', str(self.src), '--config', str(self.cfg),
                '--output', str(self.out), '--image', 'test:local']

    def test_missing_and_unknown_arguments(self):
        for args in ([], ['--source'], ['--bogus']):
            self.assertEqual(self.run_h2(*args).returncode, 2)

    def test_invalid_and_existing_output(self):
        for out in ('/tmp/h2-output', str(self.src / 'out')):
            args = self.args(); args[5] = out
            self.assertEqual(self.run_h2(*args).returncode, 3)
        self.out.mkdir()
        self.assertEqual(self.run_h2(*self.args()).returncode, 3)
        self.assertFalse(self.log.exists())

    def test_missing_duplicate_or_changed_symbols(self):
        for text in (CONFIG.replace('CONFIG_EC_DELL_XPS=m\n', ''),
                     CONFIG.replace('CONFIG_HIBERNATION=y', 'CONFIG_HIBERNATION=n'),
                     CONFIG + 'CONFIG_ARM_SCMI_CPUFREQ=m\n',
                     CONFIG.replace('CONFIG_CPU_FREQ_GOV_ONDEMAND=y', 'CONFIG_CPU_FREQ_GOV_ONDEMAND=n')):
            self.cfg.write_text(text)
            self.assertEqual(self.run_h2(*self.args()).returncode, 3)
        self.assertFalse(self.log.exists())

    def test_rootful_daemon_accepted(self):
        r = self.run_h2(*self.args())
        self.assertEqual(r.returncode, 6, r.stderr)  # fake build failure, not daemon rejection
        self.assertTrue(self.out.exists())
        self.assertTrue(any(json.loads(s)[0] == 'run' for s in self.log.read_text().splitlines()))

    def test_optional_baseline_scmi_must_match(self):
        baseline = self.root / 'baseline'
        baseline.write_text(CONFIG.replace('CONFIG_ARM_SCMI_PROTOCOL=y', 'CONFIG_ARM_SCMI_PROTOCOL=m'))
        r = self.run_h2(*self.args(), '--baseline', str(baseline))
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(self.log.exists())

    def test_output_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'escape').symlink_to(outside, target_is_directory=True)
            args = self.args()
            args[5] = str(self.root / 'escape' / 'out')
            self.assertEqual(self.run_h2(*args).returncode, 3)
            self.assertFalse((Path(outside) / 'out').exists())
        self.assertFalse(self.log.exists())

    def test_container_boundary_and_failure_provenance(self):
        r = self.run_h2(*self.args())
        self.assertEqual(r.returncode, 6, r.stderr)
        calls = [json.loads(s) for s in self.log.read_text().splitlines()]
        run = next(c for c in calls if c[0] == 'run')
        for flag, value in (('--network', 'none'), ('--cap-drop', 'ALL'),
                            ('--security-opt', 'no-new-privileges'), ('--pull', 'never'),
                            ('--user', f'{os.getuid()}:{os.getgid()}'),
                            ('--pids-limit', '256'), ('--memory', '2g')):
            self.assertEqual(run[run.index(flag)+1], value)
        self.assertIn('--read-only', run)
        self.assertIn(f'{self.src}:/src:ro', run)
        self.assertIn(f'{self.cfg}:/input/config:ro', run)
        mounts = [run[i+1] for i, arg in enumerate(run) if arg == '-v']
        self.assertEqual(mounts, [f'{self.src}:/src:ro', f'{self.cfg}:/input/config:ro',
                                  f'{self.out / "build"}:/out:rw'])
        for forbidden in ('--privileged', '--cap-add', '--pid=host', 'docker.sock'):
            self.assertNotIn(forbidden, ' '.join(run))
        manifest = (self.out / 'manifest.txt').read_text()
        for key in ('config_sha256=', 'image_id=', 'container_exit=19', 'source_makefile_sha256='):
            self.assertIn(key, manifest)
        self.assertIn(f'{self.out / "build"}:/out:rw', run)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.out / 'build').stat().st_mode & 0o777, 0o700)
        self.assertNotRegex(SCRIPT.read_text(), r'(?:^|\s)/(?:boot|efi|lib/modules)(?:/|\s)')
        inner = run[-1]
        self.assertIn('umask 022', inner)
        for target in ('modules_prepare', 'drivers/platform/arm64/dell-xps-ec.o',
                       'qcom/x1e80100-dell-xps13-9345.dtb', '-j1', 'O=/out'):
            self.assertIn(target, inner)
        for forbidden in ('efibootmgr', 'sudo', 'chmod', 'modules_install', 'depmod', 'systemctl', 'dracut', 'reboot', 'make install'):
            self.assertNotIn(forbidden, SCRIPT.read_text())


class H2BuildImage(unittest.TestCase):
    def test_dwarf_build_dependency_in_separate_layer(self):
        image = ROOT / 'container/Dockerfile.hibernate-ec-build-h2'
        self.assertTrue(image.is_file(), 'H2 image layer missing')
        text = image.read_text()
        self.assertIn('FROM xps-hibernate-kconfig:ubuntu26.10', text)
        self.assertIn('libdw-dev', text)
        self.assertIn('USER 0', text)
        self.assertIn('USER 10001', text)
        self.assertIn('/etc/hibernate-ec-build-h2-packages.txt', text)
        self.assertIn('#include <dwarf.h>', text)
        self.assertIn('#include <elfutils/libdw.h>', text)

    def test_harness_records_h2_dependencies(self):
        text = SCRIPT.read_text()
        self.assertIn('/etc/hibernate-ec-build-h2-packages.txt', text)
        doc = (ROOT / 'docs/hibernate-ec-build-h2.md').read_text()
        self.assertIn('libdw-dev', doc)
        self.assertIn('xps-hibernate-ec-build-h2:ubuntu26.10', doc)


if __name__ == '__main__':
    unittest.main()
