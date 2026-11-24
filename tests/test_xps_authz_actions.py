"""M2-B AUTHZ v1.1 actions/recovery: simulated only, no real effects.

All adapters are in-memory fakes, including a fake of the M2A engine API.
No subprocess, sudo, module, sensor, network or file-system side effects.
"""
import ast
import contextlib
import dataclasses
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "xps_authz_actions.py"
spec = importlib.util.spec_from_file_location("xps_authz_actions", SCRIPT)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

BOOT = "0123456789abcdef0123456789abcdef"
OTHER_BOOT = "fedcba9876543210fedcba9876543210"
_UNSET = object()


def _sensors(val=45.0, *, hot_val=_UNSET):
    """58-sensor XPS non-battery thermal fixture; real M3-M5 adapter enforces
    pinned sensor identity names."""
    vals = [float(val)] * m.SOC_SENSOR_COUNT
    if hot_val is not _UNSET:
        vals[-1] = hot_val
    return vals


@dataclasses.dataclass(frozen=True)
class Ticket:            # M2A-like ticket shape (admission record)
    op_id: str
    action: str
    grant_id: str
    boot_id: str


@dataclasses.dataclass(frozen=True)
class _BareCommittedOp:  # simulates M2A without CommittedOp.check_launch()
    op_id: str
    action: str


@dataclasses.dataclass(frozen=True)
class CommittedOp:       # M2A CommittedOp: op_id/action + check_launch guard
    op_id: str
    action: str
    _check: object = dataclasses.field(repr=False, compare=False)

    def check_launch(self):
        return self._check()


class SharedState:
    """Root-protected state shared by both engine identities (fake)."""

    def __init__(self):
        self.lock_held = False
        self.lease = True
        self.uses = {"audit": 5, "iris-r0": 1, "thermal": 1}
        self.marker = None
        self.boot_changed = False
        self.active = {}
        self.receipts = []
        self.n = 0
        self.fail_commit = False
        self.fail_commit_exit = False
        self.fail_finish = False
        self.fail_clear = False
        self.fail_pending = False
        self.clear_override = None
        self.provide_launch_guard = True
        self.fail_launch_guard = False
        self.launch_guard_override = _UNSET
        self.launch_guard_calls = 0


class FakeEngine(m.PolicyEngine):
    def __init__(self, st, identity):
        self.st, self.identity = st, identity

    def _blocked(self):
        return bool(self.st.active) or self.st.marker is not None

    def admit(self, request):
        assert self.identity == "executor"
        assert set(request) == {"action"}
        st = self.st
        if not st.lease or self._blocked():
            raise m.ActionDenied("engine-deny")
        if st.uses.get(request["action"], 0) <= 0:
            raise m.ActionDenied("exhausted")
        st.uses[request["action"]] -= 1
        st.n += 1
        t = Ticket(f"op-{st.n}", request["action"], "grant-1", BOOT)
        st.receipts.append(("admission", t.op_id))
        return t

    @contextlib.contextmanager
    def commit(self, ticket):
        st = self.st
        assert isinstance(ticket, Ticket)
        assert not st.lock_held, "nested lock"
        if st.fail_commit or not st.lease:
            raise OSError("commit")
        st.lock_held = True
        try:
            st.active[ticket.op_id] = ticket
            if ticket.action == "iris-r0":
                st.marker = {"op_id": ticket.op_id, "grant_id": ticket.grant_id,
                             "boot_id": BOOT, "kernel_release": m.IRIS_KERNEL_RELEASE,
                             "module_sha256": m.IRIS_OFFICIAL_SHA256,
                             "srcversion": m.IRIS_OFFICIAL_SRCVERSION,
                             "committed_at": 1000}
            st.receipts.append(("commit", ticket.op_id))
            def _check_launch():
                assert st.lock_held, "check_launch must run under held commit flock"
                st.launch_guard_calls += 1
                if st.fail_launch_guard:
                    raise OSError("guard")
                if st.launch_guard_override is not _UNSET:
                    return st.launch_guard_override
                return st.lease
            yield (CommittedOp(ticket.op_id, ticket.action, _check_launch)
                   if st.provide_launch_guard
                   else _BareCommittedOp(ticket.op_id, ticket.action))
        finally:
            st.lock_held = False
        if st.fail_commit_exit:
            raise OSError("commit-exit")

    def lease_valid(self, ticket):
        assert isinstance(ticket, Ticket), "lease_valid needs the original Ticket"
        assert not self.st.lock_held, "lease_valid inside commit block"
        assert ticket.op_id in self.st.active, "lease_valid requires committed op"
        return self.st.lease

    def finish(self, ticket, result, audit_evidence=None):
        st = self.st
        assert not st.lock_held
        assert result in ("pass", "fail", "aborted")
        assert ticket.op_id in st.active, "finish without active op (fabricated)"
        if result == "pass" and ticket.action == "audit":
            assert audit_evidence is not None and set(audit_evidence) == set(
                m.AUDIT_EVIDENCE_KEYS)
        else:
            assert audit_evidence is None
        if st.fail_finish:
            raise OSError("fsync")
        del st.active[ticket.op_id]
        st.receipts.append(("result", ticket.op_id, result, audit_evidence))

    def pending_recovery(self):
        st = self.st
        if st.fail_pending:
            raise OSError("EIO")
        if st.marker is None:
            return {"state": "none"}
        if st.boot_changed:
            return dict(st.marker, state="reconcile_required")
        return dict(st.marker, state="restore_same_boot")

    def clear_recovery(self, evidence, unload_result):
        st = self.st
        assert self.identity == "recovery"
        assert tuple(sorted(evidence)) == tuple(sorted(m.RECOVERY_EVIDENCE_KEYS))
        assert unload_result in ("pass", "fail")
        if st.fail_clear:
            raise OSError("ENOSPC")
        assert evidence["op_id"] == st.marker["op_id"]
        assert all(evidence[k] is True for k in (
            "stock_module_verified", "devices_present", "cpu_smoke_pass", "iris_smoke_pass"))
        st.active.pop(evidence["op_id"], None)
        st.marker = None
        final = st.clear_override or unload_result
        st.receipts.append(("recovery", evidence["op_id"], unload_result, final))
        return final


class FakeClock(m.Clock):
    def __init__(self):
        self.t = 0.0
        self.on_sleep = []

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s
        for hook in list(self.on_sleep):
            hook(self.t)


class FakeInspector(m.HostInspector):
    def __init__(self):
        self.boot = BOOT
        self.kernel = m.IRIS_KERNEL_RELEASE
        self.sha = m.IRIS_OFFICIAL_SHA256
        self.loaded = True
        self.srcversion = m.IRIS_OFFICIAL_SRCVERSION
        self.refcnt = 0
        self.holders = []
        self.devices = True
        self.users = m.DeviceUsers(visible=True, pids=[])
        self.power = m.PowerState(external=True, battery_pct=80.0, battery_temp_c=30.0)
        self.soc = _sensors(45.0, hot_val=47.0)
        self.cap = False
        self.raise_on = set()

    def _r(self, name):
        if name in self.raise_on:
            raise OSError(name)

    def boot_id(self):
        self._r("boot"); return self.boot

    def kernel_release(self):
        self._r("kernel"); return self.kernel

    def module_state(self):
        self._r("module_state")
        if not self.loaded:
            return m.ModuleState(False, None, None, [])
        return m.ModuleState(True, self.srcversion, self.refcnt, list(self.holders))

    def official_module_sha256(self):
        self._r("sha"); return self.sha

    def iris_devices_present(self):
        self._r("devices"); return self.devices and self.loaded

    def device_users(self):
        self._r("users"); return self.users

    def power_state(self):
        self._r("power"); return self.power

    def soc_temps_c(self):
        self._r("soc"); return list(self.soc)

    def has_cap_sys_module(self):
        self._r("cap"); return self.cap


