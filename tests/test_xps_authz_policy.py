"""Unit tests for the AUTHZ v1.1 policy engine (temp dirs only, no hardware)."""
import dataclasses
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "xps_authz_policy.py"
spec = importlib.util.spec_from_file_location("xps_authz_policy", SCRIPT)
P = importlib.util.module_from_spec(spec)
sys.modules["xps_authz_policy"] = P
spec.loader.exec_module(P)

OWNER, AGENT, RECOVERY = 1000, 2000, 3000
KERNEL = "6.17.0-test"
SRCV = "ABCDEF0123456789ABCDEF0"
INCARNATION = "broker-1"
PIN = P.R0Pin(kernel_release=KERNEL, srcversion=SRCV)
AUDIT_EV = {"report_sha256": "c" * 64, "report_bytes": 4096, "findings": 3}


class Env:
    def __init__(self):
        self.now = 100.0
        self.boot = "boot-1"
        self.kernel = KERNEL
        self.caller = AGENT
        self.tick = None


class FailingFs(P.FsOps):
    def __init__(self, where):
        self.where = where

    def write(self, fd, data):
        if self.where == "write":
            raise OSError(28, "No space left on device")
        super().write(fd, data)

    def fsync(self, fd):
        if self.where == "fsync":
            raise OSError(5, "I/O error")
        super().fsync(fd)

    def unlink(self, name, dir_fd):
        if self.where == "unlink":
            raise OSError(5, "I/O error")
        super().unlink(name, dir_fd)

    def replace(self, src, dst, dir_fd):
        if self.where == "all":
            raise OSError(5, "I/O error")
        super().replace(src, dst, dir_fd)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "authz")
        os.mkdir(self.dir, 0o700)
        self.env = Env()
        self.e = self.engine()
        self.owner = P.OwnerControl(self.e)
        self.as_(OWNER)
        self.owner.initialize()
        self.as_(AGENT)

    def engine(self, fs=None, pin=PIN, incarnation=INCARNATION, caller_uid=None):
        env = self.env

        def clock():
            if env.tick:
                env.now = env.tick(env.now)
            return env.now
        return P.PolicyEngine(
            self.dir, expected_uid=os.geteuid(),
            identities=P.Identities(owner=OWNER, agent=AGENT, recovery=RECOVERY),
            caller_uid=caller_uid or (lambda: env.caller), r0_pin=pin, clock=clock,
            boot_id=lambda: env.boot, kernel_release=lambda: env.kernel, fs=fs, incarnation=incarnation)

    def as_(self, uid):
        self.env.caller = uid

    def grant(self):
        self.as_(OWNER)
        g = self.owner.grant()
        self.as_(AGENT)
        return g

    def run_action(self, action, result="pass"):
        t = self.e.admit({"action": action})
        with self.e.commit(t) as op:
            self.assertEqual(op.action, action)
        if action != "iris-r0":
            ev = AUDIT_EV if (action == "audit" and result == "pass") else None
            self.e.finish(t, result, ev)
        return t

    def evidence(self, op_id, **kw):
        ev = {"op_id": op_id, "boot_id": self.env.boot, "kernel_release": KERNEL,
              "module_sha256": P.STOCK_IRIS_SHA256, "module_srcversion": SRCV,
              "stock_module_verified": True, "devices_present": True,
              "cpu_smoke_frames": 120, "cpu_smoke_pass": True,
              "iris_smoke_frames": 120, "iris_smoke_pass": True}
        ev.update(kw)
        return ev

    def path(self, name=P.STATE_FILE):
        return os.path.join(self.dir, name)

    def state(self):
        with open(self.path(), "rb") as fh:
            return json.load(fh)["state"]

    def write_state(self, st):
        with open(self.path(), "wb") as fh:
            fh.write(P._canon({"sha256": hashlib.sha256(P._canon(st)).hexdigest(), "state": st}))

    def enter(self, cm):
        return cm.__enter__()

    def assertDenied(self, reason, fn, *a):
        with self.assertRaises(P.Denied) as cm:
            fn(*a)
        if reason:
            self.assertIn(reason, str(cm.exception))


class PinTests(unittest.TestCase):
    def test_exact_stock_sha_constant(self):
        self.assertEqual(P.STOCK_IRIS_SHA256,
                         "2183021a89244ad917b3afcbe24f2515c5d671033082f783c22ab817e6c6236b")
        self.assertEqual(PIN.module_sha256, P.STOCK_IRIS_SHA256)

    def test_pin_rejects_other_values(self):
        for kw in ({"module_sha256": "0" * 64}, {"srcversion": "abc"}, {"srcversion": "abcdef0123456789abcdef0"},
                   {"kernel_release": ""}, {"kernel_release": "6.1 ; rm"}, {"kernel_release": "../x"}):
            args = {"kernel_release": KERNEL, "srcversion": SRCV}
            args.update(kw)
            with self.assertRaises(ValueError):
                P.R0Pin(**args)


