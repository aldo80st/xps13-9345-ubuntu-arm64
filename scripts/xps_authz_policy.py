"""XPS AUTHZ v1.1 — deterministic transactional policy engine (M2-A).

Pure policy/ledger library (Python stdlib only).  It NEVER runs commands,
loads/unloads modules or touches hardware.  It decides admission and keeps one
authoritative, durable, root-owned state file.  See docs/xps-authz-policy-api.md.

    ticket = engine.admit({"action": "audit"})      # consumes 1 use, durable receipt
    with engine.commit(ticket) as op:               # shared lock held across launch
        if op.check_launch() is True:               # after preflight, just before launch
            launch_fixed_unit(op.action)            # effect starts UNDER the lock
    engine.finish(ticket, "pass")

Caller identity (``caller_uid``) must be injected ONLY by the trusted root
broker from the kernel (SO_PEERCRED of the connecting socket) — never from
client-supplied data.  Owner control and recovery are separate entry points.
"""
from __future__ import annotations

import contextlib
import dataclasses
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import time
import threading
import uuid
from typing import Callable, Dict, Iterator, Optional

SCHEMA = "xps-authz-policy/1"
GRANT_SECONDS = 1200
STATE_FILE = "state.json"
LOCK_FILE = "lock"
OK_TOKEN = "ledger-ok"          # ABSENCE of this token == persistent ledger fault
ARCHIVE_PREFIX = "receipts-archive-"
SMOKE_FRAMES = 120
COMMIT_WINDOW = 30
STOCK_IRIS_SHA256 = "2183021a89244ad917b3afcbe24f2515c5d671033082f783c22ab817e6c6236b"

CATALOG: Dict[str, Dict[str, int]] = {
    "audit": {"uses": 5, "reserve": 60},
    "iris-r0": {"uses": 1, "reserve": 300},
    "thermal": {"uses": 1, "reserve": 15},
}
RESULTS = ("pass", "fail", "aborted")
MAX_RECEIPTS = 2048
RESERVED_RECEIPTS = 32          # kept for finish/commit/revoke/recovery; never truncated
_HEX32 = re.compile(r"\A[0-9a-f]{32}\Z")
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_KREL = re.compile(r"\A[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}\Z")
_SRCV = re.compile(r"\A[0-9A-F]{23}\Z")
AUDIT_MAX_BYTES = 16 * 1024 * 1024
AUDIT_MAX_FINDINGS = 10000


class PolicyError(Exception):
    """Base error; every error is fail-closed (no effect may start)."""


class Denied(PolicyError):
    pass


class StateCorrupt(PolicyError):
    pass


class LedgerWriteError(PolicyError):
    pass


class UnsafeStorage(PolicyError):
    pass


def _default_boottime() -> float:
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def _default_boot_id() -> str:
    with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as fh:
        return fh.read().strip()


def _default_kernel() -> str:
    return os.uname().release


class FsOps:
    """Filesystem primitives; tests subclass to inject write/fsync failures."""

    def write(self, fd: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]

    def fsync(self, fd: int) -> None:
        os.fsync(fd)

    def replace(self, src: str, dst: str, dir_fd: int) -> None:
        os.replace(src, dst, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)

    def unlink(self, name: str, dir_fd: int) -> None:
        os.unlink(name, dir_fd=dir_fd)


@dataclasses.dataclass(frozen=True)
class Identities:
    """Kernel-verified uids (SO_PEERCRED in the root broker)."""
    owner: int = 0
    agent: int = -1
    recovery: int = 0


@dataclasses.dataclass(frozen=True)
class R0Pin:
    """Root-owned install configuration for the official Iris module.
    The SHA-256 is fixed to STOCK_IRIS_SHA256; anything else is rejected."""
    kernel_release: str
    srcversion: str
    module_sha256: str = STOCK_IRIS_SHA256

    def __post_init__(self):
        if self.module_sha256 != STOCK_IRIS_SHA256:
            raise ValueError("R0 pin must be the official stock Iris SHA-256")
        if not (type(self.kernel_release) is str and _KREL.match(self.kernel_release)):
            raise ValueError("invalid kernel release pin")
        if not (type(self.srcversion) is str and _SRCV.match(self.srcversion)):
            raise ValueError("invalid module srcversion pin")


@dataclasses.dataclass(frozen=True)
class Ticket:
    op_id: str
    action: str
    grant_id: str
    boot_id: str
    admitted_at: float
    digest: str


@dataclasses.dataclass(frozen=True)
class CommittedOp:
    """Read-only view yielded by commit(); built from durable state."""
    op_id: str
    action: str
    check_launch: Callable[[], bool] = dataclasses.field(repr=False, compare=False)


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------