class FakeModule(m.IrisModuleControl):
    def __init__(self, inspector, st):
        self.i, self.st = inspector, st
        self.unloads = 0
        self.loads = 0
        self.unload_ok = True
        self.load_ok = True
        self.unload_under_lock = None
        self.after_unload = None

    def unload_official(self):
        self.unloads += 1
        self.unload_under_lock = self.st.lock_held
        assert self.st.marker is not None, "marker must be durable before unload"
        if self.unload_ok:
            self.i.loaded = False
        if self.after_unload:
            self.after_unload()
        return self.unload_ok

    def load_official(self):
        self.loads += 1
        if self.load_ok:
            self.i.loaded = True
        return self.load_ok


class FakeSmoke(m.SmokeRunner):
    def __init__(self):
        self.cpu_ok = True
        self.iris_ok = True
        self.frames = []

    def cpu_decode(self, frames):
        self.frames.append(("cpu", frames)); return self.cpu_ok

    def iris_decode(self, frames):
        self.frames.append(("iris", frames)); return self.iris_ok


class FakeLock(m.RecoveryLock):
    def __init__(self):
        self.held = False
        self.acquisitions = 0

    @contextlib.contextmanager
    def hold(self):
        assert not self.held, "recovery lock contention"
        self.held = True
        self.acquisitions += 1
        try:
            yield
        finally:
            self.held = False


class FakeHandle(m.ThermalHandle):
    def __init__(self, clock):
        self.clock = clock
        self.running = True
        self.stop_calls = 0
        self.stop_delay = 0.0
        self.stop_at = None
        self.wd = 12.0
        self.exit_at = None
        self.alive_raises = False

    def alive(self):
        if self.alive_raises:
            raise OSError("cgroup")
        if self.exit_at is not None and self.clock.t >= self.exit_at:
            self.running = False
        if self.stop_at is not None and self.clock.t >= self.stop_at:
            self.running = False
        return self.running

    def stop(self):
        self.stop_calls += 1
        if self.stop_at is None:
            self.stop_at = self.clock.t + self.stop_delay

    def watchdog_max_s(self):
        return self.wd


class FakeThermal(m.ThermalLauncher):
    def __init__(self, clock, st):
        self.clock, self.st = clock, st
        self.handle = FakeHandle(clock)
        self.starts = []
        self.start_under_lock = None
        self.fail = False
        self.orphans_ok = True
        self.orphan_stops = 0
        self.wd_ready = 12.0
        self.wd_ready_raises = False

    def watchdog_ready(self):
        if self.wd_ready_raises:
            raise OSError("systemd-unit")
        return self.wd_ready

    def start(self, duration_s, duty, workers):
        self.start_under_lock = self.st.lock_held
        self.starts.append((duration_s, duty, workers))
        if self.fail:
            raise OSError("spawn")
        return self.handle

    def stop_orphans(self):
        self.orphan_stops += 1
        return self.orphans_ok


class Harness(unittest.TestCase):
    def setUp(self):
        self.st = SharedState()
        self.engine = FakeEngine(self.st, "executor")
        self.rengine = FakeEngine(self.st, "recovery")
        self.clock = FakeClock()
        self.insp = FakeInspector()
        self.mod = FakeModule(self.insp, self.st)
        self.smoke = FakeSmoke()
        self.thermal = FakeThermal(self.clock, self.st)
        self.lock = FakeLock()
        self.recovery = m.RecoveryManager(self.rengine, self.insp, self.mod, self.smoke,
                                          self.clock)
        self.ex = m.ActionExecutor(self.engine, self.insp, self.recovery, self.lock,
                                   self.mod, self.thermal, self.clock)
        self.sup = m.RecoverySupervisor(self.recovery, self.lock, self.thermal)

    def run_action(self, action):
        return self.ex.run({"action": action})

    def kinds(self):
        return [r[0] for r in self.st.receipts]

    def revoke_after_admit(self):
        orig = self.engine.admit
        def wrapped(req):
            t = orig(req)
            self.st.lease = False
            return t
        self.engine.admit = wrapped


class StaticSafetyTests(unittest.TestCase):
    @staticmethod
    def _docstring_nodes(tree):
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    docs.add(node.body[0].value)
        return docs

    def test_no_process_shell_fs_or_cli(self):
        src = SCRIPT.read_text()
        tree = ast.parse(src)
        docs = self._docstring_nodes(tree)
        doc_lines = set()
        for d in docs:
            doc_lines.update(range(d.lineno, (d.end_lineno or d.lineno) + 1))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docs:
                self.assertNotIn("__main__", node.value)
                self.assertNotIn("shell=True", node.value)
            elif isinstance(node, ast.Name):
                self.assertNotIn(node.id, {"__main__", "eval", "exec", "open", "compile",
                                           "__import__", "environ", "sudo"})
            elif isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"__main__", "environ"})
        self.assertTrue(imported <= {"__future__", "abc", "dataclasses", "enum", "hashlib",
                                     "json", "math", "re", "typing"}, imported)
        non_doc_src = "\n".join(
            line for lineno, line in enumerate(src.splitlines(), 1)
            if lineno not in doc_lines
        )
        for bad in ("__main__", "eval(", "exec(", "open(", "environ", "shell=True", "sudo"):
            self.assertNotIn(bad, non_doc_src)

    def test_catalog_constants(self):
        self.assertEqual(m.CATALOG, ("audit", "iris-r0", "thermal"))
        self.assertEqual(m.IRIS_KERNEL_RELEASE, "7.3.0-11-generic")
        self.assertEqual(m.IRIS_OFFICIAL_SHA256,
                         "2183021a89244ad917b3afcbe24f2515c5d671033082f783c22ab817e6c6236b")
        self.assertEqual(m.IRIS_OFFICIAL_SRCVERSION, "575ECCB0F64EE1485C4E2FE")
        self.assertEqual(m.SMOKE_FRAMES, 120)
        self.assertEqual((m.THERMAL_DURATION_S, m.THERMAL_DUTY, m.THERMAL_WORKERS),
                         (10.0, 0.25, 1))
        self.assertEqual((m.THERMAL_SAMPLE_S, m.THERMAL_WATCHDOG_MAX_S,
                          m.THERMAL_STOP_TARGET_S), (0.25, 12.0, 2.0))
        self.assertEqual(set(m.UNIT_CATALOG), set(m.CATALOG))
        self.assertEqual(m.RECOVERY_STATES,
                         ("none", "restore_same_boot", "reconcile_required", "unknown"))

    def test_effect_adapters_take_no_parameters(self):
        for meth in ("unload_official", "load_official"):
            params = list(inspect.signature(getattr(m.IrisModuleControl, meth)).parameters)
            self.assertEqual(params, ["self"])
        self.assertFalse(hasattr(m.ThermalHandle, "disarm"))

    def test_recovery_requires_dedicated_engine(self):
        st = SharedState()
        eng = FakeEngine(st, "executor")
        clock = FakeClock()
        insp = FakeInspector()
        rec = m.RecoveryManager(eng, insp, FakeModule(insp, st), FakeSmoke(), clock)
        with self.assertRaises(ValueError):
            m.ActionExecutor(eng, insp, rec, FakeLock(), FakeModule(insp, st),
                             FakeThermal(clock, st), clock)