class GrantAndQuotaTests(Base):
    def test_uninitialized_state_fails_closed(self):
        os.unlink(self.path())
        self.assertRaises(P.StateCorrupt, self.e.admit, {"action": "audit"})
        self.as_(OWNER)
        self.assertRaises(P.StateCorrupt, self.owner.grant)

    def test_initialize_refuses_overwrite(self):
        self.as_(OWNER)
        self.assertDenied("already", self.owner.initialize)

    def test_no_grant_denies(self):
        self.assertDenied("no_grant", self.e.admit, {"action": "audit"})

    def test_quota_5_1_1_and_no_refund(self):
        self.grant()
        for _ in range(5):
            self.run_action("audit", "fail")
        self.assertDenied("uses_exhausted", self.e.admit, {"action": "audit"})
        self.run_action("thermal", "aborted")
        self.assertDenied("uses_exhausted", self.e.admit, {"action": "thermal"})
        self.assertEqual(self.state()["grant"]["uses"], {"audit": 0, "iris-r0": 1, "thermal": 0})

    def test_fractional_boottime_grant_rounds_down(self):
        self.env.now = 100.75
        self.grant()
        g = self.state()["grant"]
        self.assertIs(type(g["issued_at"]), int)
        self.assertIs(type(g["expires_at"]), int)
        self.assertEqual((g["issued_at"], g["expires_at"]), (100, 1300))
        self.env.now = 1240.25
        self.assertDenied("insufficient_time", self.e.admit, {"action": "audit"})

    def test_grant_is_1200s_boottime(self):
        self.assertEqual(self.grant()["seconds"], 1200)
        self.env.now += 1200
        self.assertDenied("expired", self.e.admit, {"action": "audit"})

    def test_malformed_requests(self):
        self.grant()
        for bad in [None, "audit", {}, {"action": "shell"}, {"action": "audit", "args": ["-x"]},
                    {"action": ["audit"]}, {"action": {"a": 1}}, {"Action": "audit"}, [("action", "audit")]]:
            self.assertDenied("malformed", self.e.admit, bad)
        self.assertEqual(self.state()["grant"]["uses"]["audit"], 5)

    def test_identity_separation(self):
        self.assertDenied("identity", self.owner.grant)
        self.assertDenied("identity", self.owner.revoke)
        self.as_(OWNER)
        self.assertDenied("identity", self.e.admit, {"action": "audit"})
        self.as_(RECOVERY)
        self.assertDenied("identity", self.e.admit, {"action": "audit"})
        with self.assertRaises(ValueError):
            P.PolicyEngine(self.dir, incarnation=INCARNATION, caller_uid=lambda: 0, identities=P.Identities(owner=0, agent=0, recovery=0))

    def test_one_active_operation(self):
        self.grant()
        self.e.admit({"action": "audit"})
        self.assertDenied("operation_active", self.e.admit, {"action": "audit"})

    def test_insufficient_time_reserve(self):
        self.grant()
        self.env.now += 1200 - 100
        self.assertDenied("insufficient_time", self.e.admit, {"action": "iris-r0"})
        self.e.admit({"action": "audit"})

    def test_invalid_clock(self):
        self.grant()
        self.env.now = float("nan")
        self.assertDenied("clock", self.e.admit, {"action": "audit"})

    def test_r0_pin_required(self):
        self.grant()
        self.assertDenied("r0_pin", self.engine(pin=None).admit, {"action": "iris-r0"})
        self.env.kernel = "other"
        self.assertDenied("r0_pin", self.e.admit, {"action": "iris-r0"})

    def test_grant_blocked_by_ledger_fault(self):
        os.unlink(self.path(P.OK_TOKEN))
        self.as_(OWNER)
        self.assertDenied("ledger_fault", self.owner.grant)


class TicketTests(Base):
    def test_tampered_ticket_fields_rejected(self):
        self.grant()
        t = self.e.admit({"action": "audit"})
        for forged in (dataclasses.replace(t, action="iris-r0"),
                       dataclasses.replace(t, grant_id="0" * 32),
                       dataclasses.replace(t, boot_id="boot-x"),
                       dataclasses.replace(t, admitted_at=t.admitted_at + 1),
                       dataclasses.replace(t, admitted_at=int(t.admitted_at)),
                       dataclasses.replace(t, digest="0" * 64)):
            self.assertDenied("ticket", self.enter, self.e.commit(forged))
        self.assertDenied("ticket", self.enter, self.e.commit(dataclasses.asdict(t)))

        class Sub(P.Ticket):
            pass
        self.assertDenied("ticket", self.enter, self.e.commit(Sub(**dataclasses.asdict(t))))
        object.__setattr__(t, "action", "iris-r0")  # in-place mutation keeping digest
        self.assertDenied("ticket", self.enter, self.e.commit(t))
        self.assertEqual(self.state()["active"]["phase"], "admitted")

    def test_commit_yields_readonly_view(self):
        self.grant()
        t = self.e.admit({"action": "audit"})
        with self.e.commit(t) as op:
            self.assertIsInstance(op, P.CommittedOp)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                op.action = "iris-r0"

    def test_no_replay_of_committed_ticket(self):
        self.grant()
        t = self.e.admit({"action": "audit"})
        with self.e.commit(t):
            pass
        self.assertDenied("no replay", self.enter, self.e.commit(t))
        self.e.finish(t, "pass", AUDIT_EV)
        self.assertDenied("ticket", self.enter, self.e.commit(t))
        self.assertDenied("ticket", self.e.finish, t, "pass", AUDIT_EV)

    def test_malformed_result(self):
        self.grant()
        t = self.e.admit({"action": "audit"})
        for bad in ("PASS", None, 1, ["pass"]):
            self.assertDenied("malformed", self.e.finish, t, bad)

    def test_pass_only_for_committed(self):
        self.grant()
        t = self.e.admit({"action": "thermal"})
        self.assertDenied("pass only", self.e.finish, t, "pass")
        self.e.finish(t, "aborted")  # uncommitted can be closed as aborted; no refund
        self.assertEqual(self.state()["grant"]["uses"]["thermal"], 0)


