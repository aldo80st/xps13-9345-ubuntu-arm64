"""Tests for M3-DIAGNOSTIC non-privileged diagnostic channel and staged units.

Exercises strict SO_PEERCRED via socketpair and an ephemeral user-owned UNIX
listener, NSS/group validation negatives, pinned root-owned IPC provenance and
SHA-256 verification, FD adoption checks, and static unit/AST contracts.
Does NOT install units, create users, or prove live runtime G-ID isolation.
"""
from __future__ import annotations

import ast
from configparser import ConfigParser
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEPLOY_DIR = REPO_ROOT / "deploy" / "xps-authz-diagnostic"
DIAG_SCRIPT = SCRIPTS_DIR / "xps_authz_diagnostic.py"
IPC_SCRIPT = SCRIPTS_DIR / "xps_authz_ipc.py"

sys.path.insert(0, str(SCRIPTS_DIR))
import xps_authz_diagnostic as diag  # noqa: E402
import xps_authz_ipc as ipc  # noqa: E402


def _make_passwd(
    name: str,
    uid: int,
    gid: int,
    home: str = "/nonexistent",
) -> pwd.struct_passwd:
    return pwd.struct_passwd((name, "x", uid, gid, "", home, "/usr/sbin/nologin"))


def _make_group(name: str, gid: int, members: list[str] | None = None):
    return types.SimpleNamespace(
        gr_name=name,
        gr_passwd="x",
        gr_gid=gid,
        gr_mem=list(members or []),
    )


def _send_and_recv(sock: socket.socket, frame: bytes, *, shutdown_wr: bool = True) -> bytes:
    sock.settimeout(4.0)
    sock.sendall(frame)
    if shutdown_wr:
        sock.shutdown(socket.SHUT_WR)
    chunks: list[bytes] = []
    while True:
        try:
            part = sock.recv(1024)
        except ConnectionResetError:
            break
        if not part:
            break
        chunks.append(part)
    return b"".join(chunks)


