"""Unprivileged Unix socketpair tests; no real listener or privileged effect."""
import json
import os
import pathlib
import socket
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import xps_authz_ipc as ipc


class FrameTests(unittest.TestCase):
    def test_only_catalog(self):
        for action in ipc.Request:
            self.assertIs(ipc.parse_request(action.value.encode() + b"\n"), action)

    def test_reject_invalid_frames(self):
        for frame in (
            b"", b"audit", b"audit\r\n", b"AUDIT\n", b"audit\n\n", b"audit\x00\n",
            b"grant\n", b"revoke\n", b"recover\n", b"worker\n", b"status\nx",
            b"audit\nthermal\n", b"/bin/sh\n", b"\xff\n", bytearray(b"audit\n"),
        ):
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                ipc.parse_request(frame)

    def test_reply_validated(self):
        encoded = ipc.Reply(ipc.Result.ACCEPTED, operation_id="a" * 32,
                            lease_remaining_s=1200, audit_remaining=4).encode()
        self.assertLessEqual(len(encoded), ipc.MAX_REPLY)
        self.assertEqual(json.loads(encoded)["remaining"]["audit"], 4)
        class Alias(str):
            pass
        for bad in (
            ipc.Reply(ipc.Result.ACCEPTED),
            ipc.Reply(ipc.Result.STATUS, operation_id="arbitrary"),
            ipc.Reply(ipc.Result.STATUS, audit_remaining=6),
            ipc.Reply(ipc.Result.STATUS, iris_remaining=True),
            ipc.Reply(ipc.Result.STATUS, lease_remaining_s=-1),
            ipc.Reply(ipc.Result.STATUS, recovery_pending=1),
            ipc.Reply("arbitrary"),
            ipc.Reply(ipc.Result.ACCEPTED, reason=ipc.Reason.NO_LEASE, operation_id="a"*32),
            ipc.Reply(ipc.Result.ERROR),
            ipc.Reply(ipc.Result.STATUS, operation_id="a"*32, operation_outcome="pass"),
            ipc.Reply(ipc.Result.STATUS, operation_id="a"*32, operation_phase="commit", operation_outcome="pass"),
            ipc.Reply(ipc.Result.STATUS, operation_id="a"*32, operation_phase="result"),
            ipc.Reply(ipc.Result.STATUS, operation_id="a"*32, operation_phase=Alias("admit")),
            ipc.Reply(ipc.Result.STATUS, operation_id="a"*32, operation_phase="result", operation_outcome=Alias("pass")),

            ipc.Reply(ipc.Result.STATUS, operation_phase="grant"),
            ipc.Reply(ipc.Result.STATUS, operation_outcome="pass"),
            ipc.Reply(ipc.Result.STATUS, operation_id="a"*32, operation_outcome="secret"),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bad.encode()


@unittest.skipUnless(hasattr(socket, "SO_PEERCRED") and os.getuid() > 0 and os.getgid() > 0,
                     "requires non-root Linux socket credentials")
class PeerTests(unittest.TestCase):
    def request(self, frame, *, expected_uid=None, expected_gid=None, dispatch=None,
                end=True, timeout=2.0, status_provider=None):
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        calls, replies = [], []

        def record(req, peer):
            calls.append((req, peer))
            if dispatch:
                return dispatch(req, peer)
            return ipc.Reply(
                ipc.Result.STATUS if req is ipc.Request.STATUS else ipc.Result.ACCEPTED,
                operation_id=None if req is ipc.Request.STATUS else "1" * 32
            )

        def server():
            replies.append(ipc.handle_connection(
                a,
                os.getuid() if expected_uid is None else expected_uid,
                os.getgid() if expected_gid is None else expected_gid,
                record, status_provider=status_provider,
            ))

        with patch.object(ipc, "READ_TIMEOUT_S", timeout), b:
            b.settimeout(4.0)
            # Send before start so test does not race denied peers' close.
            b.sendall(frame)
            if end:
                b.shutdown(socket.SHUT_WR)
            t = threading.Thread(target=server)
            t.start()
            chunks = []
            try:
                while True:
                    try:
                        part = b.recv(1024)
                    except ConnectionResetError:
                        break
                    if not part:
                        break
                    chunks.append(part)
            finally:
                t.join(5.0)
                self.assertFalse(t.is_alive())
        self.assertEqual(len(replies), 1)
        raw = b"".join(chunks)
        # Unread bytes on a rejected peer may reset stream after send; no
        # response-delivery guarantee, but the handler verdict is authoritative.
        if raw:
            self.assertEqual(json.loads(raw)["result"], replies[0].result.value)
        return replies[0], calls

    def test_actual_peer_identity_and_single_dispatch(self):
        reply, calls = self.request(b"audit\n")
        self.assertIs(reply.result, ipc.Result.ACCEPTED)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], ipc.Peer(os.getpid(), os.getuid(), os.getgid()))

    def test_wrong_uid_gid_root_rejected_before_dispatch(self):
        for kw in ({"expected_uid": os.getuid() + 1}, {"expected_gid": os.getgid() + 1},
                   {"expected_uid": 0}, {"expected_gid": 0}):
            with self.subTest(kw=kw):
                reply, calls = self.request(b"audit\n", **kw)
                self.assertIs(reply.reason, ipc.Reason.PEER_DENIED)
                self.assertFalse(calls)

    def test_multiple_frames_and_owner_actions_denied(self):
        for frame in (b"audit\nthermal\n", b"grant\n", b"revoke\n", b"audit\nx"):
            with self.subTest(frame=frame):
                reply, calls = self.request(frame)
                self.assertIs(reply.reason, ipc.Reason.INVALID_FRAME)
                self.assertFalse(calls)

    def test_requires_eof_and_deadline(self):
        reply, calls = self.request(b"audit\n", end=False, timeout=0.04)
        self.assertIs(reply.reason, ipc.Reason.TIMEOUT)
        self.assertFalse(calls)

    def test_dispatch_exception_sanitized_no_retry(self):
        def fail(*unused):
            raise RuntimeError("sensitive-test-value")
        with self.assertLogs(ipc.LOG, "ERROR") as log:
            reply, calls = self.request(b"thermal\n", dispatch=fail)
        self.assertEqual(len(calls), 1)
        self.assertIs(reply.reason, ipc.Reason.DISPATCH_FAILED)
        self.assertNotIn("sensitive-test-value", " ".join(log.output))
        self.assertNotIn(b"sensitive-test-value", reply.encode())

    def test_status_cannot_admit(self):
        with self.assertLogs(ipc.LOG, "ERROR"):
            reply, calls = self.request(b"status\n", status_provider=lambda *_: ipc.Reply(
                ipc.Result.ACCEPTED, operation_id="a" * 32))
        self.assertIs(reply.result, ipc.Result.ERROR)
        self.assertEqual(len(calls), 0)

    def test_status_separate_readonly_provider(self):
        seen = []
        def status(peer):
            seen.append(peer)
            return ipc.Reply(ipc.Result.STATUS, operation_id="a" * 32,
                             operation_phase="result", operation_outcome="pass")
        reply, calls = self.request(b"status\n", status_provider=status)
        self.assertIs(reply.result, ipc.Result.STATUS)
        self.assertEqual(json.loads(reply.encode())["operation_outcome"], "pass")
        self.assertEqual(len(seen), 1)
        self.assertFalse(calls)

    def test_status_missing_provider_never_dispatches(self):
        with self.assertLogs(ipc.LOG, "ERROR"):
            reply, calls = self.request(b"status\n")
        self.assertIs(reply.result, ipc.Result.ERROR)
        self.assertFalse(calls)

    def test_bad_response_does_not_retry(self):
        with self.assertLogs(ipc.LOG, "ERROR"):
            reply, calls = self.request(b"audit\n", dispatch=lambda *_: "secret")
        self.assertIs(reply.result, ipc.Result.ERROR)
        self.assertEqual(len(calls), 1)

    def test_inconsistent_dispatch_reply_no_retry(self):
        with self.assertLogs(ipc.LOG, "ERROR"):
            reply, calls = self.request(b"audit\n", dispatch=lambda *_: ipc.Reply(
                ipc.Result.ACCEPTED, reason=ipc.Reason.NO_LEASE, operation_id="a"*32))
        self.assertIs(reply.result, ipc.Result.ERROR)
        self.assertEqual(len(calls), 1)

    def test_disconnected_client_no_replay(self):
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        calls = []
        b.sendall(b"audit\n")
        b.shutdown(socket.SHUT_WR)
        b.close()
        def dispatch(req, peer):
            calls.append(req)
            return ipc.Reply(ipc.Result.ACCEPTED, operation_id="b" * 32)
        with self.assertLogs(ipc.LOG, "WARNING"):
            reply = ipc.handle_connection(a, os.getuid(), os.getgid(), dispatch)
        self.assertIs(reply.result, ipc.Result.ACCEPTED)
        self.assertEqual(calls, [ipc.Request.AUDIT])


if __name__ == "__main__":
    unittest.main()