class AuditEvidenceTests(Base):
    def test_audit_pass_requires_bounded_evidence(self):
        self.grant()
        t = self.e.admit({"action": "audit"})
        with self.e.commit(t):
            pass
        bads = [None, {}, dict(AUDIT_EV, extra="x"), dict(AUDIT_EV, report_sha256="C" * 64),
                dict(AUDIT_EV, report_bytes=0), dict(AUDIT_EV, report_bytes=P.AUDIT_MAX_BYTES + 1),
                dict(AUDIT_EV, findings=-1), dict(AUDIT_EV, findings=True), dict(AUDIT_EV, report_bytes=1.0)]
        for bad in bads:
            self.assertRaises(P.Denied, self.e.finish, t, "pass", bad)
        self.e.finish(t, "pass", AUDIT_EV)
        rec = self.state()["receipts"][-1]
        self.assertEqual((rec["report_sha256"], rec["report_bytes"], rec["findings"]), ("c" * 64, 4096, 3))

    def test_evidence_rejected_for_other_results(self):
        self.grant()
        t = self.e.admit({"action": "thermal"})
        with self.e.commit(t):
            pass
        self.assertDenied("only accepted", self.e.finish, t, "pass", AUDIT_EV)
        self.e.finish(t, "pass")


class PhaseTests(Base):
    def test_expiry_between_admit_and_commit_no_refund(self):
        self.grant()
        self.env.now += 1200 - 61
        t = self.e.admit({"action": "audit"})
        self.env.now += 5
        launched = []
        with self.assertRaises(P.Denied):
            with self.e.commit(t):
                launched.append(1)
        self.assertEqual(launched, [])
        self.assertIsNone(self.state()["active"])
        self.assertEqual(self.state()["grant"]["uses"]["audit"], 4)

    def _jump_after_commit_write(self):
        reads = []

        def tick(now):
            reads.append(now)
            return now + (5 if len(reads) >= 3 else 0)  # 3rd read = post-fsync recheck
        self.env.tick = tick

    def test_expiry_during_commit_fsync_blocks_launch(self):
        self.grant()
        self.env.now += 1200 - 61
        t = self.e.admit({"action": "audit"})
        self._jump_after_commit_write()
        launched = []
        with self.assertRaises(P.Denied) as cm:
            with self.e.commit(t):
                launched.append(1)
        self.env.tick = None
        self.assertIn("after commit", str(cm.exception))
        self.assertEqual(launched, [])
        st = self.state()
        self.assertIsNone(st["active"])
        self.assertEqual(st["grant"]["uses"]["audit"], 4)
        self.assertTrue(st["receipts"][-1]["outcome"].startswith("not_launched_after_commit"))

    def test_r0_expiry_after_commit_keeps_marker_final_fail(self):
        self.grant()
        self.env.now += 1200 - 301
        t = self.e.admit({"action": "iris-r0"})
        self._jump_after_commit_write()
        with self.assertRaises(P.Denied):
            with self.e.commit(t):
                self.fail("unload must not start")
        self.env.tick = None
        self.assertEqual(self.state()["r0_marker"]["op_id"], t.op_id)
        self.assertDenied("r0_recovery_pending", self.e.admit, {"action": "audit"})
        self.as_(RECOVERY)
        self.assertEqual(self.e.clear_recovery(self.evidence(t.op_id), "pass"), "fail")
        self.assertIsNone(self.state()["r0_marker"])

    def test_revoke_between_admit_and_commit(self):
        self.grant()
        t = self.e.admit({"action": "thermal"})
        self.as_(OWNER)
        self.assertTrue(self.owner.revoke()["revoked"])
        self.as_(AGENT)
        self.assertDenied("revoked", self.enter, self.e.commit(t))
        self.assertDenied("revoked", self.e.admit, {"action": "audit"})

    def test_commit_window_elapsed(self):
        self.grant()
        t = self.e.admit({"action": "audit"})
        self.env.now += P.COMMIT_WINDOW + 1
        self.assertDenied("commit_window", self.enter, self.e.commit(t))

    def test_stale_boot(self):
        self.grant()
        t = self.e.admit({"action": "audit"})
        self.env.boot = "boot-2"
        self.assertDenied("stale_boot", self.enter, self.e.commit(t))
        self.assertDenied("stale_boot", self.e.admit, {"action": "audit"})

    def test_same_broker_engine_keeps_consumption(self):
        self.grant()
        self.run_action("audit")
        t = self.e.admit({"action": "audit"})
        e2 = self.engine()
        self.assertEqual(self.state()["grant"]["uses"]["audit"], 3)
        self.assertDenied("operation_active", e2.admit, {"action": "audit"})
        with e2.commit(t):
            pass
        e2.finish(t, "pass", AUDIT_EV)
        s = self.engine().status()
        self.assertEqual(s["ledger_seq"], self.state()["seq"])
        self.assertEqual(s["last_operation"],
                         {"seq": s["ledger_seq"], "op_id": t.op_id, "action": "audit", "event": "result",
                          "phase": "finished", "outcome": "pass"})

    def test_restart_rejects_healthy_grant(self):
        self.grant()
        self.run_action("audit")
        restarted = self.engine(incarnation="broker-2")
        self.assertDenied("stale_incarnation", restarted.admit, {"action": "audit"})
        self.assertEqual(self.state()["grant"]["uses"]["audit"], 4)
        code = """
import os
import sys
from test_xps_authz_policy import AGENT, OWNER, RECOVERY, P

engine = P.PolicyEngine(
    sys.argv[1], expected_uid=os.geteuid(), identities=P.Identities(OWNER, AGENT, RECOVERY),
    caller_uid=lambda: AGENT, clock=lambda: 100.0, boot_id=lambda: "boot-1",
    incarnation="broker-2",
)
try:
    engine.admit({"action": "audit"})
except P.Denied as exc:
    if str(exc) == "stale_incarnation":
        sys.exit(0)
    raise
sys.exit("previous broker grant was accepted")
"""
        result = subprocess.run([sys.executable, "-B", "-c", code, self.dir],
                                cwd=Path(__file__).parent, capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_launch_revalidates_reserve_after_preflight(self):
        self.grant()
        self.env.now += 1200 - 61
        ticket = self.e.admit({"action": "audit"})
        with self.e.commit(ticket) as op:
            self.assertIs(op.check_launch(), True)
            self.env.now += 2
            self.assertDenied("insufficient_time", op.check_launch)
        self.assertDenied("commit scope", op.check_launch)

    def test_check_launch_rechecks_ticket_and_boot(self):
        self.grant()
        ticket = self.e.admit({"action": "audit"})
        with self.e.commit(ticket) as op:
            self.env.boot = "boot-2"
            self.assertDenied("stale_boot", op.check_launch)
            self.env.boot = "boot-1"
            st = self.state()
            st["active"] = None
            self.write_state(st)
            self.assertDenied("committed operation", op.check_launch)

    def test_abandoned_admission_closed_without_refund(self):
        self.grant()
        self.e.admit({"action": "audit"})
        self.env.now += P.COMMIT_WINDOW + 1
        self.e.admit({"action": "audit"})
        st = self.state()
        self.assertEqual(st["grant"]["uses"]["audit"], 3)
        self.assertIn("abandoned_uncommitted", [r.get("outcome") for r in st["receipts"]])

    def test_committed_unknown_result_not_reaped(self):
        self.grant()
        t = self.e.admit({"action": "thermal"})
        with self.e.commit(t):
            pass  # executor "crashes": no finish()
        self.env.now += 10000
        self.assertDenied("operation_active", self.e.admit, {"action": "audit"})
        self.env.boot = "boot-2"
        self.assertDenied("owner_reconciliation_required", self.e.admit, {"action": "audit"})
        self.assertEqual(self.e.status()["reason"], "owner_reconciliation_required")
        self.as_(OWNER)
        self.assertDenied("operation_active", self.owner.grant)
        self.owner.close_unknown_operation(t.op_id, "verified_ended")
        self.owner.grant()
        self.assertEqual(self.state()["grant"]["uses"]["thermal"], 1)  # new grant, not refund

    def test_status_active_denied_and_sanitized(self):
        self.grant()
        self.assertEqual(self.e.status()["new_actions"], "allowed")
        t = self.e.admit({"action": "audit"})
        s = self.e.status()
        self.assertEqual((s["new_actions"], s["reason"]), ("denied", "operation_active"))
        self.assertEqual(s["active"], {"op_id": t.op_id, "action": "audit", "phase": "admitted"})
        self.assertEqual(s["last_operation"]["phase"], "admitted")
        blob = json.dumps(s)
        for leak in (self.dir, t.grant_id, "boot-1", "receipts", str(AGENT)):
            self.assertNotIn(leak, blob)


class LeaseValidTests(Base):
    def committed(self, action="thermal"):
        self.grant()
        t = self.e.admit({"action": action})
        with self.e.commit(t):
            pass
        return t

    def test_valid_only_for_committed_matching_ticket(self):
        self.grant()
        t = self.e.admit({"action": "thermal"})
        self.assertFalse(self.e.lease_valid(t))
        with self.e.commit(t):
            pass
        self.assertTrue(self.e.lease_valid(t))
        self.assertFalse(self.e.lease_valid(dataclasses.replace(t, action="audit")))
        self.assertFalse(self.e.lease_valid("not a ticket"))

    def test_revoke_stops(self):
        t = self.committed()
        self.as_(OWNER)
        self.owner.revoke()
        self.assertFalse(self.e.lease_valid(t))

    def test_expiry_and_boot(self):
        t = self.committed()
        self.env.now += 1200
        self.assertFalse(self.e.lease_valid(t))
        self.env.now -= 1200
        self.env.boot = "boot-2"
        self.assertFalse(self.e.lease_valid(t))

    def test_ledger_fault_stops_thermal(self):
        t = self.committed()
        os.unlink(self.path(P.OK_TOKEN))
        self.assertFalse(self.e.lease_valid(t))

    def test_unreadable_state_stops_thermal(self):
        t = self.committed()
        with open(self.path(), "wb") as fh:
            fh.write(b"\x00garbage")
        self.assertFalse(self.e.lease_valid(t))
        os.chmod(self.dir, 0o755)
        self.assertFalse(self.e.lease_valid(t))
        os.chmod(self.dir, 0o700)


class ConcurrencyTests(Base):
    def test_concurrent_admit_single_winner(self):
        self.grant()
        results, barrier = [], threading.Barrier(8)

        def worker():
            e = self.engine()
            barrier.wait()
            try:
                results.append(e.admit({"action": "audit"}))
            except P.Denied:
                results.append(None)
        ts = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.state()["grant"]["uses"]["audit"], 4)

    def test_revoke_ack_never_precedes_launch(self):
        self.grant()
        t = self.e.admit({"action": "thermal"})
        events, entered = [], threading.Event()
        owner_engine = P.PolicyEngine(
            self.dir, expected_uid=os.geteuid(), identities=P.Identities(OWNER, AGENT, RECOVERY),
            incarnation=INCARNATION, caller_uid=lambda: OWNER, clock=lambda: self.env.now, boot_id=lambda: self.env.boot)

        def revoker():
            entered.wait()
            P.OwnerControl(owner_engine).revoke()
            events.append("revoke_ack")
        th = threading.Thread(target=revoker)
        th.start()
        with self.e.commit(t):
            entered.set()
            time.sleep(0.2)
            events.append("launch")
        th.join()
        self.assertEqual(events, ["launch", "revoke_ack"])
        self.assertFalse(self.e.lease_valid(t))  # thermal must stop
        self.e.finish(t, "aborted")
        self.assertDenied("revoked", self.e.admit, {"action": "audit"})

    def test_revoke_first_prevents_launch(self):
        self.grant()
        t = self.e.admit({"action": "thermal"})
        self.as_(OWNER)
        self.owner.revoke()
        self.as_(AGENT)
        launched = []
        with self.assertRaises(P.Denied):
            with self.e.commit(t):
                launched.append(1)
        self.assertEqual(launched, [])


