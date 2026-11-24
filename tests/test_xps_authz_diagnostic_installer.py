"""Exercise the builder and emitted installer with synthetic data and OS calls."""

from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_xps_authz_diagnostic_installer as builder


class InstallerTests(unittest.TestCase):
    def setUp(self):
        scratch = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(scratch)
        self.manifest = {}
        for source in builder.SOURCES:
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            data = (source + "\n").encode()
            path.write_bytes(data)
            self.manifest[source] = hashlib.sha256(data).hexdigest()

    def render(self):
        return builder.render(self.root, json.dumps(self.manifest))

    def runtime(self):
        artifact = self.render()
        namespace = {"__name__": "synthetic_installer"}
        exec(compile(artifact, "<synthetic installer>", "exec"), namespace)
        return namespace

    def test_reproducible_and_fixed_destinations(self):
        artifact = self.render()
        self.manifest = dict(reversed(tuple(self.manifest.items())))
        self.assertEqual(self.render(), artifact)
        self.assertEqual(tuple(path for path, _, _ in self.runtime()["PAYLOAD"]), (
            "/usr/local/libexec/xps-authz-diagnostic/xps_authz_ipc.py",
            "/usr/local/libexec/xps-authz-diagnostic/xps_authz_diagnostic.py",
            "/etc/systemd/system/xps-authz-diagnostic@.service",
            "/etc/systemd/system/xps-authz-diagnostic.socket",
        ))

    def test_manifest_rejects_missing_extra_duplicate_and_invalid_digest(self):
        source = next(iter(self.manifest))
        cases = [
            json.dumps({}),
            json.dumps(dict(self.manifest, extra="0" * 64)),
            json.dumps(self.manifest)[:-1] + f', "{source}": "duplicate"' + '}',
            json.dumps(dict(self.manifest, **{source: "0" * 63})),
        ]
        for invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                builder.render(self.root, invalid)

    def test_source_mismatch(self):
        (self.root / next(iter(self.manifest))).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.render()

    def test_symlink_source_refused_even_with_matching_bytes(self):
        source = next(iter(self.manifest))
        path = self.root / source
        target = self.root / "substitute"
        path.rename(target)
        path.symlink_to(target)
        with self.assertRaises(OSError):
            self.render()

    def test_host_guard(self):
        runtime = self.runtime()
        uname = Mock(return_value=SimpleNamespace(
            sysname="Linux", machine="aarch64", release="7.3.0-11-generic"))
        model = Mock(return_value=b"Dell XPS 13 9345")
        with patch.dict(runtime, os=SimpleNamespace(uname=uname), host_model=model):
            runtime["check_host"]()
            model.return_value = b"Dell XPS 13 9350"
            with self.assertRaisesRegex(ValueError, "model mismatch"):
                runtime["check_host"]()
            uname.return_value.release = "7.3.0-12-generic"
            with self.assertRaisesRegex(ValueError, "kernel mismatch"):
                runtime["check_host"]()

    def test_unsafe_ancestor_and_nofollow_walk(self):
        runtime = self.runtime()
        fake_os = Mock()
        fake_os.fstat.side_effect = [
            SimpleNamespace(st_uid=0, st_gid=0, st_mode=0o755),
            SimpleNamespace(st_uid=0, st_gid=0, st_mode=0o775),
        ]
        fake_os.open.side_effect = [10, 11]
        with patch.dict(runtime, os=fake_os), self.assertRaisesRegex(ValueError, "ancestor"):
            with runtime["directory"]("/usr/local"):
                self.fail("unsafe ancestor was accepted")
        fake_os.open.assert_called_with("usr", runtime["DIRECTORY"], dir_fd=10)

    def test_embedded_digest_checked_before_account_lookup(self):
        runtime = self.runtime()
        path, _, data = runtime["PAYLOAD"][0]
        account = Mock()
        with patch.dict(runtime, PAYLOAD=((path, "0" * 64, data),),
                        check_host=Mock(), lookup=account):
            with self.assertRaisesRegex(ValueError, "embedded SHA-256 mismatch"):
                runtime["install"]([])
        account.assert_not_called()

    def fixtures(self, runtime):
        owner = SimpleNamespace(pw_name="owner", pw_uid=1000, pw_gid=1000)
        os_calls = Mock()
        os_calls.stat.side_effect = FileNotFoundError
        os_calls.open.return_value = 9
        calls = dict(
            os=os_calls, check_host=Mock(), check_useradd=Mock(),
            pwd=SimpleNamespace(getpwuid=Mock(return_value=owner),
                                getpwnam=Mock(return_value=owner)),
            lookup=Mock(return_value=None), verify_account=Mock(),
            directory=Mock(side_effect=lambda path: nullcontext(path)),
            protected=Mock(), write_exclusive=Mock(),
            subprocess=Mock(TimeoutExpired=runtime["subprocess"].TimeoutExpired),
        )
        calls["subprocess"].run.return_value.returncode = 0
        return calls

    def test_account_socket_and_destination_collisions_precede_mutation(self):
        runtime = self.runtime()
        for index in range(6):
            calls = self.fixtures(runtime)
            if index < 2:
                outcomes = [None, None]
                outcomes[index] = object()
                calls["lookup"].side_effect = outcomes
            else:
                calls["os"].stat.side_effect = [FileNotFoundError] * (index - 2) + [object()]
            with self.subTest(index=index), patch.dict(runtime, calls):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    runtime["install"]([])
                calls["subprocess"].run.assert_not_called()
                calls["os"].mkdir.assert_not_called()

    def test_timeout_reports_observed_account_and_writes_nothing(self):
        runtime = self.runtime()
        calls = self.fixtures(runtime)
        calls["lookup"].side_effect = [None, None, object(), object()]
        calls["subprocess"].run.side_effect = runtime["subprocess"].TimeoutExpired(
            runtime["USERADD"], 30)
        effects = []
        with patch.dict(runtime, calls), self.assertRaisesRegex(ValueError, "useradd failed"):
            runtime["install"](effects)
        self.assertEqual(effects, [
            "useradd timed out after 30 seconds, xps-agent user present=True, group present=True"
        ])
        calls["os"].mkdir.assert_not_called()

    def test_fixed_useradd_and_partial_failure_keeps_prior_effects(self):
        runtime = self.runtime()
        calls = self.fixtures(runtime)
        writer = calls["write_exclusive"]

        def write(fd, name, path, data, effects):
            if name == "xps-authz-diagnostic@.service":
                raise OSError("simulated failure")
            effects.append("wrote " + path)

        writer.side_effect = write
        effects = []
        with patch.dict(runtime, calls), self.assertRaisesRegex(OSError, "simulated failure"):
            runtime["install"](effects)
        args, kwargs = calls["subprocess"].run.call_args
        self.assertEqual(args, ((
            "/usr/sbin/useradd", "--system", "--user-group", "--no-create-home",
            "--home-dir", "/var/lib/xps-agent", "--shell", "/usr/sbin/nologin", "xps-agent",
        ),))
        self.assertEqual(kwargs["cwd"], "/")
        self.assertEqual(kwargs["timeout"], 30)
        self.assertEqual(kwargs["env"], {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
        self.assertEqual(writer.call_count, 3)
        self.assertTrue(effects[-1].endswith("/xps_authz_diagnostic.py"))
        self.assertEqual(calls["os"].fsync.call_count, 3)
        calls["os"].unlink.assert_not_called()

    def test_exclusive_write_refuses_dangling_symlink(self):
        runtime = self.runtime()
        collision = self.root / "diagnostic.py"
        collision.symlink_to(self.root / "absent")
        fd = runtime["os"].open(self.root, runtime["DIRECTORY"])
        effects = []
        try:
            with self.assertRaises(FileExistsError):
                runtime["write_exclusive"](fd, collision.name, str(collision), b"data", effects)
        finally:
            runtime["os"].close(fd)
        self.assertTrue(collision.is_symlink())
        self.assertEqual(effects, [])


if __name__ == "__main__":
    unittest.main()
