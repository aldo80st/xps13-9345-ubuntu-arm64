"""Real filesystem-backed policy + IPC + fake hardware actions.

All state resides in a temporary user-owned directory. No privileged adapters,
native module controls, sockets outside socketpair, thermal load or installation.
"""
import inspect
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import test_xps_authz_actions as fixtures
import test_xps_authz_policy as policy_fixtures
from xps_authz_broker_lab import LabBroker
from xps_authz_ipc import Peer, Request, Result

A=fixtures.m
P=policy_fixtures.P
OWNER, AGENT, RECOVERY = 1000, 2000, 3000

class RealMarkerModule(A.IrisModuleControl):
    def __init__(self,insp,state_file):
        self.insp,self.state_file=insp,state_file
        self.unloads,self.loads=0,0
        self.unload_ok,self.load_ok=True,True
        self.marker_before_effect=False
    def unload_official(self):
        # Commit holds the policy flock. Inspect the already published test
        # file directly, rather than recursively acquiring the same lock.
        marker=json.loads(self.state_file.read_text())["state"]["r0_marker"]
        self.marker_before_effect=(type(marker) is dict and marker.get("module_sha256")==A.IRIS_OFFICIAL_SHA256)
        if not self.marker_before_effect:
            raise AssertionError("no durable recovery marker before unload")
        self.unloads+=1
        if self.unload_ok:self.insp.loaded=False
        return self.unload_ok
    def load_official(self):
        self.loads+=1
        if self.load_ok:self.insp.loaded=True
        return self.load_ok