class LedgerFailureTests(Base):
    def _fail(self, where):
        self.grant()
        bad = self.engine(FailingFs(where))
        before = self.state()
        with self.assertRaises(P.LedgerWriteError):
            bad.admit({"action": "audit"})
        self.assertEqual(self.state(), before)
        self.assertDenied("ledger_fault", bad.admit, {"action": "audit"})
        self.assertDenied("ledger_fault", self.engine().admit, {"action": "audit"})  # restart
        self.assertEqual(self.engine().status()["reason"], "ledger_fault")
        self.as_(OWNER)
        self.assertDenied("ledger_fault", self.owner.grant)
        self.owner.clear_ledger_fault()
        self.as_(AGENT)
        self.e.admit({"action": "audit"})

    def test_enospc_fail_closed_persistent(self):
        self._fail("write")

    def test_fsync_failure_fail_closed_persistent(self):
        self._fail("fsync")

    def test_failed_revoke_unlink_blocks_other_engines_and_restart(self):
        self.grant()
        ticket = self.e.admit({"action": "thermal"})
        before = self.state()
        bad = self.engine(FailingFs("unlink"), caller_uid=lambda: OWNER)
        with self.assertRaises(P.LedgerWriteError):
            P.OwnerControl(bad).revoke()
        self.assertEqual(self.state(), before)
        self.assertTrue(os.path.exists(self.path(P.OK_TOKEN)))
        self.as_(AGENT)
        self.assertDenied("ledger_fault", self.enter, self.e.commit(ticket))
        restarted = self.engine(incarnation="broker-2")
        self.assertDenied("stale_incarnation", self.enter, restarted.commit(ticket))
        self.assertDenied("stale_incarnation", restarted.admit, {"action": "audit"})
        self.assertEqual(self.state()["grant"]["uses"]["thermal"], 0)

    def test_retry_revoke_requires_directory_sync_after_visible_replace(self):
        self.grant()
        ticket = self.e.admit({"action": "thermal"})

        class FailedStateSync(P.FsOps):
            state_replaced = False

            def replace(self, src, dst, dir_fd):
                super().replace(src, dst, dir_fd)
                self.state_replaced |= dst == P.STATE_FILE

            def fsync(self, fd):
                if self.state_replaced and stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise OSError(5, "state directory sync failed")
                super().fsync(fd)

        self.as_(OWNER)
        with self.assertRaises(P.LedgerWriteError):
            P.OwnerControl(self.engine(FailedStateSync())).revoke()
        self.assertTrue(self.state()["grant"]["revoked"])
        with self.assertRaises(P.LedgerWriteError):
            P.OwnerControl(self.engine(FailingFs("fsync"))).revoke()
        self.assertTrue(self.owner.revoke()["revoked"])
        self.assertEqual([r["event"] for r in self.state()["receipts"]].count("revoke"), 1)
        self.as_(AGENT)
        self.assertDenied("ledger_fault", self.enter, self.e.commit(ticket))

    def test_commit_write_failure_blocks_launch_no_refund(self):
        self.grant()
        t = self.e.admit({"action": "audit"})
        launched = []
        with self.assertRaises(P.LedgerWriteError):
            with self.engine(FailingFs("fsync")).commit(t):
                launched.append(1)
        self.assertEqual(launched, [])
        self.assertEqual(self.state()["grant"]["uses"]["audit"], 4)

    def test_corruption_fail_closed(self):
        self.grant()
        for payload in (b"{not json", b'{"sha256":"0","state":{}}',
                        b'{"sha256":"0","sha256":"1","state":{}}', b'{"sha256":NaN,"state":{}}',
                        b'{"sha256":"0","state":{"seq":Infinity}}'):
            with open(self.path(), "wb") as fh:
                fh.write(payload)
            self.assertRaises(P.StateCorrupt, self.e.admit, {"action": "audit"})
            self.assertEqual(self.e.status()["new_actions"], "denied")

    def test_semantic_schema_violations(self):
        self.grant()
        good = self.state()
        mutations = [
            lambda s: s["grant"]["uses"].__setitem__("audit", 99),
            lambda s: s["grant"].__setitem__("expires_at", s["grant"]["issued_at"] + 99999),
            lambda s: s["grant"].__setitem__("revoked", 0),
            lambda s: s["grant"].__setitem__("issued_at", True),
            lambda s: s["grant"].update(issued_at=100.25, expires_at=1300.25),
            lambda s: s["grant"].update(issued_at=100.0, expires_at=1300.0),
            lambda s: s.__setitem__("seq", s["seq"] + 5),
            lambda s: s["receipts"].append({"seq": 999, "event": "x"}),
            lambda s: s.__setitem__("active", {"op_id": "0" * 32, "action": "audit", "grant_id": "f" * 32,
                                               "boot_id": "boot-1", "admitted_at": 1, "digest": "x",
                                               "phase": "admitted", "committed_at": None}),
        ]
        for mutate in mutations:
            st = json.loads(json.dumps(good))
            mutate(st)
            self.write_state(st)
            self.assertRaises(P.StateCorrupt, self.e.admit, {"action": "audit"})

    def test_committed_r0_without_marker_is_corrupt(self):
        self.grant()
        t = self.e.admit({"action": "iris-r0"})
        with self.e.commit(t):
            pass
        st = self.state()
        st["r0_marker"] = None
        self.write_state(st)
        self.assertRaises(P.StateCorrupt, self.e.admit, {"action": "audit"})
        self.assertEqual(self.e.pending_recovery()["state"], "unknown")

    def test_unsafe_storage(self):
        os.chmod(self.dir, 0o755)
        self.assertRaises(P.UnsafeStorage, self.e.admit, {"action": "audit"})
        os.chmod(self.dir, 0o700)
        os.chmod(self.path(), 0o644)
        self.assertRaises(P.UnsafeStorage, self.e.admit, {"action": "audit"})
        os.chmod(self.path(), 0o600)
        link = os.path.join(self.tmp.name, "link")
        os.symlink(self.dir, link)
        e = P.PolicyEngine(link, expected_uid=os.geteuid(), incarnation=INCARNATION, caller_uid=lambda: AGENT,
                           identities=P.Identities(OWNER, AGENT, RECOVERY))
        self.assertRaises(P.UnsafeStorage, e.admit, {"action": "audit"})
        e2 = P.PolicyEngine(self.dir, expected_uid=os.geteuid() + 1, incarnation=INCARNATION, caller_uid=lambda: AGENT,
                            identities=P.Identities(OWNER, AGENT, RECOVERY))
        self.assertRaises(P.UnsafeStorage, e2.admit, {"action": "audit"})


