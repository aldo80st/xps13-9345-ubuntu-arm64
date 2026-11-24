"""Socket + status mapping tests with non-privileged fake dispatcher."""
import json
import os
from pathlib import Path
import socket
import sys
import threading
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from xps_authz_broker_lab import LabBroker, _reply_from_status
from xps_authz_ipc import Peer, Request, Result

def snapshot(op=None, phase="result", outcome="pass", action="audit", seq=None):
    seq = (1 if op else 0) if seq is None else seq
    return {"state": "ok", "remaining_seconds": 1000, "ledger_seq": seq,
            "uses_left": {"audit": 4, "iris-r0": 1, "thermal": 1},
            "recovery_required": False,
            "last_operation": None if op is None else {
                "op_id": op, "event": phase, "outcome": outcome, "action": action, "seq": seq,
            }}

class StatusTests(unittest.TestCase):
    def test_terminal_pass_and_unknown(self):
        for v, expected in (("pass", "pass"), ("private reason", "unknown")):
            r = _reply_from_status(snapshot("a"*32, outcome=v))
            self.assertIs(r.result, Result.STATUS)
            self.assertEqual(json.loads(r.encode())["operation_outcome"], expected)
            self.assertNotIn(b"private reason", r.encode())
    def test_unknown_recovery_and_bad_counters_fail_closed(self):
        for field, value in (("recovery_required", "unknown"), ("remaining_seconds", True),
                             ("last_operation", {"op_id": "secret", "event": "result"}),
                             ("uses_left", {}), ("state", "unavailable")):
            s = snapshot(); s[field] = value
            r = _reply_from_status(s)
            self.assertIs(r.result, Result.ERROR)
            self.assertTrue(r.recovery_pending)
    def test_faulted_ledger_cannot_ack_visible_receipt(self):
        status = snapshot("a"*32, seq=3)
        status.update(reason="ledger_fault", new_actions="denied")
        for result in (Result.STATUS, Result.ACCEPTED):
            r = _reply_from_status(status, result=result)
            self.assertIs(r.result, Result.ERROR)
            self.assertTrue(r.recovery_pending)
            self.assertIsNone(r.operation_id)

    def test_expected_receipt_not_found(self):
        r = _reply_from_status(snapshot("a"*32), result=Result.ACCEPTED, expected_op="b"*32)
        self.assertIs(r.result, Result.ERROR)
    def test_missing_last_operation_is_not_null(self):
        s=snapshot(); del s["last_operation"]
        self.assertIs(_reply_from_status(s).result, Result.ERROR)
        self.assertIs(_reply_from_status(snapshot()).result, Result.STATUS)
    def test_stale_or_wrong_action_receipt_cannot_ack(self):
        peer=Peer(1,1001,1001)
        class Alias(str):
            pass
        for kind in ("stale", "wrong_action", "old_seq", "alias_action"):
            with self.subTest(kind=kind):
                calls=[]; state=[snapshot("a"*32,seq=2)]
                def run(req):
                    calls.append(req)
                    if kind=="stale":
                        return types.SimpleNamespace(op_id="a"*32)
                    state[0]=snapshot("b"*32,action="thermal" if kind=="wrong_action" else Alias("audit") if kind=="alias_action" else "audit",
                                      seq=2 if kind=="old_seq" else 3)
                    return types.SimpleNamespace(op_id="b"*32)
                b=LabBroker(1001,1001,lambda:state[0],run)
                self.assertIs(b.dispatch(Request.AUDIT,peer).result, Result.ERROR)
                self.assertEqual(calls,[{"action":"audit"}])
    def test_status_does_not_execute(self):
        calls = []
        b = LabBroker(1001, 1001, lambda: snapshot(), lambda req: calls.append(req))
        self.assertIs(b.status(Peer(1, 1001, 1001)).result, Result.STATUS)
        self.assertIs(b.dispatch(Request.STATUS, Peer(1, 1001, 1001)).result, Result.DENIED)
        self.assertFalse(calls)

@unittest.skipUnless(os.getuid() > 0 and os.getgid() > 0 and hasattr(socket,"SO_PEERCRED"),
                     "non-root Linux socketpair")
class SocketTests(unittest.TestCase):
    def test_one_dispatch_then_receipt_query(self):
        calls, s = [], [snapshot()]
        def run(req):
            calls.append(req); s[0] = snapshot("c"*32)
            return types.SimpleNamespace(op_id="c"*32)
        b = LabBroker(os.getuid(), os.getgid(), lambda: s[0], run)
        def request(frame):
            a,c=socket.socketpair()
            with c:
                c.settimeout(3); c.sendall(frame); c.shutdown(socket.SHUT_WR)
                t=threading.Thread(target=b.handle,args=(a,));t.start()
                data=b""
                while True:
                    chunk=c.recv(1024)
                    if not chunk: break
                    data+=chunk
                t.join(3); self.assertFalse(t.is_alive())
                return json.loads(data)
        r=request(b"audit\n")
        self.assertEqual((r["result"],r["operation_id"],r["operation_outcome"]),
                         ("ACCEPTED","c"*32,"pass"))
        self.assertEqual(request(b"status\n")["operation_id"],"c"*32)
        self.assertEqual(calls,[{"action":"audit"}])
    def test_denied_before_admission(self):
        b=LabBroker(os.getuid(),os.getgid(),lambda:snapshot(),
                    lambda req:types.SimpleNamespace(op_id="-",outcome=types.SimpleNamespace(value="DENIED")))
        self.assertIs(b.dispatch(Request.AUDIT,Peer(os.getpid(),os.getuid(),os.getgid())).result,Result.DENIED)
    def test_wrong_identity(self):
        b=LabBroker(os.getuid(),os.getgid(),lambda:snapshot(),lambda req:self.fail("dispatched"))
        self.assertIs(b.dispatch(Request.AUDIT,Peer(os.getpid(),os.getuid()+1,os.getgid())).result,Result.DENIED)