def _empty_state() -> dict:
    return {"schema": SCHEMA, "seq": 0, "grant": None, "active": None,
            "r0_marker": None, "receipts": []}


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _ticket_digest(op: dict) -> str:
    core = {k: op[k] for k in ("op_id", "action", "grant_id", "boot_id", "admitted_at")}
    return hashlib.sha256(_canon(core)).hexdigest()


def _req(cond: bool, what: str) -> None:
    if not cond:
        raise StateCorrupt("schema violation: " + what)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0


def _int(v) -> bool:
    return type(v) is int and v >= 0


def _str(v) -> bool:
    return isinstance(v, str) and 0 < len(v) <= 128


def validate_state(st) -> None:
    _req(isinstance(st, dict) and set(st) == {"schema", "seq", "grant", "active", "r0_marker", "receipts"}, "top keys")
    _req(st["schema"] == SCHEMA, "schema id")
    _req(_int(st["seq"]), "seq")
    g = st["grant"]
    if g is not None:
        _req(isinstance(g, dict) and set(g) == {"grant_id", "boot_id", "incarnation", "issued_at", "expires_at", "uses", "revoked"}, "grant keys")
        _req(bool(_HEX32.match(str(g["grant_id"]))) and _str(g["boot_id"]) and _str(g["incarnation"]), "grant ids")
        # Integer seconds: issued_at = floor(BOOTTIME) so the effective lease is <= 1200 s.
        _req(_int(g["issued_at"]) and _int(g["expires_at"]) and g["expires_at"] - g["issued_at"] == GRANT_SECONDS, "grant times")
        _req(type(g["revoked"]) is bool, "grant revoked")
        _req(isinstance(g["uses"], dict) and set(g["uses"]) == set(CATALOG), "grant uses keys")
        for name, left in g["uses"].items():
            _req(_int(left) and left <= CATALOG[name]["uses"], "uses " + name)
    a = st["active"]
    if a is not None:
        _req(isinstance(a, dict) and set(a) == {"op_id", "action", "grant_id", "boot_id", "admitted_at", "digest", "phase", "committed_at"}, "active keys")
        _req(isinstance(a["action"], str) and a["action"] in CATALOG, "active action")
        _req(a["phase"] in ("admitted", "committed"), "active phase")
        _req(bool(_HEX32.match(str(a["op_id"]))) and _str(a["boot_id"]) and _num(a["admitted_at"]), "active fields")
        _req(g is not None and a["grant_id"] == g["grant_id"], "active grant reference")
        _req((a["phase"] == "committed") == _num(a["committed_at"]), "active phase/commit")
        _req(a["phase"] == "admitted" or a["committed_at"] >= a["admitted_at"], "commit order")
        _req(a["digest"] == _ticket_digest(a), "active digest")
    m = st["r0_marker"]
    if m is not None:
        _req(isinstance(m, dict) and set(m) == {"op_id", "grant_id", "boot_id", "committed_at", "kernel_release", "module_sha256", "srcversion"}, "marker keys")
        _req(bool(_HEX32.match(str(m["op_id"]))) and _str(m["grant_id"]) and _str(m["boot_id"]) and _num(m["committed_at"]), "marker fields")
        _req(_str(m["kernel_release"]) and _str(m["srcversion"]) and m["module_sha256"] == STOCK_IRIS_SHA256, "marker pin")
    if a is not None and a["action"] == "iris-r0" and a["phase"] == "committed":
        _req(m is not None and m["op_id"] == a["op_id"], "committed r0 without marker")
    r = st["receipts"]
    _req(isinstance(r, list) and len(r) <= MAX_RECEIPTS, "receipts bound")
    prev = None
    for rec in r:
        _req(isinstance(rec, dict) and isinstance(rec.get("event"), str) and _int(rec.get("seq")), "receipt")
        _req(prev is None or rec["seq"] == prev + 1, "receipt sequence")
        prev = rec["seq"]
    _req(prev is None or prev == st["seq"], "receipt head")


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise StateCorrupt("duplicate JSON key")
        out[k] = v
    return out


def _bad_constant(name):
    raise StateCorrupt("non-finite JSON constant " + name)


def _strict_loads(data: bytes):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_no_dupes, parse_constant=_bad_constant)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise StateCorrupt("unparseable state") from exc


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------