class ReceiptCapacityTests(Base):
    def _limits(self, cap, reserve):
        old = P.MAX_RECEIPTS, P.RESERVED_RECEIPTS
        P.MAX_RECEIPTS, P.RESERVED_RECEIPTS = cap, reserve
        self.addCleanup(lambda: (setattr(P, "MAX_RECEIPTS", old[0]), setattr(P, "RESERVED_RECEIPTS", old[1])))

    def test_capacity_denies_new_but_keeps_reserve_and_archives(self):
        self._limits(12, 4)
        self.grant()                            # 1 receipt
        self.run_action("audit")                # 4
        self.run_action("audit")                # 7
        t = self.e.admit({"action": "audit"})   # 8
        with self.e.commit(t):                  # 9: reserved headroom
            pass
        self.e.finish(t, "pass", AUDIT_EV)      # 10
        self.assertDenied("ledger_capacity", self.e.admit, {"action": "audit"})
        self.assertEqual(self.e.status()["reason"], "ledger_capacity")
        self.as_(OWNER)
        self.assertDenied("ledger_capacity", self.owner.grant)
        total = self.state()["receipts"]
        before = self.e.status()
        self.assertEqual(before["last_operation"]["op_id"], t.op_id)
        info = self.owner.archive_receipts()
        with open(self.path(info["file"]), "rb") as fh:
            body = fh.read()
        self.assertEqual(hashlib.sha256(body).hexdigest(), info["sha256"])
        self.assertEqual(json.loads(body)["receipts"], total)  # nothing lost
        self.assertEqual([r["seq"] for r in total], list(range(1, len(total) + 1)))
        arch = self.state()["receipts"][0]
        self.assertEqual((arch["event"], arch["seq"], arch["first_seq"]), ("archived", total[-1]["seq"] + 1, 1))
        after = self.e.status()
        self.assertEqual(after["ledger_seq"], before["ledger_seq"] + 1)  # monotonic, no reset
        self.assertEqual(after["last_operation"], before["last_operation"])  # not lost by archival
        self.as_(AGENT)
        t2 = self.e.admit({"action": "audit"})
        s = self.e.status()
        self.assertEqual((s["ledger_seq"], s["last_operation"]["seq"], s["last_operation"]["op_id"]),
                         (after["ledger_seq"] + 1, after["ledger_seq"] + 1, t2.op_id))

    def test_hard_cap_fault_persists_across_restart(self):
        self._limits(3, 0)
        self.grant()
        t = self.e.admit({"action": "audit"})
        with self.e.commit(t):
            pass
        self.assertRaises(P.LedgerWriteError, self.e.finish, t, "pass", AUDIT_EV)
        self.assertEqual(self.engine().status()["reason"], "ledger_fault")

    def test_archive_refused_while_pending(self):
        self.grant()
        self.e.admit({"action": "audit"})
        self.as_(OWNER)
        self.assertDenied("pending", self.owner.archive_receipts)

    def test_hard_cap_fails_closed_without_truncation(self):
        self._limits(3, 0)
        self.grant()
        t = self.e.admit({"action": "audit"})
        with self.e.commit(t):
            pass
        before = self.state()
        self.assertRaises(P.LedgerWriteError, self.e.finish, t, "pass", AUDIT_EV)
        self.assertEqual(self.state(), before)