@unittest.skipUnless(
    hasattr(socket, "SO_PEERCRED") and os.getuid() > 0 and os.getgid() > 0,
    "requires non-root Linux socket credentials",
)
class SocketPairAndListenerTests(unittest.TestCase):
    def _run_socketpair(
        self,
        frame: bytes,
        *,
        expected_uid: int | None = None,
        expected_gid: int | None = None,
        shutdown_wr: bool = True,
        read_timeout: float = 2.0,
    ) -> tuple[ipc.Reply, dict | None]:
        uid = os.getuid() if expected_uid is None else expected_uid
        gid = os.getgid() if expected_gid is None else expected_gid
        handler = diag.DiagnosticHandler(uid, gid)
        server_sock, client_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        replies: list[ipc.Reply] = []

        def serve() -> None:
            replies.append(handler.handle(server_sock))

        with patch.object(ipc, "READ_TIMEOUT_S", read_timeout), client_sock:
            client_sock.settimeout(4.0)
            client_sock.sendall(frame)
            if shutdown_wr:
                client_sock.shutdown(socket.SHUT_WR)
            thread = threading.Thread(target=serve)
            thread.start()
            chunks: list[bytes] = []
            try:
                while True:
                    try:
                        part = client_sock.recv(1024)
                    except ConnectionResetError:
                        break
                    if not part:
                        break
                    chunks.append(part)
            finally:
                thread.join(5.0)
                self.assertFalse(thread.is_alive())

        self.assertEqual(len(replies), 1)
        raw = b"".join(chunks)
        payload = json.loads(raw) if raw else None
        if payload is not None:
            self.assertEqual(payload["result"], replies[0].result.value)
            self.assertEqual(payload["reason"], replies[0].reason.value)
        return replies[0], payload

    def test_status_returns_all_zero_no_grant(self) -> None:
        reply, payload = self._run_socketpair(b"status\n")
        self.assertIs(reply.result, ipc.Result.STATUS)
        self.assertIs(reply.reason, ipc.Reason.NONE)
        self.assertEqual(
            payload,
            {
                "lease_remaining_s": 0,
                "operation_id": None,
                "operation_outcome": None,
                "operation_phase": None,
                "reason": "NONE",
                "recovery_pending": False,
                "remaining": {"audit": 0, "iris-r0": 0, "thermal": 0},
                "result": "STATUS",
            },
        )

    def test_actions_always_denied_even_with_fake_env_or_state(self) -> None:
        fake_env = {
            "XPS_AUTHZ_LEASE": "1200",
            "XPS_AUTHZ_STATE": "/tmp/fake-grant.json",
            "XPS_AUTHZ_GRANT": "1",
        }
        with patch.dict(os.environ, fake_env, clear=False):
            for cmd in (b"audit\n", b"iris-r0\n", b"thermal\n"):
                with self.subTest(cmd=cmd):
                    reply, payload = self._run_socketpair(cmd)
                    self.assertIs(reply.result, ipc.Result.DENIED)
                    self.assertIs(reply.reason, ipc.Reason.NO_LEASE)
                    self.assertIsNone(reply.operation_id)
                    self.assertIsNotNone(payload)
                    self.assertEqual(payload["lease_remaining_s"], 0)
                    self.assertEqual(payload["remaining"], {"audit": 0, "iris-r0": 0, "thermal": 0})
                    self.assertFalse(payload["recovery_pending"])

    def test_peer_mismatch_and_root_rejected_before_reading_frame(self) -> None:
        for kw in (
            {"expected_uid": os.getuid() + 1},
            {"expected_gid": os.getgid() + 1},
        ):
            with self.subTest(kw=kw):
                reply, _ = self._run_socketpair(b"status\n", **kw)
                self.assertIs(reply.result, ipc.Result.DENIED)
                self.assertIs(reply.reason, ipc.Reason.PEER_DENIED)

        for bad_id in (0, -1, 2**32 - 1, "1001"):
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(ValueError):
                    diag.DiagnosticHandler(bad_id, os.getgid())  # type: ignore[arg-type]
                with self.assertRaises(ValueError):
                    diag.DiagnosticHandler(os.getuid(), bad_id)  # type: ignore[arg-type]

    def test_invalid_frames_grant_revoke_and_timeout_denied(self) -> None:
        for frame in (
            b"grant\n",
            b"revoke\n",
            b"recover\n",
            b"AUDIT\n",
            b"audit",
            b"status\nx",
            b"audit\nthermal\n",
            b"/bin/sh\n",
            b"\x00\n",
            b"too-long-frame\n",
        ):
            with self.subTest(frame=frame):
                reply, _ = self._run_socketpair(frame)
                self.assertIs(reply.result, ipc.Result.DENIED)
                self.assertIs(reply.reason, ipc.Reason.INVALID_FRAME)

        reply, _ = self._run_socketpair(b"status\n", shutdown_wr=False, read_timeout=0.04)
        self.assertIs(reply.result, ipc.Result.DENIED)
        self.assertIs(reply.reason, ipc.Reason.TIMEOUT)

    def test_ephemeral_user_owned_unix_listener_and_fd_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sock_path = Path(tmpdir) / "diag-test.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(sock_path))
            os.chmod(sock_path, 0o600)
            listener.listen(4)

            handler = diag.DiagnosticHandler(os.getuid(), os.getgid())
            results: list[ipc.Reply] = []

            def accept_once() -> None:
                conn, _ = listener.accept()
                # Replicate systemd Accept=yes passing an accepted stream FD via dup.
                adopted = diag.adopt_accepted_socket(os.dup(conn.fileno()))
                conn.close()
                results.append(handler.handle(adopted))

            try:
                for cmd, expected_result, expected_reason in (
                    (b"status\n", ipc.Result.STATUS, ipc.Reason.NONE),
                    (b"audit\n", ipc.Result.DENIED, ipc.Reason.NO_LEASE),
                    (b"grant\n", ipc.Result.DENIED, ipc.Reason.INVALID_FRAME),
                ):
                    with self.subTest(cmd=cmd):
                        server_thread = threading.Thread(target=accept_once)
                        server_thread.start()
                        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                            client.connect(str(sock_path))
                            raw = _send_and_recv(client, cmd)
                        server_thread.join(5.0)
                        self.assertFalse(server_thread.is_alive())
                        payload = json.loads(raw)
                        self.assertEqual(payload["result"], expected_result.value)
                        self.assertEqual(payload["reason"], expected_reason.value)
                self.assertEqual(len(results), 3)
            finally:
                listener.close()

    def test_adopt_accepted_socket_rejects_listener_and_non_unix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sock_path = Path(tmpdir) / "listen.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                listener.bind(str(sock_path))
                listener.listen(1)
                with self.assertRaises(ValueError):
                    diag.adopt_accepted_socket(listener.fileno())
            finally:
                listener.close()

        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with self.assertRaises(ValueError):
                diag.adopt_accepted_socket(tcp.fileno())
        finally:
            tcp.close()

        r_fd, w_fd = os.pipe()
        try:
            with self.assertRaises(ValueError):
                diag.adopt_accepted_socket(r_fd)
        finally:
            os.close(r_fd)
            os.close(w_fd)