class _Store:
    def __init__(self, state_dir: str, expected_uid: int, fs: FsOps):
        self.dir = os.path.abspath(state_dir)
        self.uid = expected_uid
        self.fs = fs

    def _open_dir(self) -> int:
        try:
            st = os.lstat(self.dir)
        except FileNotFoundError:
            raise UnsafeStorage("state directory missing")
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != self.uid or st.st_mode & 0o077:
            raise UnsafeStorage("state directory must be a real 0700 directory owned by the expected uid")
        return os.open(self.dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)

    def _check_file(self, fd: int) -> None:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != self.uid or st.st_mode & 0o077 or st.st_nlink != 1:
            raise UnsafeStorage("protected file has unsafe type/owner/mode/links")

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        dfd = self._open_dir()
        try:
            fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
        finally:
            os.close(dfd)
        try:
            self._check_file(fd)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def healthy(self) -> bool:
        dfd = self._open_dir()
        try:
            fd = os.open(OK_TOKEN, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dfd)
        except OSError:
            return False
        finally:
            os.close(dfd)
        try:
            self._check_file(fd)
            return True
        except UnsafeStorage:
            return False
        finally:
            os.close(fd)

    def sync_directory(self) -> None:
        dfd = self._open_dir()
        try:
            self.fs.fsync(dfd)
        finally:
            os.close(dfd)

    def invalidate_strict(self) -> None:
        """Remove the OK token and make its absence durable."""
        dfd = self._open_dir()
        try:
            with contextlib.suppress(FileNotFoundError):
                self.fs.unlink(OK_TOKEN, dfd)
            self.fs.fsync(dfd)
        finally:
            os.close(dfd)

    def set_healthy(self) -> None:
        self._write_file(OK_TOKEN, b"ok\n")

    def load(self) -> dict:
        dfd = self._open_dir()
        try:
            fd = os.open(STATE_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dfd)
        except FileNotFoundError:
            raise StateCorrupt("state not initialized")
        except OSError as exc:
            raise UnsafeStorage("cannot open state") from exc
        finally:
            os.close(dfd)
        try:
            self._check_file(fd)
            chunks, size = [], 0
            while True:
                b = os.read(fd, 65536)
                if not b:
                    break
                size += len(b)
                if size > 8 * 1024 * 1024:
                    raise StateCorrupt("state too large")
                chunks.append(b)
        finally:
            os.close(fd)
        wrapper = _strict_loads(b"".join(chunks))
        if not (isinstance(wrapper, dict) and set(wrapper) == {"sha256", "state"}):
            raise StateCorrupt("bad envelope")
        try:
            digest = hashlib.sha256(_canon(wrapper["state"])).hexdigest()
        except (ValueError, TypeError) as exc:
            raise StateCorrupt("uncanonicalizable state") from exc
        if digest != wrapper["sha256"]:
            raise StateCorrupt("checksum mismatch")
        validate_state(wrapper["state"])
        return wrapper["state"]

    def _write_file(self, name: str, body: bytes) -> None:
        tmp = ".tmp-%s" % uuid.uuid4().hex
        dfd = self._open_dir()
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
            try:
                self.fs.write(fd, body)
                self.fs.fsync(fd)
            finally:
                os.close(fd)
            try:
                self.fs.replace(tmp, name, dfd)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp, dir_fd=dfd)
                raise
            self.fs.fsync(dfd)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp, dir_fd=dfd)
            raise
        finally:
            os.close(dfd)

    def save(self, state: dict) -> None:
        validate_state(state)
        self._write_file(STATE_FILE, _canon({"sha256": hashlib.sha256(_canon(state)).hexdigest(), "state": state}))


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------