class R0RecoveryTests(Base):
    def r0(self):
        self.grant()
        return self.run_action("iris-r0")

    def test_marker_committed_atomically_with_pin(self):
        t = self.r0()
        st = self.state()
        m = st["r0_marker"]
        self.assertEqual((m["op_id"], m["kernel_release"], m["module_sha256"], m["srcversion"]),
                         (t.op_id, KERNEL, P.STOCK_IRIS_SHA256, SRCV))
        self.assertEqual(st["receipts"][-1]["event"], "commit")
        self.assertDenied("r0_recovery_pending", self.e.admit, {"action": "audit"})
        self.assertTrue(self.e.status()["recovery_required"])
        self.assertEqual(self.e.pending_recovery()["state"], "restore_same_boot")

    def test_r0_finish_pass_denied_fail_keeps_marker(self):
        t = self.r0()
        self.assertDenied("pass only", self.e.finish, t, "pass")
        self.e.finish(t, "fail")
        self.assertIsNotNone(self.state()["r0_marker"])
        self.assertDenied("r0_recovery_pending", self.e.admit, {"action": "audit"})
        self.as_(RECOVERY)
        self.assertEqual(self.e.clear_recovery(self.evidence(t.op_id), "pass"), "fail")

    def test_r0_aborted_keeps_marker(self):
        t = self.r0()
        self.e.finish(t, "aborted")
        self.assertIsNotNone(self.state()["r0_marker"])

    def test_clear_requires_trusted_executor_and_exact_evidence(self):
        t = self.r0()
        self.assertDenied("identity", self.e.clear_recovery, self.evidence(t.op_id), "pass")
        self.as_(OWNER)
        self.assertDenied("identity", self.e.clear_recovery, self.evidence(t.op_id), "pass")
        self.as_(RECOVERY)
        bads = [self.evidence(t.op_id, cpu_smoke_frames=119), self.evidence(t.op_id, iris_smoke_frames=121),
                self.evidence(t.op_id, iris_smoke_frames=True), self.evidence(t.op_id, cpu_smoke_frames=120.0),
                self.evidence(t.op_id, cpu_smoke_pass=False), self.evidence(t.op_id, iris_smoke_pass=1),
                self.evidence(t.op_id, stock_module_verified=1), self.evidence(t.op_id, devices_present=False),
                self.evidence("0" * 32), self.evidence(t.op_id, module_sha256="b" * 64),
                self.evidence(t.op_id, module_srcversion="ABCDEF0123456789ABCDEF1"),
                self.evidence(t.op_id, boot_id="boot-0"), self.evidence(t.op_id, kernel_release="other"),
                {"op_id": t.op_id}, dict(self.evidence(t.op_id), extra=1)]
        for bad in bads:
            self.assertRaises(P.Denied, self.e.clear_recovery, bad, "pass")
        self.assertRaises(P.Denied, self.e.clear_recovery, self.evidence(t.op_id), "PASS")
        self.assertIsNotNone(self.state()["r0_marker"])
        self.assertEqual(self.e.clear_recovery(self.evidence(t.op_id), "pass"), "pass")
        st = self.state()
        self.assertIsNone(st["r0_marker"])
        self.assertIsNone(st["active"])
        self.assertEqual((st["receipts"][-1]["event"], st["receipts"][-1]["final"]), ("recovery_cleared", "pass"))
        self.as_(AGENT)
        self.assertDenied("ticket", self.e.finish, t, "fail")  # no finish after clear
        self.assertEqual(self.e.status()["last_operation"]["outcome"], "pass")
        self.run_action("audit")
        self.assertDenied("uses_exhausted", self.e.admit, {"action": "iris-r0"})

    def test_restore_after_failed_unload_is_fail(self):
        t = self.r0()
        self.as_(RECOVERY)
        self.assertEqual(self.e.clear_recovery(self.evidence(t.op_id), "fail"), "fail")

    def test_revoke_and_expiry_do_not_block_recovery(self):
        t = self.r0()
        self.as_(OWNER)
        self.assertTrue(self.owner.revoke()["recovery_pending"])
        self.env.now += 5000
        self.assertEqual(self.e.pending_recovery()["state"], "restore_same_boot")
        self.as_(RECOVERY)
        self.e.clear_recovery(self.evidence(t.op_id), "pass")

    def test_boot_change_requires_owner_reconciliation(self):
        t = self.r0()
        self.env.boot = "boot-2"
        self.assertEqual(self.e.pending_recovery()["state"], "reconcile_required")
        self.assertTrue(self.e.status()["reconciliation_required"])
        self.as_(RECOVERY)
        self.assertDenied("reconciliation", self.e.clear_recovery, self.evidence(t.op_id), "pass")
        self.as_(OWNER)
        self.assertDenied("r0_recovery_pending", self.owner.grant)
        self.assertRaises(P.Denied, self.owner.reconcile_marker, self.evidence(t.op_id, boot_id="boot-1"))
        self.owner.reconcile_marker(self.evidence(t.op_id))
        self.assertEqual(self.state()["receipts"][-1]["final"], "fail")
        self.owner.grant()

    def test_recovery_visible_when_ledger_fails(self):
        t = self.r0()
        bad = self.engine(FailingFs("write"))
        self.assertEqual(bad.pending_recovery()["op_id"], t.op_id)
        self.as_(RECOVERY)
        with self.assertRaises(P.LedgerWriteError):
            bad.clear_recovery(self.evidence(t.op_id), "pass")
        self.assertIsNotNone(self.state()["r0_marker"])
        self.assertEqual(self.engine().pending_recovery()["state"], "restore_same_boot")
        with open(self.path(), "wb") as fh:
            fh.write(b"garbage")
        self.assertEqual(self.e.pending_recovery(), {"state": "unknown", "action": "owner_reconciliation"})

    def test_r0_commit_write_failure_no_marker_no_launch(self):
        self.grant()
        t = self.e.admit({"action": "iris-r0"})
        with self.assertRaises(P.LedgerWriteError):
            with self.engine(FailingFs("fsync")).commit(t):
                self.fail("unload must not start")
        self.assertIsNone(self.state()["r0_marker"])
        self.assertEqual(self.state()["grant"]["uses"]["iris-r0"], 0)


if __name__ == "__main__":
    unittest.main()