class RequestTests(Harness):
    def test_rejects_extra_fields_client_ids_and_unknown_actions(self):
        for raw in ({"action": "audit", "request_id": "client-1"},
                    {"action": "audit", "op_id": "op-99"},
                    {"action": "audit", "identity": "recovery"},
                    {"action": "audit", "argv": ["/bin/sh"]},
                    {"action": "audit", "env": {"LD_PRELOAD": "x"}},
                    {"action": "audit", "path": "/home/x/script"},
                    {"action": "shell"}, {"action": "iris-r1"}, {}, ["audit"], "audit",
                    {"action": None}):
            self.assertEqual(self.ex.run(raw).outcome, m.Outcome.DENIED, raw)
        self.assertEqual(self.st.n, 0)
        self.assertEqual(self.mod.unloads, 0)

    def test_op_id_generated_by_engine(self):
        self.assertEqual(self.run_action("audit").op_id, "op-1")


class RecoveryStateParsingTests(Harness):
    def test_flat_record_parsed_and_nested_rejected(self):
        self.st.marker = {"op_id": "op-7", "grant_id": "g", "boot_id": BOOT,
                          "kernel_release": m.IRIS_KERNEL_RELEASE,
                          "module_sha256": m.IRIS_OFFICIAL_SHA256,
                          "srcversion": m.IRIS_OFFICIAL_SRCVERSION, "committed_at": 1}
        state, mk = m.read_recovery_state(self.rengine)
        self.assertEqual((state, mk.op_id), ("restore_same_boot", "op-7"))

        class Nested(FakeEngine):
            def pending_recovery(self):
                return {"state": "restore_same_boot", "marker": dict(self.st.marker)}
        self.assertEqual(m.read_recovery_state(Nested(self.st, "recovery")),
                         ("unknown", None))

        class OldName(FakeEngine):
            def pending_recovery(self):
                return dict(self.st.marker, state="same_boot")
        self.assertEqual(m.read_recovery_state(OldName(self.st, "recovery"))[0], "unknown")

    def test_marker_tampering_is_unknown(self):
        base = {"op_id": "op-7", "grant_id": "g", "boot_id": BOOT,
                "kernel_release": m.IRIS_KERNEL_RELEASE,
                "module_sha256": m.IRIS_OFFICIAL_SHA256,
                "srcversion": m.IRIS_OFFICIAL_SRCVERSION, "committed_at": 1}
        for k, v in (("module_sha256", "f" * 64), ("srcversion", "X"),
                     ("kernel_release", "6.0"), ("boot_id", "?"), ("committed_at", None),
                     ("op_id", "")):
            self.st.marker = dict(base, **{k: v})
            self.assertEqual(m.read_recovery_state(self.rengine)[0], "unknown", k)
        self.st.marker = {k: v for k, v in base.items() if k != "grant_id"}
        self.assertEqual(m.read_recovery_state(self.rengine)[0], "unknown")