class PolicyEngine:
    # The broker hosts all granting/launching engines for an incarnation in one
    # process. Retain faults even if an individual engine is discarded.
    _faulted_ledgers: set[tuple[str, str]] = set()

    def __init__(self, state_dir: str, *, expected_uid: int = 0,
                 identities: Identities = Identities(),
                 caller_uid: Callable[[], int],
                 r0_pin: Optional[R0Pin] = None,
                 clock: Callable[[], float] = _default_boottime,
                 boot_id: Callable[[], str] = _default_boot_id,
                 kernel_release: Callable[[], str] = _default_kernel,
                 fs: Optional[FsOps] = None,
                 incarnation: str):
        # incarnation: random id generated ONCE per trusted broker lifetime and
        # shared by its owner/agent/recovery engines.  A new broker incarnation
        # invalidates every older grant (owner must re-authenticate and re-grant);
        # recovery is not grant-bound and stays possible.
        if not (type(incarnation) is str and _str(incarnation)):
            raise ValueError("trusted broker incarnation id required")
        self._inc = incarnation
        if identities.agent in (identities.owner, identities.recovery) or identities.agent == 0:
            raise ValueError("agent identity must differ from owner/recovery and root")
        self._store = _Store(state_dir, expected_uid, fs or FsOps())
        self._ids = identities
        self._caller = caller_uid
        self._pin = r0_pin
        self._clock_fn = clock
        self._boot = boot_id
        self._kernel = kernel_release
        self._fault_key = (os.path.realpath(self._store.dir), incarnation)

    # ---- internals ----------------------------------------------------
    def _clock(self) -> float:
        now = self._clock_fn()
        if not _num(now):
            raise Denied("invalid clock")
        return now

    def _require_caller(self, *allowed: int) -> None:
        if self._caller() not in allowed:
            raise Denied("caller identity not permitted for this interface")

    @property
    def _poisoned(self) -> bool:
        return self._fault_key in self._faulted_ledgers

    def _mark_fault(self) -> None:
        self._faulted_ledgers.add(self._fault_key)
        with contextlib.suppress(OSError, UnsafeStorage):
            self._store.invalidate_strict()

    def _write(self, st: dict) -> None:
        """Synchronize token removal, state replacement, then token publication."""
        restore_health = not self._poisoned and self._store.healthy()
        try:
            self._store.invalidate_strict()
        except (OSError, UnsafeStorage) as exc:
            self._faulted_ledgers.add(self._fault_key)
            raise LedgerWriteError("cannot durably pre-invalidate ledger; nothing written") from exc
        try:
            self._store.save(st)
            if restore_health:
                self._store.set_healthy()
        except (OSError, UnsafeStorage) as exc:
            self._mark_fault()
            raise LedgerWriteError("durable write failed; new actions denied") from exc

    def _enable_ledger(self) -> None:
        try:
            self._store.set_healthy()
        except (OSError, UnsafeStorage) as exc:
            self._mark_fault()
            raise LedgerWriteError("cannot durably enable ledger") from exc
        self._faulted_ledgers.discard(self._fault_key)

    def _receipt(self, st: dict, event: str, **fields) -> None:
        if len(st["receipts"]) >= MAX_RECEIPTS:
            self._mark_fault()
            raise LedgerWriteError("receipt capacity exhausted; owner archival required")
        st["seq"] += 1
        rec = {"seq": st["seq"], "event": event, "t_boot": round(self._clock(), 3), "boot_id": self._boot()}
        rec.update(fields)
        st["receipts"].append(rec)

    def _blocked(self, st: dict) -> Optional[str]:
        if self._poisoned or not self._store.healthy():
            return "ledger_fault"
        if st["r0_marker"] is not None:
            return "r0_recovery_pending"
        # Capacity gates only NEW admissions/grants: an in-flight op (active) may
        # still commit/finish/recover using the RESERVED_RECEIPTS headroom.
        if st["active"] is None and len(st["receipts"]) >= MAX_RECEIPTS - RESERVED_RECEIPTS:
            return "ledger_capacity"
        return None

    def _reap_uncommitted(self, st: dict, now: float, boot: str) -> bool:
        """Only admitted-but-never-committed ops are closed automatically: commit
        is refused after COMMIT_WINDOW or on another boot, so no effect ran.
        Committed ops require a result or owner reconciliation."""
        a = st["active"]
        if a is None or a["phase"] != "admitted":
            return False
        if a["boot_id"] == boot and now <= a["admitted_at"] + COMMIT_WINDOW:
            return False
        st["active"] = None
        self._receipt(st, "closed", op_id=a["op_id"], action=a["action"], outcome="abandoned_uncommitted")
        return True

    def _lease_problem(self, g: Optional[dict], boot: str, now: float, reserve: int) -> Optional[str]:
        if g is None:
            return "no_grant"
        if g["boot_id"] != boot:
            return "stale_boot"
        if g["incarnation"] != self._inc:
            return "stale_incarnation"
        if g["revoked"]:
            return "revoked"
        if now >= g["expires_at"]:
            return "expired"
        if now + reserve > g["expires_at"]:
            return "insufficient_time"
        return None

    @staticmethod
    def _matches(ticket, a: Optional[dict]) -> bool:
        return (type(ticket) is Ticket and a is not None
                and ticket.op_id == a["op_id"] and ticket.action == a["action"]
                and ticket.grant_id == a["grant_id"] and ticket.boot_id == a["boot_id"]
                and type(ticket.admitted_at) is type(a["admitted_at"]) and ticket.admitted_at == a["admitted_at"]
                and ticket.digest == a["digest"] == _ticket_digest(a))

    # ---- agent-facing --------------------------------------------------
    def admit(self, request) -> Ticket:
        self._require_caller(self._ids.agent)
        if not (type(request) is dict and set(request) == {"action"}
                and type(request["action"]) is str and request["action"] in CATALOG):
            raise Denied("malformed request: exactly {'action': <catalog name>} allowed")
        action = request["action"]
        with self._store.locked():
            st = self._store.load()
            now, boot = self._clock(), self._boot()
            reaped = self._reap_uncommitted(st, now, boot)
            reason = self._blocked(st)
            if reason is None and st["active"] is not None:
                reason = "operation_active" if st["active"]["boot_id"] == boot else "owner_reconciliation_required"
            g = st["grant"]
            if reason is None:
                reason = self._lease_problem(g, boot, now, CATALOG[action]["reserve"])
            if reason is None and g["uses"][action] <= 0:
                reason = "uses_exhausted"
            if reason is None and action == "iris-r0" and (self._pin is None or self._kernel() != self._pin.kernel_release):
                reason = "r0_pin_mismatch"
            if reason is not None:
                if reaped and reason != "ledger_fault":
                    self._write(st)
                raise Denied(reason)
            op = {"op_id": uuid.uuid4().hex, "action": action, "grant_id": g["grant_id"],
                  "boot_id": boot, "admitted_at": now}
            op["digest"] = _ticket_digest(op)
            op.update(phase="admitted", committed_at=None)
            g["uses"][action] -= 1
            st["active"] = op
            self._receipt(st, "admit", op_id=op["op_id"], action=action, grant_id=g["grant_id"])
            self._write(st)
            return Ticket(op["op_id"], action, op["grant_id"], boot, now, op["digest"])

    @contextlib.contextmanager
    def commit(self, ticket: Ticket) -> Iterator[CommittedOp]:
        """Commit point.  Holds the shared lock across the caller's launch.
        iris-r0: commit receipt + recovery marker in ONE atomic replace."""
        self._require_caller(self._ids.agent)
        with self._store.locked():
            st = self._store.load()
            now, boot = self._clock(), self._boot()
            a = st["active"]
            if not self._matches(ticket, a):
                raise Denied("ticket does not match the active operation")
            if a["phase"] != "admitted":
                raise Denied("ticket already committed; no replay")
            reason = self._blocked(st)
            if reason is None and now > a["admitted_at"] + COMMIT_WINDOW:
                reason = "commit_window_elapsed"
            if reason is None:
                reason = self._lease_problem(st["grant"], boot, now, CATALOG[a["action"]]["reserve"])
            if reason is None and a["boot_id"] != boot:
                reason = "stale_boot"
            if reason is None and a["action"] == "iris-r0" and (self._pin is None or self._kernel() != self._pin.kernel_release):
                reason = "r0_pin_mismatch"
            if reason is not None:
                if reason != "ledger_fault":
                    st["active"] = None
                    self._receipt(st, "closed", op_id=a["op_id"], action=a["action"], outcome="denied_at_commit:" + reason)
                    self._write(st)
                raise Denied(reason)
            a["phase"], a["committed_at"] = "committed", now
            self._receipt(st, "commit", op_id=a["op_id"], action=a["action"])
            if a["action"] == "iris-r0":
                st["r0_marker"] = {"op_id": a["op_id"], "grant_id": a["grant_id"], "boot_id": boot,
                                   "committed_at": now, "kernel_release": self._pin.kernel_release,
                                   "module_sha256": self._pin.module_sha256, "srcversion": self._pin.srcversion}
            self._write(st)
            # Re-validate after the fsync, immediately before handing control to
            # the launcher (the fsync itself may have consumed the reserve).
            later = self._clock()
            late = self._lease_problem(st["grant"], self._boot(), later, CATALOG[a["action"]]["reserve"])
            if late is not None:
                # No launch.  Use stays consumed.  An R0 marker already persisted is
                # kept: the module was not unloaded, but only verified evidence or
                # owner reconciliation may clear it.
                st["active"] = None
                self._receipt(st, "closed", op_id=a["op_id"], action=a["action"],
                              outcome="not_launched_after_commit:" + late)
                self._write(st)
                raise Denied("lease no longer valid after commit: " + late)
            commit_thread = threading.current_thread()
            in_scope = True

            def check_launch() -> bool:
                if not in_scope or threading.current_thread() is not commit_thread:
                    raise Denied("launch check outside commit scope")
                self._require_caller(self._ids.agent)
                if self._poisoned or not self._store.healthy():
                    raise Denied("ledger_fault")
                current = self._store.load()
                active = current["active"]
                if not self._matches(ticket, active) or active["phase"] != "committed":
                    raise Denied("ticket does not match the committed operation")
                boot = self._boot()
                if active["boot_id"] != boot:
                    raise Denied("stale_boot")
                if active["action"] == "iris-r0" and self._kernel() != self._pin.kernel_release:
                    raise Denied("r0_pin_mismatch")
                reason = self._lease_problem(current["grant"], boot, self._clock(),
                                             CATALOG[active["action"]]["reserve"])
                if reason is not None:
                    raise Denied(reason)
                return True

            try:
                yield CommittedOp(a["op_id"], a["action"], check_launch)
            finally:
                in_scope = False

    def finish(self, ticket: Ticket, result: str, audit_evidence: Optional[dict] = None) -> None:
        """Record the executor result.  Never refunds; never clears the R0 marker.

        * "pass" only for a COMMITTED audit/thermal operation.
        * iris-r0 accepts only "fail"/"aborted" here; its final outcome is
          written atomically by clear_recovery / reconcile_marker.
        * audit "pass" requires bounded audit evidence (see _check_audit_evidence).
        """
        self._require_caller(self._ids.agent)
        if type(result) is not str or result not in RESULTS:
            raise Denied("malformed result")
        with self._store.locked():
            st = self._store.load()
            a = st["active"]
            if not self._matches(ticket, a):
                raise Denied("ticket does not match the active operation")
            if result == "pass" and (a["phase"] != "committed" or a["action"] == "iris-r0"):
                raise Denied("pass only for committed audit/thermal; R0 outcome is set by recovery")
            fields = {}
            if a["action"] == "audit" and result == "pass":
                fields = _check_audit_evidence(audit_evidence)
            elif audit_evidence is not None:
                raise Denied("audit evidence only accepted for audit pass")
            st["active"] = None
            self._receipt(st, "result", op_id=a["op_id"], action=a["action"], phase=a["phase"],
                          result=result, **fields)
            self._write(st)

    def lease_valid(self, ticket: Ticket) -> bool:
        """Lock-free poll for the thermal supervisor (target every 250 ms).
        Any error, fault, revocation, expiry or mismatch => False (stop)."""
        try:
            if self._poisoned or not self._store.healthy():
                return False
            st = self._store.load()
            a = st["active"]
            if not self._matches(ticket, a) or a["phase"] != "committed":
                return False
            g = st["grant"]
            boot = self._boot()
            return (a["boot_id"] == boot and g["grant_id"] == a["grant_id"]
                    and self._lease_problem(g, boot, self._clock(), 0) is None)
        except Exception:  # noqa: BLE001 - fail closed on anything
            return False

    def status(self) -> dict:
        """Sanitized status: no paths, uids, grant ids or receipt bodies."""
        try:
            st = self._store.load()
            now, boot = self._clock(), self._boot()
        except Exception:  # noqa: BLE001
            return {"state": "unavailable", "new_actions": "denied", "recovery_required": "unknown",
                    "ledger_seq": None, "last_operation": None}
        g = st["grant"]
        lease = self._lease_problem(g, boot, now, 0)
        m = st["r0_marker"]
        try:
            blocked = self._blocked(st)
        except Exception:  # noqa: BLE001
            blocked = "ledger_fault"
        a = st["active"]
        last = self._last_op(st["receipts"])
        if blocked is None and a is not None:
            blocked = "operation_active" if a["boot_id"] == boot else "owner_reconciliation_required"
        return {
            "state": "ok",
            "new_actions": "denied" if (blocked or lease) else "allowed",
            "reason": blocked or lease,
            "remaining_seconds": int(g["expires_at"] - now) if lease is None else 0,
            "uses_left": dict(g["uses"]) if lease is None else {k: 0 for k in CATALOG},
            "active": None if a is None else {"op_id": a["op_id"], "action": a["action"], "phase": a["phase"]},
            "ledger_seq": st["seq"],
            "last_operation": last,
            "recovery_required": m is not None,
            "reconciliation_required": m is not None and m["boot_id"] != boot,
        }

    @staticmethod
    def _last_op(receipts) -> Optional[dict]:
        """Most recent operation receipt (sanitized), surviving owner archival
        via the summary carried in the 'archived' receipt."""
        for rec in reversed(receipts):
            if rec["event"] == "archived":
                return rec.get("last_operation")
            if "op_id" in rec and rec["event"] in _EVENT_PHASE:
                return {"seq": rec["seq"], "op_id": rec["op_id"], "action": rec.get("action"),
                        "event": rec["event"], "phase": _EVENT_PHASE[rec["event"]],
                        "outcome": rec.get("result") or rec.get("final") or rec.get("outcome")}
        return None

    # ---- recovery-manager-facing ---------------------------------------
    def pending_recovery(self) -> dict:
        """Readable even when writes fail.  Corrupt/unreadable => 'unknown':
        never auto-load; owner reconciliation required."""
        try:
            st = self._store.load()
        except Exception:  # noqa: BLE001
            return {"state": "unknown", "action": "owner_reconciliation"}
        m = st["r0_marker"]
        if m is None:
            return {"state": "none"}
        same = m["boot_id"] == self._boot() and m["kernel_release"] == self._kernel()
        out = dict(m)
        out["state"] = "restore_same_boot" if same else "reconcile_required"
        return out

    def clear_recovery(self, evidence: dict, unload_result: str) -> str:
        """Trusted recovery executor clears the marker after a verified restore
        and records the FINAL R0 outcome in the same atomic write.

        unload_result: "pass" if the R0 unload/test phase succeeded, "fail"
        otherwise.  Final outcome is "pass" only if unload_result == "pass" AND
        no fail/aborted result was recorded for the op; a verified restore after
        a failed unload is "fail".  Bad evidence => Denied, marker kept."""
        self._require_caller(self._ids.recovery)
        if type(unload_result) is not str or unload_result not in ("pass", "fail"):
            raise Denied("malformed unload_result")
        with self._store.locked():
            st = self._store.load()
            m = st["r0_marker"]
            if m is None:
                raise Denied("no recovery marker")
            if m["boot_id"] != self._boot():
                raise Denied("boot changed: owner reconciliation required")
            _check_evidence(evidence, m, self._boot(), self._kernel())
            final = "pass" if unload_result == "pass" and not self._r0_failed(st, m) else "fail"
            self._clear_marker(st, m, "recovery_cleared", evidence, final)
            return final

    @staticmethod
    def _r0_failed(st, m) -> bool:
        a = st["active"]
        if a is not None and a["op_id"] == m["op_id"] and a["phase"] != "committed":
            return True
        return any(r.get("op_id") == m["op_id"] and (r["event"] == "result" or r["event"] == "closed")
                   for r in st["receipts"])

    def _clear_marker(self, st, m, event, ev, final) -> None:
        st["r0_marker"] = None
        if st["active"] is not None and st["active"]["op_id"] == m["op_id"]:
            st["active"] = None
        self._receipt(st, event, op_id=m["op_id"], action="iris-r0", final=final,
                      module_sha256=ev["module_sha256"], srcversion=ev["module_srcversion"],
                      cpu_frames=ev["cpu_smoke_frames"], iris_frames=ev["iris_smoke_frames"])
        self._write(st)