class IdentityResolutionTests(unittest.TestCase):
    def _mock_nss(
        self,
        *,
        agent_uid: int = 995,
        agent_gid: int = 995,
        agent_home: str = "/nonexistent",
        primary_group_name: str = "xps-agent",
        named_group_gid: int | None = None,
        owner_uid: int | None = 1000,
        owner_gid: int | None = 1000,
        grouplist: list[int] | None = None,
        extra_groups: list[object] | None = None,
    ):
        named_gid = agent_gid if named_group_gid is None else named_group_gid
        agent_pw = _make_passwd("xps-agent", agent_uid, agent_gid, agent_home)
        owner_pw = (
            _make_passwd("amarquez", owner_uid, owner_gid, "/home/amarquez")
            if owner_uid is not None and owner_gid is not None
            else None
        )
        groups_by_gid = {
            agent_gid: _make_group(primary_group_name, agent_gid),
            27: _make_group("sudo", 27),
            999: _make_group("docker", 999),
        }
        all_groups = [groups_by_gid[agent_gid], groups_by_gid[27], groups_by_gid[999]]
        for g in extra_groups or []:
            groups_by_gid[g.gr_gid] = g
            all_groups.append(g)

        def fake_getpwnam(name: str):
            if name == "xps-agent":
                return agent_pw
            if name == "amarquez" and owner_pw is not None:
                return owner_pw
            raise KeyError(name)

        def fake_getgrgid(gid: int):
            if gid in groups_by_gid:
                return groups_by_gid[gid]
            raise KeyError(gid)

        def fake_getgrnam(name: str):
            if name == "xps-agent":
                return _make_group("xps-agent", named_gid)
            raise KeyError(name)

        def fake_getgrouplist(user: str, gid: int):
            self.assertEqual(user, "xps-agent")
            return [agent_gid] if grouplist is None else list(grouplist)

        return (
            patch.object(diag.pwd, "getpwnam", side_effect=fake_getpwnam),
            patch.object(diag.grp, "getgrgid", side_effect=fake_getgrgid),
            patch.object(diag.grp, "getgrnam", side_effect=fake_getgrnam),
            patch.object(diag.grp, "getgrall", return_value=all_groups),
            patch.object(diag.os, "getgrouplist", side_effect=fake_getgrouplist),
        )

    def test_valid_dedicated_identity_resolves(self) -> None:
        patches = self._mock_nss(agent_uid=995, agent_gid=995)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            self.assertEqual(diag.resolve_agent_identity(), (995, 995))

    def test_valid_when_amarquez_absent_from_nss(self) -> None:
        patches = self._mock_nss(agent_uid=995, agent_gid=995, owner_uid=None, owner_gid=None)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            self.assertEqual(diag.resolve_agent_identity(), (995, 995))

    def test_rejects_root_uid1000_and_nss_resolved_amarquez(self) -> None:
        cases = [
            {"agent_uid": 0, "agent_gid": 995},
            {"agent_uid": 995, "agent_gid": 0},
            {"agent_uid": 1000, "agent_gid": 995},
            {"agent_uid": 995, "agent_gid": 1000},
            {"agent_uid": 2001, "agent_gid": 995, "owner_uid": 2001, "owner_gid": 2001},
            {"agent_uid": 995, "agent_gid": 2002, "owner_uid": 2001, "owner_gid": 2002},
            {"agent_home": "/home/xps-agent"},
            {"agent_home": "/root"},
            {"primary_group_name": "sudo"},
            {"primary_group_name": "users"},
            {"named_group_gid": 994},
            {"grouplist": [995, 27]},
            {"grouplist": [995, 999]},
            {"grouplist": [995, 1001], "extra_groups": [_make_group("extra", 1001)]},
            {"extra_groups": [_make_group("docker", 998, ["xps-agent"])]},
            {"extra_groups": [_make_group("lxd", 997, ["xps-agent"])]},
            {"extra_groups": [_make_group("custom-supp", 996, ["xps-agent"])]},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                patches = self._mock_nss(**kwargs)
                with patches[0], patches[1], patches[2], patches[3], patches[4]:
                    with self.assertRaises(PermissionError):
                        diag.resolve_agent_identity()

    def test_from_system_refuses_root_execution(self) -> None:
        with patch.object(diag.os, "geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                diag.DiagnosticHandler.from_system()
        with patch.object(diag.os, "geteuid", return_value=1000), patch.object(
            diag.os, "getuid", return_value=0
        ):
            with self.assertRaises(PermissionError):
                diag.DiagnosticHandler.from_system()


class ProvenanceAndSha256Tests(unittest.TestCase):
    def test_pinned_ipc_sha256_matches_repository_file(self) -> None:
        actual = hashlib.sha256(IPC_SCRIPT.read_bytes()).hexdigest()
        self.assertEqual(diag.PINNED_IPC_SHA256, actual)
        self.assertEqual(
            diag.PINNED_IPC_PATH,
            Path("/usr/local/libexec/xps-authz-diagnostic/xps_authz_ipc.py"),
        )

    def test_rejects_unprivileged_symlink_home_or_writable_ipc_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            local_copy = Path(tmpdir) / "xps_authz_ipc.py"
            local_copy.write_bytes(IPC_SCRIPT.read_bytes())
            os.chmod(local_copy, 0o644)
            with self.assertRaises(PermissionError):
                diag._load_pinned_ipc(local_copy)

            symlink_path = Path(tmpdir) / "link.py"
            symlink_path.symlink_to(local_copy)
            with self.assertRaises(PermissionError):
                diag._load_pinned_ipc(symlink_path)

        with self.assertRaises(PermissionError):
            diag._load_pinned_ipc(Path("scripts/xps_authz_ipc.py"))
        with self.assertRaises(PermissionError):
            diag._load_pinned_ipc(Path("/home/amarquez/xps_authz_ipc.py"))
        with self.assertRaises(PermissionError):
            diag._load_pinned_ipc(IPC_SCRIPT)

    def test_sha256_mismatch_rejected_before_exec(self) -> None:
        tampered = b"raise RuntimeError('should never exec')\n"
        fake_dir_stat = os.stat_result((stat.S_IFDIR | 0o755, 1, 1, 2, 0, 0, 0, 0, 0, 0))
        fake_file_stat = os.stat_result((stat.S_IFREG | 0o644, 2, 1, 1, 0, 0, len(tampered), 0, 0, 0))
        r_fd, w_fd = os.pipe()
        os.write(w_fd, tampered)
        os.close(w_fd)

        def fake_lstat(p):
            return fake_file_stat if Path(p) == diag.PINNED_IPC_PATH else fake_dir_stat

        with (
            patch.object(diag.os, "lstat", side_effect=fake_lstat),
            patch.object(diag.os, "open", return_value=r_fd),
            patch.object(diag.os, "fstat", return_value=fake_file_stat),
        ):
            with self.assertRaises(PermissionError):
                diag._load_pinned_ipc(diag.PINNED_IPC_PATH)

    def test_valid_provenance_and_sha256_loads_module(self) -> None:
        ipc_bytes = IPC_SCRIPT.read_bytes()
        fake_dir_stat = os.stat_result((stat.S_IFDIR | 0o755, 1, 1, 2, 0, 0, 0, 0, 0, 0))
        fake_file_stat = os.stat_result((stat.S_IFREG | 0o644, 2, 1, 1, 0, 0, len(ipc_bytes), 0, 0, 0))
        r_fd, w_fd = os.pipe()
        os.write(w_fd, ipc_bytes)
        os.close(w_fd)

        def fake_lstat(p):
            return fake_file_stat if Path(p) == diag.PINNED_IPC_PATH else fake_dir_stat

        saved_mod = sys.modules.get("xps_authz_ipc")
        try:
            with (
                patch.object(diag.os, "lstat", side_effect=fake_lstat),
                patch.object(diag.os, "open", return_value=r_fd),
                patch.object(diag.os, "fstat", return_value=fake_file_stat),
            ):
                loaded = diag._load_pinned_ipc(diag.PINNED_IPC_PATH)
            self.assertEqual(loaded.__file__, str(diag.PINNED_IPC_PATH))
            self.assertEqual(loaded.MAX_FRAME, ipc.MAX_FRAME)
        finally:
            if saved_mod is not None:
                sys.modules["xps_authz_ipc"] = saved_mod

    def test_cli_rejects_arguments_and_isolated_python_fails_closed(self) -> None:
        for flag in ("--listen", "--uid=1000", "--socket=/tmp/x.sock", "--grant", "status"):
            with self.subTest(flag=flag), patch.object(sys, "stderr", new=io.StringIO()):
                self.assertEqual(diag.main([flag]), 2)

        proc = subprocess.run(
            [sys.executable, "-I", "-B", str(DIAG_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")


class StaticUnitAndAstContractTests(unittest.TestCase):
    def _read_unit(self, filename: str, expected_sections: list[str]) -> ConfigParser:
        parser = ConfigParser(interpolation=None, delimiters=("=",))
        parser.optionxform = str
        with (DEPLOY_DIR / filename).open(encoding="utf-8") as handle:
            parser.read_file(handle)
        self.assertEqual(parser.defaults(), {})
        self.assertEqual(parser.sections(), expected_sections)
        return parser

    def test_socket_unit_contract(self) -> None:
        unit = self._read_unit("xps-authz-diagnostic.socket", ["Unit", "Socket", "Install"])
        sock = unit["Socket"]
        self.assertEqual(sock["ListenStream"], "/run/xps-authz-diagnostic.sock")
        self.assertEqual(sock["Accept"], "yes")
        self.assertEqual(sock["SocketUser"], "root")
        self.assertEqual(sock["SocketGroup"], "xps-agent")
        self.assertEqual(sock["SocketMode"], "0660")
        self.assertEqual(sock["RemoveOnStop"], "yes")
        self.assertLessEqual(int(sock["MaxConnections"]), 32)
        self.assertGreater(int(sock["MaxConnections"]), 0)

    def test_service_unit_contract(self) -> None:
        unit = self._read_unit("xps-authz-diagnostic@.service", ["Unit", "Service"])
        svc = unit["Service"]
        self.assertEqual(
            svc["ExecStart"],
            "/usr/bin/python3 -I -B /usr/local/libexec/xps-authz-diagnostic/xps_authz_diagnostic.py",
        )
        self.assertNotIn("/home", svc["ExecStart"])
        self.assertEqual(svc["StandardInput"], "socket")
        self.assertEqual(svc["DynamicUser"], "yes")
        self.assertEqual(svc["NoNewPrivileges"], "yes")
        self.assertEqual(svc["CapabilityBoundingSet"], "")
        self.assertEqual(svc["AmbientCapabilities"], "")
        self.assertEqual(svc["ProtectSystem"], "strict")
        self.assertEqual(svc["ProtectHome"], "yes")
        self.assertEqual(svc["PrivateNetwork"], "yes")
        self.assertEqual(svc["RestrictAddressFamilies"], "AF_UNIX")
        self.assertRegex(svc["RuntimeMaxSec"], r"^[0-9]+s$")
        self.assertLessEqual(int(svc["RuntimeMaxSec"][:-1]), 10)
        self.assertRegex(svc["TimeoutStopSec"], r"^[0-9]+s$")
        self.assertRegex(svc["MemoryMax"], r"^[0-9]+M$")
        self.assertLessEqual(int(svc["MemoryMax"][:-1]), 128)
        self.assertLessEqual(int(svc["TasksMax"]), 16)

    def test_script_has_no_forbidden_imports_or_listener(self) -> None:
        tree = ast.parse(DIAG_SCRIPT.read_text(encoding="utf-8"))
        imported: set[str] = set()
        called_attrs: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Attribute):
                called_attrs.add(node.attr)

        forbidden_modules = {
            "xps_authz_actions",
            "xps_authz_policy",
            "xps_authz_broker_lab",
            "xps_authz_native_readonly",
            "subprocess",
            "ctypes",
            "shutil",
        }
        self.assertTrue(imported.isdisjoint(forbidden_modules), imported & forbidden_modules)
        self.assertTrue(called_attrs.isdisjoint({"bind", "listen", "accept"}), called_attrs)


if __name__ == "__main__":
    unittest.main()