class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_dir=Path(self.tmp.name)/"state"
        self.state_dir.mkdir(mode=0o700)
        self.clock=fixtures.FakeClock()
        self.clock.t=100.25
        self.incarnation='a'*32
        self.insp=fixtures.FakeInspector()
        self.identities=P.Identities(owner=OWNER,agent=AGENT,recovery=RECOVERY)
        self.pin=P.R0Pin(kernel_release=A.IRIS_KERNEL_RELEASE,srcversion=A.IRIS_OFFICIAL_SRCVERSION)
        self.engine=self.new_engine(AGENT)
        self.owner_engine=self.new_engine(OWNER)
        self.recovery_engine=self.new_engine(RECOVERY)
        self.owner=P.OwnerControl(self.owner_engine)
        self.owner.initialize()
        self.module=RealMarkerModule(self.insp,self.state_dir/P.STATE_FILE)
        self.smoke=fixtures.FakeSmoke()
        self.lock=fixtures.FakeLock()
        self.thermal=fixtures.FakeThermal(self.clock,fixtures.SharedState())
        self.recovery=A.RecoveryManager(self.recovery_engine,self.insp,self.module,
                                        self.smoke,self.clock)
        self.executor=A.ActionExecutor(self.engine,self.insp,self.recovery,self.lock,
                                        self.module,self.thermal,self.clock)
        self.broker=LabBroker(AGENT,AGENT,self.engine.status,self.executor.run)
        self.peer=Peer(os.getpid(),AGENT,AGENT)

    def new_engine(self,uid,fs=None):
        return P.PolicyEngine(str(self.state_dir),expected_uid=os.geteuid(),
                              identities=self.identities,caller_uid=lambda:uid,
                              r0_pin=self.pin,clock=self.clock.monotonic,
                              boot_id=lambda:self.insp.boot,kernel_release=lambda:self.insp.kernel,
                              fs=fs,incarnation=self.incarnation)

    def action(self,request):
        return self.broker.dispatch(request,self.peer)
    def status(self):
        return self.broker.status(self.peer)
    def ledger(self):
        return json.loads((self.state_dir/P.STATE_FILE).read_text())["state"]

    def test_grant_audit_quota_status_and_durable_receipt(self):
        self.assertIs(self.action(Request.AUDIT).result,Result.DENIED)
        self.owner.grant()
        ids=set()
        for i in range(5):
            r=self.action(Request.AUDIT)
            self.assertIs(r.result,Result.ACCEPTED,r)
            self.assertEqual(r.operation_outcome,"pass")
            self.assertEqual(r.audit_remaining,4-i)
            ids.add(r.operation_id)
            self.assertEqual(self.status().operation_id,r.operation_id)
        self.assertEqual(len(ids),5)
        self.assertIs(self.action(Request.AUDIT).result,Result.DENIED)
        receipts=[r for r in self.ledger()["receipts"] if r["event"]=="result" and r.get("action")=="audit"]
        self.assertEqual(len(receipts),5)
        self.assertTrue(all(len(r["report_sha256"])==64 and r["report_bytes"]>0 for r in receipts))

    def test_visible_unsynced_result_never_acks_and_blocks(self):
        class FaultOnResultPublication(P.FsOps):
            def __init__(self):
                self.publications = 0
            def replace(self, src, dst, dir_fd):
                if dst == P.OK_TOKEN:
                    self.publications += 1
                    if self.publications == 3:
                        raise OSError(5, "injected token publication failure")
                super().replace(src, dst, dir_fd)
        self.owner.grant()
        self.engine = self.new_engine(AGENT, fs=FaultOnResultPublication())
        self.executor.engine = self.engine
        self.broker = LabBroker(AGENT, AGENT, self.engine.status, self.executor.run)
        r = self.action(Request.AUDIT)
        self.assertIs(r.result, Result.ERROR, r)
        self.assertIsNone(r.operation_id)
        self.assertTrue(r.recovery_pending)
        self.assertEqual(self.engine.status()["reason"], "ledger_fault")
        self.assertIs(self.status().result, Result.ERROR)
        self.assertIs(self.action(Request.AUDIT).result, Result.ERROR)
        self.assertEqual(self.ledger()["grant"]["uses"]["audit"], 4)

    def test_r0_simulated_marker_and_stock_restore(self):
        self.owner.grant()
        r=self.action(Request.IRIS_R0)
        self.assertIs(r.result,Result.ACCEPTED,r)
        self.assertEqual(r.operation_outcome,"pass")
        self.assertTrue(self.module.marker_before_effect)
        self.assertEqual((self.module.unloads,self.module.loads),(1,1))
        self.assertEqual(self.smoke.frames,[("cpu",120),("iris",120)])
        self.assertIsNone(self.ledger()["r0_marker"])
        self.assertIs(self.action(Request.IRIS_R0).result,Result.DENIED)
        self.assertEqual(self.module.unloads,1)

    def test_failed_unload_is_never_pass_even_with_stock(self):
        self.owner.grant();self.module.unload_ok=False
        r=self.action(Request.IRIS_R0)
        self.assertIs(r.result,Result.ACCEPTED,r)
        self.assertEqual(r.operation_outcome,"fail")
        self.assertEqual(self.module.loads,0)
        self.assertIsNone(self.ledger()["r0_marker"])

    def test_failed_restore_blocks_new_work(self):
        self.owner.grant();self.module.load_ok=False
        r=self.action(Request.IRIS_R0)
        self.assertIs(r.result,Result.ACCEPTED,r)
        self.assertTrue(r.recovery_pending)
        self.assertNotEqual(r.operation_outcome,"pass")
        self.assertIs(self.action(Request.AUDIT).result,Result.DENIED)
        self.assertEqual(self.module.unloads,1)
        self.assertIsNotNone(self.ledger()["r0_marker"])

    def test_thermal_simulated_stop_and_one_use(self):
        self.owner.grant()
        r=self.action(Request.THERMAL)
        self.assertIs(r.result,Result.ACCEPTED,r)
        self.assertEqual(r.operation_outcome,"pass")
        self.assertEqual(self.thermal.starts,[(10.0,0.25,1)])
        self.assertFalse(self.thermal.handle.alive())
        self.assertIs(self.action(Request.THERMAL).result,Result.DENIED)

    def test_thermal_simulated_revoke_mid_run(self):
        self.owner.grant()
        fired=[]
        def revoke(t):
            if t>101 and not fired:
                self.owner.revoke()
                fired.append(t)
        self.clock.on_sleep.append(revoke)
        r=self.action(Request.THERMAL)
        self.assertIs(r.result,Result.ACCEPTED,r)
        self.assertEqual(r.operation_outcome,"aborted")
        self.assertTrue(fired)
        self.assertFalse(self.thermal.handle.alive())
        self.assertIs(self.action(Request.AUDIT).result,Result.DENIED)

    @unittest.skipUnless(os.getuid()>0 and os.getgid()>0 and hasattr(socket,"SO_PEERCRED"),
                         "native non-root socketpair")
    def test_socketpair_end_to_end_durable_policy(self):
        self.owner.grant()
        broker=LabBroker(os.getuid(),os.getgid(),self.engine.status,self.executor.run)
        def request(frame):
            a,b=socket.socketpair()
            with b:
                b.settimeout(4);b.sendall(frame);b.shutdown(socket.SHUT_WR)
                t=threading.Thread(target=broker.handle,args=(a,));t.start()
                raw=b""
                while True:
                    v=b.recv(1024)
                    if not v: break
                    raw+=v
                t.join(4);self.assertFalse(t.is_alive())
                return json.loads(raw)
        r=request(b"audit\n")
        self.assertEqual((r["result"],r["operation_outcome"]),("ACCEPTED","pass"))
        self.assertEqual(request(b"status\n")["operation_id"],r["operation_id"])
        self.assertEqual(self.ledger()["grant"]["uses"]["audit"],4)