_EVENT_PHASE = {"admit": "admitted", "commit": "committed", "result": "finished", "closed": "closed",
                "recovery_cleared": "recovered", "recovery_reconciled": "reconciled", "owner_closed": "closed"}
_AUDIT_KEYS = {"report_sha256", "report_bytes", "findings"}


def _check_audit_evidence(ev) -> dict:
    """Bounded, fixed-shape audit evidence (no free-form map is stored).

    Technical limitation: the engine cannot itself prove these values came from
    the root audit unit; the trusted broker must take them from the executor's
    root-owned output, never from client data."""
    if not (type(ev) is dict and set(ev) == _AUDIT_KEYS):
        raise Denied("audit pass requires exactly report_sha256/report_bytes/findings")
    if not (type(ev["report_sha256"]) is str and _HEX64.match(ev["report_sha256"])
            and type(ev["report_bytes"]) is int and 0 < ev["report_bytes"] <= AUDIT_MAX_BYTES
            and type(ev["findings"]) is int and 0 <= ev["findings"] <= AUDIT_MAX_FINDINGS):
        raise Denied("audit evidence out of bounds")
    return {"report_sha256": ev["report_sha256"], "report_bytes": ev["report_bytes"], "findings": ev["findings"]}


_EVIDENCE_KEYS = {"op_id", "boot_id", "kernel_release", "module_sha256", "module_srcversion",
                  "stock_module_verified", "devices_present", "cpu_smoke_frames", "cpu_smoke_pass",
                  "iris_smoke_frames", "iris_smoke_pass"}