class AuditTests(Harness):
    def test_audit_pass_with_exact_bounded_evidence(self):
        r = self.run_action("audit")
        self.assertEqual(r.outcome, m.Outcome.PASS)
        self.assertTrue(set(r.details) <= set(m.AUDIT_ALLOWED_KEYS))
        res = [x for x in self.st.receipts if x[0] == "result"][0]
        ev = res[3]
        self.assertEqual(tuple(sorted(ev)), tuple(sorted(m.AUDIT_EVIDENCE_KEYS)))
        data = m.canonical_report_bytes(r.details)
        self.assertEqual(ev["report_sha256"], hashlib.sha256(data).hexdigest())
        self.assertRegex(ev["report_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(ev["report_bytes"], len(data))
        self.assertTrue(1 <= ev["report_bytes"] <= m.AUDIT_MAX_BYTES)
        self.assertEqual(ev["findings"], 0)
        json.loads(data)  # canonical JSON
        self.assertEqual((self.mod.unloads, self.mod.loads), (0, 0))
        self.assertEqual(self.thermal.starts, [])

    def test_cap_sys_module_present_or_unknown_fails(self):
        self.insp.cap = True
        self.assertEqual(self.run_action("audit").outcome, m.Outcome.FAILED)
        self.insp.cap = False
        self.insp.raise_on.add("cap")
        self.assertEqual(self.run_action("audit").outcome, m.Outcome.FAILED)
        self.assertTrue(all(x[2] == "fail" for x in self.st.receipts if x[0] == "result"))

    def test_required_read_missing_is_partial_not_pass(self):
        self.insp.raise_on.add("sha")
        r = self.run_action("audit")
        self.assertEqual(r.outcome, m.Outcome.PARTIAL)
        self.assertIn("module_file_sha256", r.details["missing"])
        self.assertEqual([x[2] for x in self.st.receipts if x[0] == "result"], ["fail"])
        self.insp.raise_on = {"module_state"}
        self.assertEqual(self.run_action("audit").outcome, m.Outcome.PARTIAL)

    def test_loaded_missing_or_invalid_fields_is_partial_not_pass(self):
        cases = [
            ("src-none", lambda i: setattr(i, "srcversion", None)),
            ("refcnt-none", lambda i: setattr(i, "refcnt", None)),
            ("refcnt-neg", lambda i: setattr(i, "refcnt", -1)),
            ("holders-bad", lambda i: setattr(i, "holders", ["bad/holder"])),
            ("holders-many", lambda i: setattr(i, "holders",
                                               [f"h{n}" for n in range(m.AUDIT_MAX_HOLDERS + 1)])),
        ]
        expected_key = {
            "src-none": "module_srcversion",
            "refcnt-none": "module_refcnt",
            "refcnt-neg": "module_refcnt",
            "holders-bad": "module_holders",
            "holders-many": "module_holders",
        }
        for name, mutate in cases:
            with self.subTest(name):
                self.setUp()
                mutate(self.insp)
                r = self.run_action("audit")
                self.assertEqual(r.outcome, m.Outcome.PARTIAL)
                self.assertIn(expected_key[name], r.details["missing"])
                self.assertEqual([x[2] for x in self.st.receipts if x[0] == "result"], ["fail"])

    def test_unloaded_module_explicit_fields_and_findings(self):
        self.insp.loaded = False
        r = self.run_action("audit")
        self.assertEqual(r.outcome, m.Outcome.PASS)
        self.assertEqual(r.details["missing"], [])
        self.assertIsNone(r.details["module_srcversion"])
        self.assertIsNone(r.details["module_refcnt"])
        self.assertEqual(r.details["module_holders"], [])
        ev = [x for x in self.st.receipts if x[0] == "result"][0][3]
        self.assertEqual(ev["findings"], 2)  # module_loaded=False and module_matches_official=False

    def test_audit_no_secret_sanitization(self):
        secret = "SECRET_TOKEN_XYZ=/root/.ssh/id_ed25519"
        self.insp.kernel = secret
        self.insp.srcversion = secret
        self.insp.holders = [secret]
        self.insp.sha = secret
        r = self.run_action("audit")
        self.assertEqual(r.outcome, m.Outcome.PARTIAL)
        self.assertNotIn(secret, json.dumps(r.details))
        self.assertTrue(set(r.details) <= set(m.AUDIT_ALLOWED_KEYS))

    def test_findings_counted_for_nonofficial_module(self):
        self.insp.srcversion = "DEADBEEF000000000000000"
        r = self.run_action("audit")
        self.assertEqual(r.outcome, m.Outcome.PASS)
        self.assertFalse(r.details["module_matches_official"])
        ev = [x for x in self.st.receipts if x[0] == "result"][0][3]
        self.assertEqual(ev["findings"], 1)

    def test_finish_failure_not_pass(self):
        self.st.fail_finish = True
        self.assertEqual(self.run_action("audit").outcome, m.Outcome.FAILED)

    def test_commit_failure_no_fabricated_finish(self):
        self.st.fail_commit = True
        r = self.run_action("audit")
        self.assertEqual(r.outcome, m.Outcome.DENIED)
        self.assertEqual(r.details["result_receipt"], "not-recorded")
        self.assertNotIn("result", self.kinds())

    def test_marker_pending_or_unknown_blocks_audit(self):
        self.st.marker = {"op_id": "op-x", "grant_id": "g", "boot_id": BOOT,
                          "kernel_release": m.IRIS_KERNEL_RELEASE,
                          "module_sha256": m.IRIS_OFFICIAL_SHA256,
                          "srcversion": m.IRIS_OFFICIAL_SRCVERSION, "committed_at": 1}
        self.assertEqual(self.run_action("audit").reason, "recovery-pending")
        self.st.boot_changed = True
        self.assertEqual(self.run_action("audit").reason, "recovery-pending")
        self.st.marker = None
        self.st.fail_pending = True
        self.assertEqual(self.run_action("audit").reason, "recovery-state-unknown")
        self.assertEqual(self.st.n, 0)

    def test_exhausted_uses(self):
        for _ in range(5):
            self.assertEqual(self.run_action("audit").outcome, m.Outcome.PASS)
        self.assertEqual(self.run_action("audit").outcome, m.Outcome.DENIED)

    def test_audit_checks_launch_inside_commit_and_blocks_after_revoke(self):
        seen_locked = []
        orig_cap = self.insp.has_cap_sys_module
        def record_lock():
            seen_locked.append(self.st.lock_held)
            return orig_cap()
        self.insp.has_cap_sys_module = record_lock
        r = self.run_action("audit")
        self.assertEqual(r.outcome, m.Outcome.PASS)
        self.assertEqual(self.st.launch_guard_calls, 1)
        self.assertEqual(seen_locked, [True])

        self.setUp()
        cap_calls = [0]
        def count_cap():
            cap_calls[0] += 1
            return False
        self.insp.has_cap_sys_module = count_cap
        orig_commit = self.engine.commit
        @contextlib.contextmanager
        def commit_then_revoke(ticket):
            with orig_commit(ticket) as committed:
                self.st.lease = False  # revoked before check_launch
                yield committed
        self.engine.commit = commit_then_revoke
        r = self.run_action("audit")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.ABORTED, "lease-expired-before-launch"))
        self.assertEqual(cap_calls[0], 0)  # capture never started
        self.assertEqual(self.results() if hasattr(self, "results") else
                         [x for x in self.st.receipts if x[0] == "result"][0][2], "aborted")

    def test_audit_launch_guard_requires_exact_true_no_none_fallback(self):
        for bad in (None, 1, "true", []):
            with self.subTest(bad=bad):
                self.setUp()
                self.st.launch_guard_override = bad
                cap_calls = [0]
                self.insp.has_cap_sys_module = lambda: cap_calls.__setitem__(0, cap_calls[0] + 1) or False
                r = self.run_action("audit")
                self.assertEqual((r.outcome, r.reason),
                                 (m.Outcome.FAILED, "launch-guard-invalid-return"))
                self.assertEqual(cap_calls[0], 0)
        self.setUp()
        self.st.provide_launch_guard = False
        r = self.run_action("audit")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "launch-guard-unavailable"))

    def test_audit_58_sensor_schema_finding_when_missing_or_extra(self):
        for count in (57, 59):
            with self.subTest(count=count):
                self.setUp()
                self.insp.soc = [45.0] * count
                r = self.run_action("audit")
                self.assertEqual(r.outcome, m.Outcome.PASS)
                self.assertIsNone(r.details["soc_max_temp_c"])
                ev = [x for x in self.st.receipts if x[0] == "result"][0][3]
                self.assertEqual(ev["findings"], 1)


class IrisR0Tests(Harness):
    def test_happy_path_cycle(self):
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.PASS, r)
        self.assertEqual((self.mod.unloads, self.mod.loads), (1, 1))
        self.assertTrue(self.mod.unload_under_lock)
        self.assertIsNone(self.st.marker)
        self.assertEqual(self.st.active, {})
        self.assertEqual(self.smoke.frames, [("cpu", 120), ("iris", 120)])
        self.assertEqual(self.kinds(), ["admission", "commit", "recovery"])  # no finish
        self.assertEqual(self.st.receipts[-1][2:], ("pass", "pass"))
        self.assertEqual(self.lock.acquisitions, 1)

    def test_preflight_negatives_no_admit_no_effect(self):
        cases = [
            ("kernel", lambda i: setattr(i, "kernel", "7.3.0-12-generic")),
            ("sha", lambda i: setattr(i, "sha", "0" * 64)),
            ("src", lambda i: setattr(i, "srcversion", "DEADBEEF")),
            ("refcnt", lambda i: setattr(i, "refcnt", 1)),
            ("holders", lambda i: setattr(i, "holders", ["venus"])),
            ("vis", lambda i: setattr(i, "users", m.DeviceUsers(False, []))),
            ("users", lambda i: setattr(i, "users", m.DeviceUsers(True, [4242]))),
            ("unloaded", lambda i: setattr(i, "loaded", False)),
            ("devices", lambda i: setattr(i, "devices", False)),
            ("ac", lambda i: setattr(i, "power", m.PowerState(False, 80.0, 30.0))),
            ("batt", lambda i: setattr(i, "power", m.PowerState(True, 29.0, 30.0))),
            ("btemp", lambda i: setattr(i, "power", m.PowerState(True, 80.0, 40.0))),
            ("soc-none", lambda i: setattr(i, "soc", _sensors(45.0, hot_val=None))),
            ("soc-empty", lambda i: setattr(i, "soc", [])),
            ("soc-57", lambda i: setattr(i, "soc", [45.0] * 57)),
            ("soc-59", lambda i: setattr(i, "soc", [45.0] * 59)),
            ("soc-hot", lambda i: setattr(i, "soc", _sensors(45.0, hot_val=56.0))),
            ("boot", lambda i: setattr(i, "boot", "not-a-boot-id")),
            ("modstate-exc", lambda i: i.raise_on.add("module_state")),
        ]
        for name, mutate in cases:
            with self.subTest(name):
                self.setUp()
                mutate(self.insp)
                r = self.run_action("iris-r0")
                self.assertEqual(r.outcome, m.Outcome.DENIED, name)
                self.assertEqual(self.st.n, 0, name)
                self.assertEqual((self.mod.unloads, self.mod.loads), (0, 0), name)

    def test_commit_denied_after_revoke_no_unload_no_finish(self):
        self.revoke_after_admit()
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.DENIED)
        self.assertEqual(self.mod.unloads, 0)
        self.assertIsNone(self.st.marker)
        self.assertEqual(self.st.uses["iris-r0"], 0)  # use not returned
        self.assertNotIn("result", self.kinds())

    def test_state_change_under_lock_rechecked_then_recovered_as_fail(self):
        orig = self.engine.admit
        def admit_then_busy(req):
            t = orig(req)
            self.insp.users = m.DeviceUsers(True, [99])
            return t
        self.engine.admit = admit_then_busy
        r = self.run_action("iris-r0")
        self.assertEqual(self.mod.unloads, 0)
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "device-has-users"))
        self.assertIsNone(self.st.marker)  # verified untouched module, cleared as fail
        self.assertEqual(self.st.receipts[-1][2:], ("fail", "fail"))

    def test_unload_failure_no_retry_and_final_fail(self):
        self.mod.unload_ok = False
        r = self.run_action("iris-r0")
        self.assertEqual(self.mod.unloads, 1)
        self.assertEqual(self.mod.loads, 0)
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "unload-failed"))
        self.assertEqual(r.details["final"], "fail")
        self.assertIsNone(self.st.marker)

    def test_engine_final_fail_overrides(self):
        self.st.clear_override = "fail"
        r = self.run_action("iris-r0")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "engine-final-fail"))

    def test_load_failure_keeps_marker_and_blocks_everything(self):
        self.mod.load_ok = False
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.RECOVERY_PENDING)
        self.assertEqual((self.mod.unloads, self.mod.loads), (1, 1))
        self.assertIsNotNone(self.st.marker)
        for a in ("audit", "iris-r0", "thermal"):
            self.assertEqual(self.run_action(a).reason, "recovery-pending")
        self.assertEqual(self.mod.unloads, 1)

    def test_smoke_failure_keeps_marker(self):
        for attr in ("cpu_ok", "iris_ok"):
            with self.subTest(attr):
                self.setUp()
                setattr(self.smoke, attr, False)
                r = self.run_action("iris-r0")
                self.assertEqual((r.outcome, r.reason),
                                 (m.Outcome.RECOVERY_PENDING, "smoke-failed"))
                self.assertIsNotNone(self.st.marker)
                self.assertNotIn("recovery", self.kinds())

    def test_module_state_unknown_after_unload_no_load(self):
        self.mod.after_unload = lambda: self.insp.raise_on.add("module_state")
        r = self.run_action("iris-r0")
        self.assertEqual(r.reason, "module-state-unknown")
        self.assertEqual(self.mod.loads, 0)
        self.assertIsNotNone(self.st.marker)

    def test_wrong_srcversion_after_reload_keeps_marker(self):
        orig = self.mod.load_official
        def load_wrong():
            ok = orig()
            self.insp.srcversion = "CANDIDATE"
            return ok
        self.mod.load_official = load_wrong
        r = self.run_action("iris-r0")
        self.assertEqual(r.reason, "srcversion-mismatch")
        self.assertIsNotNone(self.st.marker)

    def test_artifact_changed_before_load_no_load(self):
        self.mod.after_unload = lambda: setattr(self.insp, "sha", "a" * 64)
        r = self.run_action("iris-r0")
        self.assertEqual(r.reason, "official-artifact-mismatch")
        self.assertEqual(self.mod.loads, 0)

    def test_recovery_allowed_after_revoke(self):
        self.mod.after_unload = lambda: setattr(self.st, "lease", False)
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.PASS)
        self.assertEqual(self.mod.loads, 1)
        self.assertIsNone(self.st.marker)

    def test_clear_failure_no_pass_marker_preserved(self):
        self.st.fail_clear = True
        r = self.run_action("iris-r0")
        self.assertEqual((r.outcome, r.reason),
                         (m.Outcome.RECOVERY_PENDING, "restored-but-clear-receipt-failed"))
        self.assertIsNotNone(self.st.marker)

    def test_commit_exit_error_after_unload_still_recovers(self):
        self.st.fail_commit_exit = True
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.PASS)
        self.assertEqual(self.mod.loads, 1)

    def test_executor_crash_supervisor_recovers_as_fail(self):
        def crash():
            raise KeyboardInterrupt("executor died")
        self.mod.after_unload = crash
        with self.assertRaises(KeyboardInterrupt):
            self.run_action("iris-r0")
        self.assertFalse(self.lock.held)
        self.assertIsNotNone(self.st.marker)
        self.st.lease = False  # expired/revoked meanwhile
        out = self.sup.run_once()
        rec = out["recovery"]
        self.assertEqual((rec.outcome, rec.details["final"]), (m.Outcome.FAILED, "fail"))
        self.assertEqual((self.mod.unloads, self.mod.loads), (1, 1))
        self.assertIsNone(self.st.marker)
        self.assertEqual(self.st.receipts[-1][2:], ("fail", "fail"))

    def test_supervisor_serialised_with_inflight_r0(self):
        seen = {}
        def supervisor_during_unload():
            try:
                self.sup.run_once()
            except AssertionError as exc:
                seen["blocked"] = str(exc)
        self.mod.after_unload = supervisor_during_unload
        self.run_action("iris-r0")
        self.assertIn("recovery lock contention", seen["blocked"])
        self.assertEqual(self.mod.loads, 1)

    def test_boot_changed_blocks_without_load(self):
        self.mod.after_unload = lambda: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.run_action("iris-r0")
        self.st.boot_changed = True
        r = self.sup.run_once()["recovery"]
        self.assertEqual(r.outcome, m.Outcome.BOOT_CHANGED_BLOCKED)
        self.assertEqual(self.mod.loads, 0)
        self.assertIsNotNone(self.st.marker)
        self.assertEqual(self.run_action("audit").reason, "recovery-pending")

    def test_inspector_boot_differs_from_marker_no_load(self):
        self.mod.after_unload = lambda: setattr(self.insp, "boot", OTHER_BOOT)
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.BOOT_CHANGED_BLOCKED)
        self.assertEqual(self.mod.loads, 0)

    def test_marker_unknown_no_load(self):
        self.st.fail_pending = True
        r = self.recovery.restore()
        self.assertEqual(r.outcome, m.Outcome.RECOVERY_PENDING)
        self.assertEqual(self.mod.loads, 0)

    def test_recovery_budget(self):
        orig = self.mod.load_official
        def slow_load():
            self.clock.t += m.R0_RECOVERY_BUDGET_S + 1
            return orig()
        self.mod.load_official = slow_load
        r = self.run_action("iris-r0")
        self.assertEqual(r.reason, "budget-exceeded")
        self.assertIsNotNone(self.st.marker)

    def test_single_use_no_second_unload(self):
        self.assertEqual(self.run_action("iris-r0").outcome, m.Outcome.PASS)
        self.assertEqual(self.st.launch_guard_calls, 1)
        self.assertEqual(self.run_action("iris-r0").outcome, m.Outcome.DENIED)
        self.assertEqual(self.mod.unloads, 1)

    def test_lease_expired_during_preflight_blocks_unload_via_check_launch(self):
        orig_users = self.insp.device_users
        calls = [0]
        def expire_during_preflight():
            calls[0] += 1
            if calls[0] == 2:  # second call is under held commit flock
                self.st.lease = False
            return orig_users()
        self.insp.device_users = expire_during_preflight
        r = self.run_action("iris-r0")
        self.assertEqual(self.mod.unloads, 0)
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "lease-expired-before-launch"))
        self.assertEqual(self.st.launch_guard_calls, 1)
        self.assertIsNone(self.st.marker)
        self.assertEqual(self.st.receipts[-1][2:], ("fail", "fail"))

    def test_missing_launch_guard_fails_closed_no_unload(self):
        self.st.provide_launch_guard = False
        r = self.run_action("iris-r0")
        self.assertEqual(self.mod.unloads, 0)
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "launch-guard-unavailable"))
        self.assertIsNone(self.st.marker)

        self.setUp()
        self.st.launch_guard_override = None
        r = self.run_action("iris-r0")
        self.assertEqual(self.mod.unloads, 0)
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "launch-guard-invalid-return"))

    def test_boot_changes_during_restore_hash_blocks_load(self):
        orig_sha = self.insp.official_module_sha256
        def hash_then_boot():
            result = orig_sha()
            if not self.insp.loaded:
                self.insp.boot = OTHER_BOOT
            return result
        self.insp.official_module_sha256 = hash_then_boot
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.BOOT_CHANGED_BLOCKED)
        self.assertEqual(self.mod.loads, 0)
        self.assertIsNotNone(self.st.marker)

    def test_final_identity_check_can_exhaust_recovery_budget(self):
        orig_sha = self.insp.official_module_sha256
        def slow_final_hash():
            if self.smoke.frames == [("cpu", 120), ("iris", 120)]:
                self.clock.t += m.R0_RECOVERY_BUDGET_S + 1
            return orig_sha()
        self.insp.official_module_sha256 = slow_final_hash
        r = self.run_action("iris-r0")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.RECOVERY_PENDING, "budget-exceeded"))
        self.assertIsNotNone(self.st.marker)
        self.assertFalse(any(x[0]=="recovery" for x in self.st.receipts))

    def test_recovery_rechecks_boot_kernel_and_budget_at_all_stages(self):
        # 1) Boot changed immediately before load -> no load, marker kept
        self.mod.after_unload = lambda: setattr(self.insp, "boot", OTHER_BOOT)
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.BOOT_CHANGED_BLOCKED)
        self.assertEqual(self.mod.loads, 0)
        self.assertIsNotNone(self.st.marker)

        # 2) Budget exceeded immediately before load -> no load, marker kept
        self.setUp()
        orig_sha = self.insp.official_module_sha256
        sha_calls = [0]
        def slow_sha_in_restore():
            sha_calls[0] += 1
            if sha_calls[0] >= 2:  # preflight=1, restore before load=2
                self.clock.t += m.R0_RECOVERY_BUDGET_S + 1
            return orig_sha()
        self.insp.official_module_sha256 = slow_sha_in_restore
        r = self.run_action("iris-r0")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.RECOVERY_PENDING, "budget-exceeded"))
        self.assertEqual(self.mod.loads, 0)
        self.assertIsNotNone(self.st.marker)

        # 3) Boot changed between CPU and Iris smoke -> Iris skipped, marker kept
        self.setUp()
        orig_cpu = self.smoke.cpu_decode
        def cpu_then_boot(frames):
            ok = orig_cpu(frames)
            self.insp.boot = OTHER_BOOT
            return ok
        self.smoke.cpu_decode = cpu_then_boot
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.BOOT_CHANGED_BLOCKED)
        self.assertEqual(self.smoke.frames, [("cpu", 120)])
        self.assertIsNotNone(self.st.marker)

        # 4) Kernel changed between CPU and Iris smoke -> Iris skipped, marker kept
        self.setUp()
        orig_cpu = self.smoke.cpu_decode
        def cpu_then_kernel(frames):
            ok = orig_cpu(frames)
            self.insp.kernel = "7.3.0-99-other"
            return ok
        self.smoke.cpu_decode = cpu_then_kernel
        r = self.run_action("iris-r0")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.RECOVERY_PENDING, "kernel-mismatch"))
        self.assertEqual(self.smoke.frames, [("cpu", 120)])
        self.assertIsNotNone(self.st.marker)

        # 5) Budget exceeded between CPU and Iris smoke -> Iris skipped, marker kept
        self.setUp()
        orig_cpu = self.smoke.cpu_decode
        def cpu_then_slow(frames):
            ok = orig_cpu(frames)
            self.clock.t += m.R0_RECOVERY_BUDGET_S + 1
            return ok
        self.smoke.cpu_decode = cpu_then_slow
        r = self.run_action("iris-r0")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.RECOVERY_PENDING, "budget-exceeded"))
        self.assertEqual(self.smoke.frames, [("cpu", 120)])
        self.assertIsNotNone(self.st.marker)

        # 6) Boot changed after Iris smoke before clear -> clear skipped, marker kept
        self.setUp()
        orig_iris = self.smoke.iris_decode
        def iris_then_boot(frames):
            ok = orig_iris(frames)
            self.insp.boot = OTHER_BOOT
            return ok
        self.smoke.iris_decode = iris_then_boot
        r = self.run_action("iris-r0")
        self.assertEqual(r.outcome, m.Outcome.BOOT_CHANGED_BLOCKED)
        self.assertNotIn("recovery", self.kinds())
        self.assertIsNotNone(self.st.marker)

        # 7) Budget exceeded after Iris smoke before clear -> clear skipped, marker kept
        self.setUp()
        orig_iris = self.smoke.iris_decode
        def iris_then_slow(frames):
            ok = orig_iris(frames)
            self.clock.t += m.R0_RECOVERY_BUDGET_S + 1
            return ok
        self.smoke.iris_decode = iris_then_slow
        r = self.run_action("iris-r0")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.RECOVERY_PENDING, "budget-exceeded"))
        self.assertNotIn("recovery", self.kinds())
        self.assertIsNotNone(self.st.marker)

        # 8) Non-finite / backward clock -> recovery-clock-error, marker kept
        self.setUp()
        self.clock.t = float("nan")
        r = self.run_action("iris-r0")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.RECOVERY_PENDING, "recovery-clock-error"))
        self.assertEqual(self.mod.loads, 0)
        self.assertIsNotNone(self.st.marker)