def _check_evidence(ev, marker: dict, boot: str, kernel: str) -> None:
    if not (type(ev) is dict and set(ev) == _EVIDENCE_KEYS):
        raise Denied("malformed recovery evidence")
    ok = (ev["op_id"] == marker["op_id"]
          and ev["boot_id"] == boot
          and ev["kernel_release"] == kernel == marker["kernel_release"]
          and ev["module_sha256"] == marker["module_sha256"] == STOCK_IRIS_SHA256
          and ev["module_srcversion"] == marker["srcversion"]
          and ev["stock_module_verified"] is True and ev["devices_present"] is True
          and type(ev["cpu_smoke_frames"]) is int and ev["cpu_smoke_frames"] == SMOKE_FRAMES
          and type(ev["iris_smoke_frames"]) is int and ev["iris_smoke_frames"] == SMOKE_FRAMES
          and ev["cpu_smoke_pass"] is True and ev["iris_smoke_pass"] is True)
    if not ok:
        raise Denied("recovery not verified; marker kept")


class OwnerControl:
    """Owner-only interface.  Never exposed to the agent adapter."""

    def __init__(self, engine: PolicyEngine):
        self._e = engine

    def _enter(self):
        self._e._require_caller(self._e._ids.owner)
        return self._e._store.locked()

    def initialize(self) -> None:
        """Create the authoritative state once (refuses to overwrite)."""
        e = self._e
        with self._enter():
            dfd = e._store._open_dir()
            try:
                exists = os.path.lexists(os.path.join(e._store.dir, STATE_FILE))
            finally:
                os.close(dfd)
            if exists:
                raise Denied("state already initialized")
            e._write(_empty_state())
            e._enable_ledger()

    def grant(self) -> dict:
        e = self._e
        with self._enter():
            st = e._store.load()
            now, boot = e._clock(), e._boot()
            e._reap_uncommitted(st, now, boot)
            reason = e._blocked(st)
            if reason is None and st["active"] is not None:
                reason = "operation_active"
            if reason is not None:
                raise Denied(reason)
            issued = math.floor(now)
            g = {"grant_id": uuid.uuid4().hex, "boot_id": boot, "incarnation": e._inc,
                 "issued_at": issued, "expires_at": issued + GRANT_SECONDS, "uses": {k: v["uses"] for k, v in CATALOG.items()},
                 "revoked": False}
            st["grant"] = g
            e._receipt(st, "grant", grant_id=g["grant_id"])
            e._write(st)
            return {"seconds": GRANT_SECONDS, "uses": dict(g["uses"])}

    def revoke(self) -> dict:
        """Ack is returned only after the revocation is durable under the commit
        lock; recovery of an already-committed R0 is unaffected."""
        e = self._e
        with self._enter():
            st = e._store.load()
            g = st["grant"]
            if g is not None and not g["revoked"]:
                g["revoked"] = True
                e._receipt(st, "revoke", grant_id=g["grant_id"])
                e._write(st)
            elif g is not None:
                # A prior replace may be visible after a failed directory fsync.
                try:
                    e._store.sync_directory()
                except (OSError, UnsafeStorage) as exc:
                    e._mark_fault()
                    raise LedgerWriteError("cannot confirm durable revocation") from exc
            a = st["active"]
            return {"revoked": True,
                    "committed_in_flight": None if a is None or a["phase"] != "committed" else a["action"],
                    "recovery_pending": st["r0_marker"] is not None}

    def reconcile_marker(self, evidence: dict) -> None:
        """After boot change / not-launched R0: owner supplies verified evidence
        from the CURRENT boot.  Nothing is loaded automatically."""
        e = self._e
        with self._enter():
            st = e._store.load()
            m = st["r0_marker"]
            if m is None:
                raise Denied("no recovery marker")
            _check_evidence(evidence, m, e._boot(), e._kernel())
            e._clear_marker(st, m, "recovery_reconciled", evidence, "fail")  # never PASS by reconciliation

    def close_unknown_operation(self, op_id: str, outcome: str) -> None:
        """Close a committed audit/thermal op whose result was never recorded,
        after the owner verified the unit ended.  No replay, no refund."""
        e = self._e
        if outcome not in ("verified_ended", "verified_failed"):
            raise Denied("malformed outcome")
        with self._enter():
            st = e._store.load()
            a = st["active"]
            if a is None or a["op_id"] != op_id or a["phase"] != "committed" or a["action"] == "iris-r0":
                raise Denied("no matching committed non-R0 operation")
            st["active"] = None
            e._receipt(st, "owner_closed", op_id=op_id, action=a["action"], outcome=outcome)
            e._write(st)

    def archive_receipts(self) -> dict:
        """Move receipts to a durable root-owned archive file, then reference its
        SHA-256 in the state.  No receipt is ever dropped silently."""
        e = self._e
        with self._enter():
            st = e._store.load()
            if st["active"] is not None or st["r0_marker"] is not None:
                raise Denied("archive only when no operation or recovery is pending")
            body = _canon({"schema": SCHEMA, "receipts": st["receipts"]})
            sha = hashlib.sha256(body).hexdigest()
            name = "%s%d.json" % (ARCHIVE_PREFIX, st["seq"])
            try:
                e._store._write_file(name, body)
            except OSError as exc:
                raise LedgerWriteError("archive write failed; receipts kept") from exc
            count = len(st["receipts"])
            last = e._last_op(st["receipts"])
            first_seq = st["receipts"][0]["seq"] if st["receipts"] else None
            st["receipts"] = []
            e._receipt(st, "archived", file=name, sha256=sha, count=count,
                       first_seq=first_seq, last_operation=last)
            e._write(st)
            return {"file": name, "sha256": sha, "count": count}

    def clear_ledger_fault(self) -> None:
        """Owner re-enables after inspecting the state (must load cleanly)."""
        e = self._e
        with self._enter():
            e._store.load()
            e._enable_ledger()