class ThermalTests(Harness):
    def _at(self, t, mutate):
        fired = []
        def hook(now):
            if now >= t and not fired:
                fired.append(now)
                mutate()
        self.clock.on_sleep.append(hook)

    def results(self):
        return [x for x in self.st.receipts if x[0] == "result"]

    def test_happy_path_pass_without_audit_evidence(self):
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.PASS, r)
        self.assertEqual(self.thermal.starts, [(10.0, 0.25, 1)])
        self.assertTrue(self.thermal.start_under_lock)
        self.assertEqual(r.details["samples"], 41)  # t=0.0..10.0 inclusive (final boundary sample)
        self.assertGreaterEqual(r.details["elapsed_s"], m.THERMAL_DURATION_S)
        self.assertLessEqual(r.details["stop_latency_s"], 2.0)
        self.assertEqual(self.results()[0][2:], ("pass", None))

    def test_aborts(self):
        cases = {
            "soc-temp-limit": lambda: setattr(self.insp, "soc", _sensors(50.0, hot_val=65.0)),
            "battery-temp-limit": lambda: setattr(self.insp, "power",
                                                  m.PowerState(True, 80.0, 40.0)),
            "battery-below-minimum": lambda: setattr(self.insp, "power",
                                                     m.PowerState(True, 29.9, 30.0)),
            "external-power-required": lambda: setattr(self.insp, "power",
                                                       m.PowerState(False, 80.0, 30.0)),
            "soc-sensor-invalid": lambda: setattr(self.insp, "soc",
                                                  _sensors(50.0, hot_val=float("nan"))),
            "soc-missing-57": lambda: setattr(self.insp, "soc", [50.0] * 57),
            "soc-extra-59": lambda: setattr(self.insp, "soc", [50.0] * 59),
            "sensor-error": lambda: self.insp.raise_on.add("power"),
            "lease-invalid": lambda: setattr(self.st, "lease", False),
        }
        expected_reason = lambda k: "soc-sensor-invalid" if k.startswith("soc-missing") or k.startswith("soc-extra") else k
        for case, mutate in cases.items():
            reason = expected_reason(case)
            with self.subTest(case=case):
                self.setUp()
                self._at(3.0, mutate)
                r = self.run_action("thermal")
                self.assertEqual((r.outcome, r.reason), (m.Outcome.ABORTED, reason))
                self.assertTrue(r.details["stopped"])
                self.assertLessEqual(self.clock.t, 3.0 + 0.25 + 2.0 + 1e-9)
                self.assertEqual(self.thermal.handle.stop_calls, 1)
                self.assertEqual(self.results()[0][2], "aborted")

    def test_start_denials(self):
        for name, mutate in (
                ("hot", lambda: setattr(self.insp, "soc", _sensors(45.0, hot_val=55.0))),
                ("nosensor", lambda: setattr(self.insp, "soc", [])),
                ("missing57", lambda: setattr(self.insp, "soc", [45.0] * 57)),
                ("extra59", lambda: setattr(self.insp, "soc", [45.0] * 59)),
                ("ac", lambda: setattr(self.insp, "power", m.PowerState(None, 80.0, 30.0))),
                ("pct", lambda: setattr(self.insp, "power", m.PowerState(True, None, 30.0)))):
            with self.subTest(name):
                self.setUp()
                mutate()
                self.assertEqual(self.run_action("thermal").outcome, m.Outcome.DENIED)
                self.assertEqual(self.thermal.starts, [])
                self.assertEqual(self.st.n, 0)

    def test_revoked_before_commit_no_spawn_no_finish(self):
        self.revoke_after_admit()
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.DENIED)
        self.assertEqual(self.thermal.starts, [])
        self.assertNotIn("result", self.kinds())

    def test_envelope_rechecked_under_lock(self):
        orig = self.engine.admit
        def admit_then_hot(req):
            t = orig(req)
            self.insp.soc = _sensors(60.0)
            return t
        self.engine.admit = admit_then_hot
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.ABORTED, "soc-too-hot-to-start"))
        self.assertEqual(self.thermal.starts, [])

    def test_watchdog_unconfirmed_or_too_long_fails(self):
        for wd in (None, 13.0, 0.0, float("inf")):
            with self.subTest(wd):
                self.setUp()
                self.thermal.handle.wd = wd
                r = self.run_action("thermal")
                self.assertEqual((r.outcome, r.reason),
                                 (m.Outcome.FAILED, "watchdog-unconfirmed"))
                self.assertEqual(self.thermal.handle.stop_calls, 1)

    def test_worker_exited_early_not_pass(self):
        self.thermal.handle.exit_at = 4.0
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "worker-exited-early"))

    def test_worker_state_unknown_left_active(self):
        self._at(2.0, lambda: setattr(self.thermal.handle, "alive_raises", True))
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.BLOCKED_ACTIVE)  # stop cannot be confirmed
        self.assertNotIn("result", self.kinds())
        self.assertEqual(self.run_action("audit").outcome, m.Outcome.DENIED)

    def test_stop_unconfirmed_leaves_active_no_finish_no_next(self):
        self.thermal.handle.stop_delay = 5.0
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason),
                         (m.Outcome.BLOCKED_ACTIVE, "stop-not-confirmed-watchdog-backstop"))
        self.assertTrue(r.details["active_left_blocked"])
        self.assertNotIn("result", self.kinds())
        self.assertIn("op-1", self.st.active)
        self.assertEqual(self.run_action("audit").outcome, m.Outcome.DENIED)

    def test_stop_within_target(self):
        self.thermal.handle.stop_delay = 1.5
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.PASS)

    def test_launch_unknown_orphans_stopped_fail(self):
        self.thermal.fail = True
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "worker-launch-unknown"))
        self.assertEqual(self.thermal.orphan_stops, 1)
        self.assertEqual(self.results()[0][2], "fail")

    def test_launch_unknown_orphans_not_stopped_left_active(self):
        self.thermal.fail = True
        self.thermal.orphans_ok = False
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.BLOCKED_ACTIVE)
        self.assertNotIn("result", self.kinds())
        self.assertEqual(self.run_action("audit").outcome, m.Outcome.DENIED)

    def test_supervisor_fault_stops_worker_not_pass(self):
        def boom(now):
            if now >= 1.0:
                raise RuntimeError("monitor bug")
        self.clock.on_sleep.append(boom)
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.FAILED)
        self.assertTrue(r.reason.startswith("supervisor-error"))
        self.assertGreaterEqual(self.thermal.handle.stop_calls, 1)

    def test_commit_exit_error_after_spawn_stops_worker(self):
        self.st.fail_commit_exit = True
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.FAILED)
        self.assertTrue(r.reason.startswith("commit-exit-error"))
        self.assertEqual(self.thermal.handle.stop_calls, 1)

    def test_supervisor_restart_stops_orphans(self):
        out = self.sup.run_once()
        self.assertTrue(out["thermal_orphans_stopped"])
        self.assertEqual(out["recovery"].reason, "no-recovery-pending")

    def test_finish_failure_not_pass(self):
        self.st.fail_finish = True
        self.assertEqual(self.run_action("thermal").outcome, m.Outcome.FAILED)

    def test_watchdog_ready_denies_before_admit_and_aborts_under_lock(self):
        for bad in (None, 0.0, -1.0, 13.0, float("nan"), True):
            with self.subTest(bad=bad):
                self.setUp()
                self.thermal.wd_ready = bad
                r = self.run_action("thermal")
                self.assertEqual((r.outcome, r.reason), (m.Outcome.DENIED, "watchdog-not-ready"))
                self.assertEqual(self.st.n, 0)
                self.assertEqual(self.thermal.starts, [])
        self.setUp()
        self.thermal.wd_ready_raises = True
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.DENIED, "watchdog-not-ready"))
        self.assertEqual(self.st.n, 0)

        self.setUp()
        orig = self.engine.admit
        def admit_then_wd_bad(req):
            t = orig(req)
            self.thermal.wd_ready = None
            return t
        self.engine.admit = admit_then_wd_bad
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.ABORTED, "watchdog-not-ready"))
        self.assertEqual(self.thermal.starts, [])

    def test_lease_expired_during_preflight_blocks_spawn_via_check_launch(self):
        orig_wd = self.thermal.watchdog_ready
        calls = [0]
        def expire_under_lock():
            calls[0] += 1
            if calls[0] == 2:  # second call is under held commit flock
                self.st.lease = False
            return orig_wd()
        self.thermal.watchdog_ready = expire_under_lock
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.ABORTED, "lease-expired-before-launch"))
        self.assertEqual(self.thermal.starts, [])
        self.assertEqual(self.st.launch_guard_calls, 1)
        self.assertEqual(self.results()[0][2], "aborted")

    def test_missing_launch_guard_fails_closed_no_spawn(self):
        self.st.provide_launch_guard = False
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "launch-guard-unavailable"))
        self.assertEqual(self.thermal.starts, [])

        self.setUp()
        self.st.launch_guard_override = None
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "launch-guard-invalid-return"))
        self.assertEqual(self.thermal.starts, [])

    def test_final_boundary_checks_lease_and_all_sensors_before_pass(self):
        cases = {
            "lease-invalid": lambda: setattr(self.st, "lease", False),
            "soc-temp-limit": lambda: setattr(self.insp, "soc", _sensors(50.0, hot_val=65.0)),
            "battery-temp-limit": lambda: setattr(self.insp, "power",
                                                  m.PowerState(True, 80.0, 40.0)),
            "battery-below-minimum": lambda: setattr(self.insp, "power",
                                                     m.PowerState(True, 29.9, 30.0)),
            "external-power-required": lambda: setattr(self.insp, "power",
                                                       m.PowerState(False, 80.0, 30.0)),
            "soc-57": lambda: setattr(self.insp, "soc", [45.0] * 57),
            "soc-59": lambda: setattr(self.insp, "soc", [45.0] * 59),
        }
        for name, mutate in cases.items():
            reason = "soc-sensor-invalid" if name.startswith("soc-5") else name
            with self.subTest(case=name):
                self.setUp()
                self._at(m.THERMAL_DURATION_S, mutate)
                r = self.run_action("thermal")
                self.assertEqual((r.outcome, r.reason), (m.Outcome.ABORTED, reason))
                self.assertTrue(r.details["stopped"])
                self.assertEqual(self.results()[0][2], "aborted")

    def test_boundary_thresholds_pass_and_stop_exact_target(self):
        self.insp.soc = _sensors(54.99)
        self._at(0.5, lambda: setattr(self.insp, "soc", _sensors(64.99)))
        self.thermal.handle.stop_delay = 1.95
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.PASS)
        self.assertLessEqual(r.details["stop_latency_s"], 2.0)

        self.setUp()
        self.thermal.handle.stop_delay = 2.05
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.BLOCKED_ACTIVE)

    def test_worker_exited_right_before_duration_not_false_pass(self):
        for exit_at in (9.9, 10.0):
            with self.subTest(exit_at=exit_at):
                self.setUp()
                self.thermal.handle.exit_at = exit_at
                r = self.run_action("thermal")
                self.assertEqual((r.outcome, r.reason),
                                 (m.Outcome.FAILED, "worker-exited-early"))
                self.assertEqual(self.results()[0][2], "fail")

    def test_stop_latency_exceeded_fails(self):
        def slow_stop():
            self.clock.t += 2.5
            self.thermal.handle.running = False
        self.thermal.handle.stop = slow_stop
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "stop-latency-exceeded"))
        self.assertTrue(r.details["stopped"])
        self.assertGreater(r.details["stop_latency_s"], 2.0)

    def test_all_soc_sensors_checked_and_elapsed_recorded(self):
        self.insp.soc = _sensors(40.0, hot_val=55.0)
        self.assertEqual(self.run_action("thermal").outcome, m.Outcome.DENIED)
        self.setUp()
        self._at(2.0, lambda: setattr(self.insp, "soc", _sensors(40.0, hot_val=None)))
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.ABORTED, "soc-sensor-invalid"))
        self.setUp()
        r = self.run_action("thermal")
        self.assertEqual(r.outcome, m.Outcome.PASS)
        self.assertGreaterEqual(r.details["elapsed_s"], m.THERMAL_DURATION_S)

    def test_clock_non_monotonic_fails_and_stops_worker(self):
        def backward(now):
            if now >= 1.0:
                self.clock.t -= 0.5
        self.clock.on_sleep.append(backward)
        r = self.run_action("thermal")
        self.assertEqual((r.outcome, r.reason), (m.Outcome.FAILED, "clock-error"))
        self.assertTrue(r.details["stopped"])


class EnvelopeTests(unittest.TestCase):
    def test_boundaries(self):
        P = m.PowerState
        ok = P(True, 30.0, 39.9)
        self.assertTrue(m.envelope_ok(_sensors(54.9), ok, starting=True)[0])
        self.assertFalse(m.envelope_ok(_sensors(55.0), ok, starting=True)[0])
        self.assertTrue(m.envelope_ok(_sensors(64.9), ok, starting=False)[0])
        self.assertFalse(m.envelope_ok(_sensors(65.0), ok, starting=False)[0])
        self.assertFalse(m.envelope_ok(_sensors(40.0, hot_val=66.0), ok, starting=False)[0])
        self.assertFalse(m.envelope_ok(_sensors(50.0), P(True, 30.0, 40.0), starting=False)[0])
        self.assertFalse(m.envelope_ok(_sensors(50.0), P(True, 29.99, 30.0), starting=False)[0])
        for bad in (None, "50", [50.0] * 57, [50.0] * 59,
                    _sensors(50.0, hot_val=True), _sensors(50.0, hot_val=float("inf")),
                    _sensors(50.0, hot_val=200.0), _sensors(50.0, hot_val="x")):
            self.assertFalse(m.envelope_ok(bad, ok, starting=False)[0], bad)
        self.assertFalse(m.envelope_ok(_sensors(50.0), None, starting=False)[0])


if __name__ == "__main__":
    unittest.main()
