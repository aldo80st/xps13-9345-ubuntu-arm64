"""XPS AUTHZ v1.1 (M2-B) - fixed-catalog action executor and R0 recovery.

LAB-ONLY COMPONENT.  Not production-validated; not an authorisation to
install or activate anything.  Scope: ADR-001 / contract revision 2,
components ``action-executor`` and ``recovery-manager``.

Single authority: the M2A policy engine owns consumption, the common flock,
commit receipts, the R0 recovery marker (created internally by ``commit``),
result receipts and recovery clearing.  This module never writes markers or
receipts.  Consumed M2A surface (exact)::

    ticket = engine.admit({"action": action})          # durable consumption
    with engine.commit(ticket) as committed:           # common flock held;
        ...preflight...                                # lease revalidated after fsync
        committed.check_launch()                       # guard under held flock (M2A)
        ...launch (unload / spawn)...                  # no nested engine.lease_valid()
    engine.lease_valid(ticket) -> bool                 # ORIGINAL ticket; after commit,
                                                       # outside the commit block
    engine.finish(ticket, "pass"|"fail"|"aborted", audit_evidence=None)
        # audit_evidence only on audit pass:
        # {"report_sha256", "report_bytes", "findings"}
    recovery_engine.pending_recovery() -> flat dict
        {"state": "none"|"restore_same_boot"|"reconcile_required"|"unknown",
         "op_id", "grant_id", "boot_id", "kernel_release", "module_sha256",
         "srcversion", "committed_at"}        # marker fields at top level
    recovery_engine.clear_recovery(evidence, unload_result) -> "pass"|"fail"
        # evidence keys exactly RECOVERY_EVIDENCE_KEYS; terminal for R0

``recovery_engine`` is a dedicated engine instance bound to the trusted
recovery identity over the same protected state; requests cannot select it.

Lock order (no nesting inside the engine): ``RecoveryLock`` (R0 worker /
recovery supervisor exclusion) -> engine flock (taken by the engine).  The
executor makes no engine call inside the ``commit`` block.

Deliberately *inert*: no privileged CLI, no ``__main__``, no subprocess, no
shell, no environment inheritance, no file-system access.  Every effect goes
through injected abstract adapters (real ones belong to M3-M5).  The client
supplies only an action id.  Uncertain state => no new effect and no PASS.
"""
from __future__ import annotations

import abc
import dataclasses
import enum
import hashlib
import json
import math
import re
from typing import Any, Callable, ContextManager, Mapping, Optional, Sequence

# ---------------------------------------------------------------------------
# Fixed catalog (contract revision 2).  Changing any value requires review.
# ---------------------------------------------------------------------------

ACTION_AUDIT = "audit"
ACTION_IRIS_R0 = "iris-r0"
ACTION_THERMAL = "thermal"
CATALOG = (ACTION_AUDIT, ACTION_IRIS_R0, ACTION_THERMAL)

IRIS_KERNEL_RELEASE = "7.3.0-11-generic"
IRIS_MODULE_NAME = "qcom_iris"
IRIS_OFFICIAL_SHA256 = "2183021a89244ad917b3afcbe24f2515c5d671033082f783c22ab817e6c6236b"
IRIS_OFFICIAL_SRCVERSION = "575ECCB0F64EE1485C4E2FE"
SMOKE_FRAMES = 120

THERMAL_DURATION_S = 10.0
THERMAL_DUTY = 0.25
THERMAL_WORKERS = 1
THERMAL_SAMPLE_S = 0.25
THERMAL_START_MAX_C = 55.0      # start requires max SoC < 55 C
THERMAL_ABORT_C = 65.0          # abort when max SoC >= 65 C
BATTERY_ABORT_C = 40.0          # deny/abort when battery >= 40 C
BATTERY_MIN_PCT = 30.0          # require battery >= 30 %
THERMAL_STOP_TARGET_S = 2.0     # verified stop target (not real-time)
THERMAL_WATCHDOG_MAX_S = 12.0   # independent worker lifetime bound
SOC_SENSOR_COUNT = 58           # exact non-battery thermal sensor count (XPS schema)

R0_RECOVERY_BUDGET_S = 180.0

# One fixed systemd unit per action; never derived from request data.  The
# thermal unit must carry RuntimeMaxSec<=12 configured at install time so the
# watchdog is armed atomically with the spawn and survives controller death.
UNIT_CATALOG: Mapping[str, str] = {
    ACTION_AUDIT: "xps-authz-audit.service",
    ACTION_IRIS_R0: "xps-authz-iris-r0.service",
    ACTION_THERMAL: "xps-authz-thermal-worker.service",
}
RECOVERY_UNIT = "xps-authz-iris-recovery.service"

CLEAN_ENVIRONMENT: Mapping[str, str] = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}

STATE_NONE = "none"
STATE_RESTORE = "restore_same_boot"
STATE_RECONCILE = "reconcile_required"
STATE_UNKNOWN = "unknown"
RECOVERY_STATES = (STATE_NONE, STATE_RESTORE, STATE_RECONCILE, STATE_UNKNOWN)
MARKER_FIELDS = ("op_id", "grant_id", "boot_id", "kernel_release",
                 "module_sha256", "srcversion", "committed_at")
RECOVERY_EVIDENCE_KEYS = (
    "op_id", "boot_id", "kernel_release", "module_sha256", "module_srcversion",
    "stock_module_verified", "devices_present", "cpu_smoke_frames", "cpu_smoke_pass",
    "iris_smoke_frames", "iris_smoke_pass",
)
AUDIT_EVIDENCE_KEYS = ("report_sha256", "report_bytes", "findings")
# B-side bounds are deliberately STRICTER than M2A's (16 MiB / 10000), not
# equal: any evidence B emits is accepted by M2A; the converse does not hold.
AUDIT_MAX_BYTES = 16 * 1024
AUDIT_MAX_FINDINGS = 64
AUDIT_MAX_HOLDERS = 16

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BOOT_ID_RE = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$")

AUDIT_REQUIRED_KEYS = (
    "kernel_release", "module_loaded", "module_srcversion",
    "module_refcnt", "module_holders", "module_file_sha256",
)
AUDIT_ALLOWED_KEYS = AUDIT_REQUIRED_KEYS + (
    "module_name", "module_matches_official", "power_external", "battery_pct",
    "battery_temp_c", "soc_max_temp_c", "cap_sys_module", "missing",
)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

class Outcome(str, enum.Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    DENIED = "DENIED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"
    BLOCKED_ACTIVE = "BLOCKED_ACTIVE"          # committed op left active on purpose
    RECOVERY_PENDING = "RECOVERY_PENDING"
    BOOT_CHANGED_BLOCKED = "BOOT_CHANGED_BLOCKED"


def engine_result(outcome: Outcome) -> str:
    if outcome is Outcome.PASS:
        return "pass"
    if outcome is Outcome.ABORTED:
        return "aborted"
    return "fail"


class ActionDenied(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclasses.dataclass(frozen=True)
class ActionResult:
    action: str
    op_id: str
    outcome: Outcome
    reason: str
    details: Mapping[str, object] = dataclasses.field(default_factory=dict)


def parse_request(raw: object) -> str:
    """Only ``{"action": <catalog id>}`` is accepted.  Returns the action."""
    if not isinstance(raw, Mapping) or set(raw.keys()) != {"action"}:
        raise ActionDenied("request-shape-invalid")
    action = raw["action"]
    if not isinstance(action, str) or action not in CATALOG:
        raise ActionDenied("action-not-in-catalog")
    return action


# ---------------------------------------------------------------------------
# M2A policy-engine API (single authority, one common lock).
# ---------------------------------------------------------------------------

class PolicyEngine(abc.ABC):
    """Exact M2A surface; see module docstring.  ``Ticket``/``CommittedOp``
    are M2A types, read only through ``op_id`` and ``action``."""

    @abc.abstractmethod
    def admit(self, request: Mapping[str, str]) -> Any: ...

    @abc.abstractmethod
    def commit(self, ticket: Any) -> ContextManager[Any]: ...

    @abc.abstractmethod
    def lease_valid(self, ticket: Any) -> bool: ...

    @abc.abstractmethod
    def finish(self, ticket: Any, result: str,
               audit_evidence: Optional[Mapping[str, object]] = None) -> None: ...

    @abc.abstractmethod
    def pending_recovery(self) -> Mapping[str, object]: ...

    @abc.abstractmethod
    def clear_recovery(self, evidence: Mapping[str, object], unload_result: str) -> str: ...


class RecoveryLock(abc.ABC):
    """Exclusive gate between an in-flight R0 worker and the recovery
    supervisor (future root-owned lock; lab fake only).  Taken before any
    engine call (lock order: RecoveryLock -> engine flock)."""

    @abc.abstractmethod
    def hold(self) -> ContextManager[None]: ...


@dataclasses.dataclass(frozen=True)
class RecoveryMarker:
    op_id: str
    grant_id: str
    boot_id: str
    kernel_release: str
    module_sha256: str
    srcversion: str
    committed_at: object


def marker_from_trusted(raw: Mapping[str, object]) -> Optional[RecoveryMarker]:
    """Strict adaptation of the flat engine record: exact pinned constants."""
    if any(k not in raw for k in MARKER_FIELDS):
        return None
    for key in MARKER_FIELDS[:-1]:
        if not isinstance(raw[key], str) or not raw[key]:
            return None
    committed_at = raw["committed_at"]
    if committed_at is None or isinstance(committed_at, bool) or \
            not isinstance(committed_at, (str, int, float)):
        return None
    if isinstance(committed_at, str) and not committed_at.strip():
        return None
    if isinstance(committed_at, float) and not math.isfinite(committed_at):
        return None
    mk = RecoveryMarker(**{k: raw[k] for k in MARKER_FIELDS})
    if (mk.kernel_release != IRIS_KERNEL_RELEASE
            or mk.module_sha256 != IRIS_OFFICIAL_SHA256
            or mk.srcversion != IRIS_OFFICIAL_SRCVERSION
            or not _BOOT_ID_RE.fullmatch(mk.boot_id)):
        return None
    return mk


def read_recovery_state(engine: PolicyEngine) -> tuple[str, Optional[RecoveryMarker]]:
    """Flat record.  Exception, unknown state or invalid marker -> unknown."""
    try:
        raw = engine.pending_recovery()
    except Exception:
        return STATE_UNKNOWN, None
    if not isinstance(raw, Mapping):
        return STATE_UNKNOWN, None
    state = raw.get("state")
    if state not in RECOVERY_STATES:
        return STATE_UNKNOWN, None
    if state == STATE_RESTORE:
        mk = marker_from_trusted(raw)
        return (STATE_RESTORE, mk) if mk is not None else (STATE_UNKNOWN, None)
    return state, None


def recovery_evidence(marker: RecoveryMarker) -> dict:
    """Exact clear_recovery evidence, built only after every check passed."""
    return {
        "op_id": marker.op_id,
        "boot_id": marker.boot_id,
        "kernel_release": IRIS_KERNEL_RELEASE,
        "module_sha256": IRIS_OFFICIAL_SHA256,
        "module_srcversion": IRIS_OFFICIAL_SRCVERSION,
        "stock_module_verified": True,
        "devices_present": True,
        "cpu_smoke_frames": SMOKE_FRAMES,
        "cpu_smoke_pass": True,
        "iris_smoke_frames": SMOKE_FRAMES,
        "iris_smoke_pass": True,
    }


def canonical_report_bytes(report: Mapping[str, object]) -> bytes:
    return json.dumps(report, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def audit_findings(report: Mapping[str, object]) -> int:
    """Count of non-nominal observations in the sanitised report."""
    n = len(report.get("missing") or [])
    for key in ("module_matches_official", "module_loaded", "power_external"):
        if report.get(key) is not True:
            n += 1
    if report.get("soc_max_temp_c") is None:
        n += 1
    return n


def audit_evidence(report: Mapping[str, object]) -> Optional[dict]:
    """{report_sha256, report_bytes, findings} over the canonical trusted
    report; None if not representable within bounds."""
    try:
        data = canonical_report_bytes(report)
    except (TypeError, ValueError):
        return None
    findings = audit_findings(report)
    if not (1 <= len(data) <= AUDIT_MAX_BYTES) or not (0 <= findings <= AUDIT_MAX_FINDINGS):
        return None
    return {"report_sha256": hashlib.sha256(data).hexdigest(),
            "report_bytes": len(data), "findings": findings}


def _ticket_ok(ticket: object, action: str) -> bool:
    op = getattr(ticket, "op_id", None)
    return getattr(ticket, "action", None) == action and isinstance(op, str) and bool(op)


def _launch_guard_ok(committed: Any) -> tuple[bool, Optional[str]]:
    """Recheck lease/validity under the already-held commit flock immediately
    before unload/spawn/capture without nesting ``engine.lease_valid``.
    Requires exact ``True``; fails closed if absent, erroring, or non-True."""
    guard = getattr(committed, "check_launch", None)
    if not callable(guard):
        return False, "launch-guard-unavailable"
    ok, valid = _safe(guard)
    if not ok:
        return False, f"launch-guard-error:{valid}"
    if valid is True:
        return True, None
    if valid is False:
        return False, "lease-expired-before-launch"
    return False, "launch-guard-invalid-return"


# ---------------------------------------------------------------------------
# Read-only host inspection adapter (no CAP_SYS_MODULE, no load syscalls).
# Runs inside the fixed audit/executor units, never in the client.
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class ModuleState:
    loaded: bool
    srcversion: Optional[str]
    refcnt: Optional[int]
    holders: Sequence[str]


@dataclasses.dataclass(frozen=True)
class DeviceUsers:
    visible: bool          # False => could not observe all processes => deny
    pids: Sequence[int]


@dataclasses.dataclass(frozen=True)
class PowerState:
    external: Optional[bool]
    battery_pct: Optional[float]
    battery_temp_c: Optional[float]


class HostInspector(abc.ABC):
    @abc.abstractmethod
    def boot_id(self) -> str: ...

    @abc.abstractmethod
    def kernel_release(self) -> str: ...

    @abc.abstractmethod
    def module_state(self) -> ModuleState:
        """State of the pinned module; raise if unknown."""

    @abc.abstractmethod
    def official_module_sha256(self) -> str:
        """SHA-256 of the pinned module file for the pinned kernel (read-only)."""

    @abc.abstractmethod
    def iris_devices_present(self) -> bool: ...

    @abc.abstractmethod
    def device_users(self) -> DeviceUsers: ...

    @abc.abstractmethod
    def power_state(self) -> PowerState: ...

    @abc.abstractmethod
    def soc_temps_c(self) -> Sequence[float]:
        """Exact ``SOC_SENSOR_COUNT`` (58) non-battery SoC thermal sensors; real
        adapters enforce pinned sensor identity names; max is enforced."""

    @abc.abstractmethod
    def has_cap_sys_module(self) -> bool:
        """Effective capability of the audit process.  Must be False."""


# ---------------------------------------------------------------------------
# Trusted effect adapters (fixed operations only; no generic executor).
# ---------------------------------------------------------------------------

class IrisModuleControl(abc.ABC):
    """Fixed root-owned operations on the pinned official module only; no
    name/path/force parameter; clean environment; no shell."""

    @abc.abstractmethod
    def unload_official(self) -> bool: ...

    @abc.abstractmethod
    def load_official(self) -> bool: ...


class SmokeRunner(abc.ABC):
    """Trusted unprivileged smoke tests with fixed frame count."""

    @abc.abstractmethod
    def cpu_decode(self, frames: int) -> bool: ...

    @abc.abstractmethod
    def iris_decode(self, frames: int) -> bool: ...


class ThermalHandle(abc.ABC):
    @abc.abstractmethod
    def alive(self) -> bool: ...

    @abc.abstractmethod
    def stop(self) -> None: ...

    @abc.abstractmethod
    def watchdog_max_s(self) -> Optional[float]:
        """Lifetime bound enforced independently since spawn (the fixed
        unit's RuntimeMaxSec).  None if not confirmed.  There is no disarm."""


class ThermalLauncher(abc.ABC):
    """Spawns the unprivileged worker in its fixed unit; the independent
    watchdog is part of the unit (armed atomically with the spawn)."""

    @abc.abstractmethod
    def watchdog_ready(self) -> Optional[float]:
        """Read-only: RuntimeMaxSec configured on the fixed worker unit, from
        the root-owned installed unit (before any spawn).  None if unknown."""

    @abc.abstractmethod
    def start(self, duration_s: float, duty: float, workers: int) -> ThermalHandle: ...

    @abc.abstractmethod
    def stop_orphans(self) -> bool:
        """Stop any worker of the fixed unit; True only when none remain."""


class Clock(abc.ABC):
    @abc.abstractmethod
    def monotonic(self) -> float: ...

    @abc.abstractmethod
    def sleep(self, seconds: float) -> None: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finite(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _safe(fn: Callable[[], object]) -> tuple[bool, object]:
    try:
        return True, fn()
    except Exception as exc:
        return False, type(exc).__name__


def soc_max(temps: object) -> Optional[float]:
    """Max of all ``SOC_SENSOR_COUNT`` (58) required non-battery thermal
    sensors; any missing, extra, or invalid reading => None."""
    if isinstance(temps, (str, bytes)) or not isinstance(temps, Sequence) \
            or len(temps) != SOC_SENSOR_COUNT:
        return None
    vals = []
    for t in temps:
        v = _finite(t)
        if v is None or v < -20 or v > 130:
            return None
        vals.append(v)
    return max(vals)


def envelope_ok(soc_temps: object, power: object, *, starting: bool) -> tuple[bool, str]:
    """Pure thermal/power envelope check.  Invalid sensor => False."""
    soc = soc_max(soc_temps)
    if soc is None:
        return False, "soc-sensor-invalid"
    if not isinstance(power, PowerState):
        return False, "power-sensor-invalid"
    batt_t, batt_p = _finite(power.battery_temp_c), _finite(power.battery_pct)
    if batt_t is None or batt_t < -20 or batt_t > 100:
        return False, "battery-temp-sensor-invalid"
    if batt_p is None or batt_p < 0 or batt_p > 100:
        return False, "battery-pct-sensor-invalid"
    if power.external is not True:
        return False, "external-power-required"
    if batt_p < BATTERY_MIN_PCT:
        return False, "battery-below-minimum"
    if batt_t >= BATTERY_ABORT_C:
        return False, "battery-temp-limit"
    if starting and soc >= THERMAL_START_MAX_C:
        return False, "soc-too-hot-to-start"
    if soc >= THERMAL_ABORT_C:
        return False, "soc-temp-limit"
    return True, "ok"


_HOLDER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SRCVERSION_RE = re.compile(r"^[0-9A-F]{1,64}$")
_KERNEL_RE = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")


def _watchdog_bound_ok(value: object) -> bool:
    v = _finite(value)
    return v is not None and 0 < v <= THERMAL_WATCHDOG_MAX_S


def _sample_envelope(inspector: HostInspector, starting: bool) -> tuple[bool, str, Optional[float]]:
    ok_p, power = _safe(inspector.power_state)
    ok_t, temps = _safe(inspector.soc_temps_c)
    if not (ok_p and ok_t):
        return False, "sensor-error", None
    ok, why = envelope_ok(temps, power, starting=starting)
    return ok, why, soc_max(temps)


# ---------------------------------------------------------------------------
# Recovery manager (trusted recovery identity; independent of lease/client).
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RecoveryManager:
    """``restore-stock`` for an admitted R0 via a dedicated recovery engine.
    Never consults the lease, never unloads/forces/reboots/loads a candidate.
    Loads only when the module is *confirmed* unloaded on the marker's boot
    with pinned kernel/hash.  Clears only after official identity, devices
    and BOTH 120-frame smoke tests.  The caller must hold ``RecoveryLock``.

    Result: PASS only if ``clear_recovery`` returned "pass"; "fail" =>
    FAILED with ``cleared=True`` (stock restored, operation failed)."""

    engine: PolicyEngine          # recovery-identity instance
    inspector: HostInspector
    module: IrisModuleControl
    smoke: SmokeRunner
    clock: Clock
    budget_s: float = R0_RECOVERY_BUDGET_S

    @staticmethod
    def _pending(op_id: str, outcome: Outcome, reason: str,
                 info: Optional[dict] = None) -> ActionResult:
        details = dict(info or {})
        details["cleared"] = False
        return ActionResult(ACTION_IRIS_R0, op_id, outcome, reason, details)

    def verify_official(self) -> tuple[bool, str]:
        ok, kernel = _safe(self.inspector.kernel_release)
        if not ok or kernel != IRIS_KERNEL_RELEASE:
            return False, "kernel-mismatch"
        ok, sha = _safe(self.inspector.official_module_sha256)
        if not ok or sha != IRIS_OFFICIAL_SHA256:
            return False, "artifact-sha-mismatch"
        ok, state = _safe(self.inspector.module_state)
        if not ok or not isinstance(state, ModuleState) or state.loaded is not True:
            return False, "module-not-loaded"
        if state.srcversion != IRIS_OFFICIAL_SRCVERSION:
            return False, "srcversion-mismatch"
        ok, present = _safe(self.inspector.iris_devices_present)
        if not ok or present is not True:
            return False, "devices-missing"
        return True, "ok"

    def _check_boot_ok(self, marker: RecoveryMarker) -> bool:
        ok, boot = _safe(self.inspector.boot_id)
        return ok and boot == marker.boot_id

    def _check_kernel_ok(self) -> bool:
        ok, kernel = _safe(self.inspector.kernel_release)
        return ok and kernel == IRIS_KERNEL_RELEASE

    def _check_budget(self, start: float, prev: float) -> tuple[bool, float, str]:
        budget = _finite(self.budget_s)
        now = _finite(self.clock.monotonic())
        if budget is None or budget < 0 or now is None or now < prev:
            return False, prev, "recovery-clock-error"
        if now - start > budget:
            return False, now, "budget-exceeded"
        return True, now, "ok"

    def restore(self, unload_ok: Optional[bool] = None) -> ActionResult:
        state, marker = read_recovery_state(self.engine)
        if state == STATE_NONE:
            return ActionResult(ACTION_IRIS_R0, "-", Outcome.PASS, "no-recovery-pending",
                                {"cleared": False})
        if state == STATE_RECONCILE:
            return self._pending("-", Outcome.BOOT_CHANGED_BLOCKED,
                                 "boot-changed-local-reconciliation-required")
        if state != STATE_RESTORE or marker is None:
            return self._pending("-", Outcome.RECOVERY_PENDING, "marker-state-unknown")
        op = marker.op_id
        start = _finite(self.clock.monotonic())
        budget = _finite(self.budget_s)
        if start is None or budget is None or budget < 0:
            return self._pending(op, Outcome.RECOVERY_PENDING, "recovery-clock-error")
        prev = start

        if not self._check_boot_ok(marker):
            return self._pending(op, Outcome.BOOT_CHANGED_BLOCKED,
                                 "boot-changed-local-reconciliation-required")

        ok, st = _safe(self.inspector.module_state)
        if not ok or not isinstance(st, ModuleState) or not isinstance(st.loaded, bool):
            return self._pending(op, Outcome.RECOVERY_PENDING, "module-state-unknown")

        load_attempted = False
        if st.loaded is False:
            if not self._check_boot_ok(marker):
                return self._pending(op, Outcome.BOOT_CHANGED_BLOCKED,
                                     "boot-changed-local-reconciliation-required")
            ok_k, kernel = _safe(self.inspector.kernel_release)
            ok_s, sha = _safe(self.inspector.official_module_sha256)
            if not (ok_k and ok_s and kernel == IRIS_KERNEL_RELEASE
                    and sha == IRIS_OFFICIAL_SHA256):
                return self._pending(op, Outcome.RECOVERY_PENDING, "official-artifact-mismatch")
            # Hashing/inspection may have taken time or changed the observed
            # host. Recheck after the reads, directly before the fixed load.
            if not self._check_kernel_ok():
                return self._pending(op, Outcome.RECOVERY_PENDING, "kernel-mismatch")
            if not self._check_boot_ok(marker):
                return self._pending(op, Outcome.BOOT_CHANGED_BLOCKED,
                                     "boot-changed-local-reconciliation-required")
            ok_b, prev, why_b = self._check_budget(start, prev)
            if not ok_b:
                return self._pending(op, Outcome.RECOVERY_PENDING, why_b)
            load_attempted = True
            ok, loaded = _safe(self.module.load_official)  # single attempt, no force
            if not ok or loaded is not True:
                return self._pending(op, Outcome.RECOVERY_PENDING, "load-failed",
                                     {"load_attempted": True})

        info = {"load_attempted": load_attempted}
        if not self._check_boot_ok(marker):
            return self._pending(op, Outcome.BOOT_CHANGED_BLOCKED,
                                 "boot-changed-local-reconciliation-required", info)
        id_ok, why = self.verify_official()
        if not id_ok:
            return self._pending(op, Outcome.RECOVERY_PENDING, why, info)
        ok_b, prev, why_b = self._check_budget(start, prev)
        if not ok_b:
            return self._pending(op, Outcome.RECOVERY_PENDING, why_b, info)

        if not self._check_boot_ok(marker):
            return self._pending(op, Outcome.BOOT_CHANGED_BLOCKED,
                                 "boot-changed-local-reconciliation-required", info)
        ok_b, prev, why_b = self._check_budget(start, prev)
        if not ok_b:
            return self._pending(op, Outcome.RECOVERY_PENDING, why_b, info)
        ok_c, cpu = _safe(lambda: self.smoke.cpu_decode(SMOKE_FRAMES))
        info["cpu_smoke_pass"] = bool(ok_c and cpu is True)
        if not info["cpu_smoke_pass"]:
            info["iris_smoke_pass"] = False
            return self._pending(op, Outcome.RECOVERY_PENDING, "smoke-failed", info)

        if not self._check_boot_ok(marker):
            return self._pending(op, Outcome.BOOT_CHANGED_BLOCKED,
                                 "boot-changed-local-reconciliation-required", info)
        if not self._check_kernel_ok():
            return self._pending(op, Outcome.RECOVERY_PENDING, "kernel-mismatch", info)
        ok_b, prev, why_b = self._check_budget(start, prev)
        if not ok_b:
            return self._pending(op, Outcome.RECOVERY_PENDING, why_b, info)

        ok_i, iris = _safe(lambda: self.smoke.iris_decode(SMOKE_FRAMES))
        info["iris_smoke_pass"] = bool(ok_i and iris is True)
        if not info["iris_smoke_pass"]:
            return self._pending(op, Outcome.RECOVERY_PENDING, "smoke-failed", info)

        ok_b, prev, why_b = self._check_budget(start, prev)
        if not ok_b:
            return self._pending(op, Outcome.RECOVERY_PENDING, why_b, info)
        if not self._check_boot_ok(marker):
            return self._pending(op, Outcome.BOOT_CHANGED_BLOCKED,
                                 "boot-changed-local-reconciliation-required", info)
        id_ok, why = self.verify_official()       # identity unchanged after smoke
        if not id_ok:
            return self._pending(op, Outcome.RECOVERY_PENDING, why, info)

        # Final identity reads must not silently consume the remaining budget
        # or leave a stale boot witness. The engine independently checks boot.
        if not self._check_kernel_ok():
            return self._pending(op, Outcome.RECOVERY_PENDING, "kernel-mismatch", info)
        if not self._check_boot_ok(marker):
            return self._pending(op, Outcome.BOOT_CHANGED_BLOCKED,
                                 "boot-changed-local-reconciliation-required", info)
        ok_b, prev, why_b = self._check_budget(start, prev)
        if not ok_b:
            return self._pending(op, Outcome.RECOVERY_PENDING, why_b, info)
        unload_result = "pass" if unload_ok is True else "fail"
        ok, final = _safe(lambda: self.engine.clear_recovery(
            recovery_evidence(marker), unload_result))
        if not ok or final not in ("pass", "fail"):
            # Stock restored but evidence not durable/unknown: marker stays, no PASS.
            return self._pending(op, Outcome.RECOVERY_PENDING,
                                 "restored-but-clear-receipt-failed", info)
        info.update(cleared=True, final=final)
        if final == "pass":
            return ActionResult(ACTION_IRIS_R0, op, Outcome.PASS, "r0-cycle-restored", info)
        return ActionResult(ACTION_IRIS_R0, op, Outcome.FAILED,
                            "stock-restored-operation-failed", info)


# ---------------------------------------------------------------------------
# Action executor (run-fixed-action).
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ActionExecutor:
    engine: PolicyEngine          # executor-identity instance (not recovery)
    inspector: HostInspector
    recovery: RecoveryManager
    recovery_lock: RecoveryLock
    module: IrisModuleControl
    thermal: ThermalLauncher
    clock: Clock

    def __post_init__(self) -> None:
        if self.recovery.engine is self.engine:
            raise ValueError("recovery must use a dedicated engine instance")

    def run(self, raw_request: object) -> ActionResult:
        try:
            action = parse_request(raw_request)
        except ActionDenied as exc:
            return ActionResult("?", "-", Outcome.DENIED, exc.reason)
        try:
            self._no_pending_recovery()
            if action == ACTION_AUDIT:
                return self._audit()
            if action == ACTION_IRIS_R0:
                return self._iris_r0()
            return self._thermal()
        except ActionDenied as exc:
            return ActionResult(action, "-", Outcome.DENIED, exc.reason)

    # -- shared ------------------------------------------------------------
    def _no_pending_recovery(self) -> None:
        state, _ = read_recovery_state(self.recovery.engine)
        if state == STATE_UNKNOWN:
            raise ActionDenied("recovery-state-unknown")
        if state != STATE_NONE:
            raise ActionDenied("recovery-pending")

    def _admit(self, action: str) -> Any:
        try:
            ticket = self.engine.admit({"action": action})
        except ActionDenied:
            raise
        except Exception as exc:
            raise ActionDenied("admit-denied:" + type(exc).__name__)
        if not _ticket_ok(ticket, action):
            raise ActionDenied("ticket-invalid")
        return ticket

    def _lease_ok(self, ticket: Any) -> bool:
        ok, valid = _safe(lambda: self.engine.lease_valid(ticket))
        return ok and valid is True

    def _finish(self, ticket: Any, outcome: Outcome, reason: str,
                details: Optional[dict] = None,
                evidence: Optional[dict] = None) -> ActionResult:
        """Only for committed ops that remain active.  ``evidence`` only for
        audit pass."""
        details = dict(details or {})
        result = engine_result(outcome)
        if result == "pass" and evidence is not None:
            call = lambda: self.engine.finish(ticket, "pass", audit_evidence=evidence)
        else:
            call = lambda: self.engine.finish(ticket, result)
        ok, _ = _safe(call)
        if not ok:
            details["result_receipt"] = "failed"
            if outcome in (Outcome.PASS, Outcome.PARTIAL):
                outcome, reason = Outcome.FAILED, "result-receipt-failed"
        return ActionResult(ticket.action, ticket.op_id, outcome, reason, details)

    @staticmethod
    def _not_committed(ticket: Any, reason: str) -> ActionResult:
        # Commit raised: no active op known -> no finish (no fabricated receipt).
        return ActionResult(ticket.action, ticket.op_id, Outcome.DENIED, reason,
                            {"result_receipt": "not-recorded"})

    # -- audit (read-only) -------------------------------------------------
    def collect_audit(self) -> tuple[Outcome, str, dict]:
        """Read-only bounded snapshot (G-AUDIT).  FAILED if the audit process
        holds CAP_SYS_MODULE or that is undetermined; PARTIAL (never PASS) if
        any required module read/hash is missing."""
        ok, cap = _safe(self.inspector.has_cap_sys_module)
        if not ok or cap is not False:
            return Outcome.FAILED, "audit-cap-sys-module-not-excluded", {}
        report: dict = {"module_name": IRIS_MODULE_NAME, "cap_sys_module": False}
        ok, kernel = _safe(self.inspector.kernel_release)
        if ok and isinstance(kernel, str) and _KERNEL_RE.fullmatch(kernel):
            report["kernel_release"] = kernel
        ok, state = _safe(self.inspector.module_state)
        if ok and isinstance(state, ModuleState) and isinstance(state.loaded, bool):
            report["module_loaded"] = state.loaded
            if state.loaded:
                # Loaded: srcversion, refcnt and holders all required and strict.
                if isinstance(state.srcversion, str) and _SRCVERSION_RE.fullmatch(state.srcversion):
                    report["module_srcversion"] = state.srcversion
                if isinstance(state.refcnt, int) and not isinstance(state.refcnt, bool) \
                        and 0 <= state.refcnt < 1_000_000:
                    report["module_refcnt"] = state.refcnt
                holders = state.holders
                if isinstance(holders, (list, tuple)) and len(holders) <= AUDIT_MAX_HOLDERS \
                        and all(isinstance(h, str) and _HOLDER_RE.fullmatch(h) for h in holders):
                    report["module_holders"] = list(holders)
            else:
                # Not loaded: srcversion/refcnt/holders do not exist; explicit values.
                report.update(module_srcversion=None, module_refcnt=None, module_holders=[])
        ok, sha = _safe(self.inspector.official_module_sha256)
        if ok and isinstance(sha, str) and _SHA256_RE.fullmatch(sha):
            report["module_file_sha256"] = sha
        ok, power = _safe(self.inspector.power_state)
        if ok and isinstance(power, PowerState):
            report.update(power_external=power.external if isinstance(power.external, bool)
                          else None,
                          battery_pct=_finite(power.battery_pct),
                          battery_temp_c=_finite(power.battery_temp_c))
        ok, temps = _safe(self.inspector.soc_temps_c)
        report["soc_max_temp_c"] = soc_max(temps) if ok else None
        report["module_matches_official"] = (
            report.get("kernel_release") == IRIS_KERNEL_RELEASE
            and report.get("module_file_sha256") == IRIS_OFFICIAL_SHA256
            and report.get("module_srcversion") == IRIS_OFFICIAL_SRCVERSION)
        missing = [k for k in AUDIT_REQUIRED_KEYS if k not in report]
        report["missing"] = missing
        clean = {k: report.get(k) for k in AUDIT_ALLOWED_KEYS}
        if missing:
            return Outcome.PARTIAL, "audit-required-reads-missing", clean
        return Outcome.PASS, "audit-complete", clean

    def _audit(self) -> ActionResult:
        ticket = self._admit(ACTION_AUDIT)
        entered = False
        guard_ok = False
        guard_reason: Optional[str] = None
        outcome = Outcome.FAILED
        reason = "audit-not-captured"
        report: dict = {}
        commit_error: Optional[str] = None
        try:
            with self.engine.commit(ticket) as committed:
                entered = True
                guard_ok, guard_reason = _launch_guard_ok(committed)
                if guard_ok:
                    outcome, reason, report = self.collect_audit()
        except Exception as exc:
            commit_error = type(exc).__name__
        if not entered:
            return self._not_committed(ticket, "commit-denied:" + str(commit_error))
        if commit_error is not None:
            return self._finish(ticket, Outcome.FAILED, "commit-exit-error:" + commit_error)
        if not guard_ok:
            fail_outcome = (Outcome.FAILED
                            if guard_reason and guard_reason.startswith("launch-guard-")
                            else Outcome.ABORTED)
            return self._finish(ticket, fail_outcome, guard_reason or "lease-expired-before-launch")
        evidence = None
        if outcome is Outcome.PASS:
            evidence = audit_evidence(report)
            if evidence is None:
                outcome, reason = Outcome.FAILED, "audit-evidence-out-of-bounds"
        return self._finish(ticket, outcome, reason, report, evidence)

    # -- iris-r0 -----------------------------------------------------------
    def iris_preflight(self) -> None:
        """All R0 preconditions, read-only; raises ActionDenied."""
        ok, boot = _safe(self.inspector.boot_id)
        if not ok or not isinstance(boot, str) or not _BOOT_ID_RE.fullmatch(boot):
            raise ActionDenied("boot-id-invalid")
        ok, kernel = _safe(self.inspector.kernel_release)
        if not ok or kernel != IRIS_KERNEL_RELEASE:
            raise ActionDenied("kernel-not-pinned")
        ok, sha = _safe(self.inspector.official_module_sha256)
        if not ok or sha != IRIS_OFFICIAL_SHA256:
            raise ActionDenied("official-sha-mismatch")
        ok, state = _safe(self.inspector.module_state)
        if not ok or not isinstance(state, ModuleState) or state.loaded is not True:
            raise ActionDenied("module-not-loaded-or-unknown")
        if state.srcversion != IRIS_OFFICIAL_SRCVERSION:
            raise ActionDenied("srcversion-mismatch")
        if state.refcnt != 0 or list(state.holders):
            raise ActionDenied("module-in-use")
        ok, users = _safe(self.inspector.device_users)
        if not ok or not isinstance(users, DeviceUsers) or users.visible is not True:
            raise ActionDenied("process-visibility-insufficient")
        if list(users.pids):
            raise ActionDenied("device-has-users")
        ok, devices = _safe(self.inspector.iris_devices_present)
        if not ok or devices is not True:
            raise ActionDenied("devices-missing")
        env_ok, why, _ = _sample_envelope(self.inspector, starting=True)
        if not env_ok:
            raise ActionDenied(why)

    def _iris_r0(self) -> ActionResult:
        self.iris_preflight()
        ticket = self._admit(ACTION_IRIS_R0)
        with self.recovery_lock.hold():      # exclusive vs recovery supervisor
            return self._iris_r0_locked(ticket)

    def _iris_r0_locked(self, ticket: Any) -> ActionResult:
        unload_ok: Optional[bool] = None
        unload_attempted = False
        entered = False
        denied: Optional[str] = None
        commit_error: Optional[str] = None
        try:
            with self.engine.commit(ticket) as committed:
                entered = True
                # Lock held; lease revalidated after fsync; marker durable.
                try:
                    self.iris_preflight()          # fresh safety check under lock
                except ActionDenied as exc:
                    denied = exc.reason
                else:
                    guard_ok, guard_reason = _launch_guard_ok(committed)
                    if not guard_ok:
                        denied = guard_reason
                    else:
                        unload_attempted = True
                        ok, res = _safe(self.module.unload_official)  # once, never retried
                        unload_ok = bool(ok and res is True)
        except Exception as exc:
            commit_error = type(exc).__name__
        # Outside the engine lock; recovery never depends on lease/revocation.
        state, _ = read_recovery_state(self.recovery.engine)
        if state == STATE_NONE and not unload_attempted:
            if not entered:
                return self._not_committed(ticket, "commit-denied:" + str(commit_error))
            return self._finish(ticket, Outcome.DENIED, denied or "no-marker-after-commit")
        rec = self.recovery.restore(unload_ok=unload_ok)
        details = dict(rec.details)
        details.update(unload_attempted=unload_attempted, unloaded=unload_ok,
                       recovery_reason=rec.reason)
        # clear_recovery is the terminal receipt: never finish() after it.
        if rec.details.get("cleared") is not True:
            return ActionResult(ACTION_IRIS_R0, ticket.op_id, rec.outcome, rec.reason, details)
        if rec.details.get("final") == "pass" and unload_ok is True and denied is None:
            return ActionResult(ACTION_IRIS_R0, ticket.op_id, Outcome.PASS,
                                "r0-cycle-restored", details)
        reason = denied or ("unload-failed" if unload_ok is not True else "engine-final-fail")
        return ActionResult(ACTION_IRIS_R0, ticket.op_id, Outcome.FAILED, reason, details)

    # -- thermal (unprivileged) -------------------------------------------
    def _thermal(self) -> ActionResult:
        env_ok, why, _ = _sample_envelope(self.inspector, starting=True)
        if not env_ok:
            raise ActionDenied(why)
        ok, wd = _safe(self.thermal.watchdog_ready)
        if not ok or not _watchdog_bound_ok(wd):
            raise ActionDenied("watchdog-not-ready")   # before admit: no use consumed
        ticket = self._admit(ACTION_THERMAL)
        handle: Optional[ThermalHandle] = None
        entered = False
        launch_attempted = False
        pre_reason: Optional[str] = None
        commit_error: Optional[str] = None
        try:
            with self.engine.commit(ticket) as committed:
                entered = True
                env_ok, why, _ = _sample_envelope(self.inspector, starting=True)
                ok_w, wd = _safe(self.thermal.watchdog_ready)
                if not env_ok:
                    pre_reason = why
                elif not ok_w or not _watchdog_bound_ok(wd):
                    pre_reason = "watchdog-not-ready"
                else:
                    guard_ok, guard_reason = _launch_guard_ok(committed)
                    if not guard_ok:
                        pre_reason = guard_reason
                    else:
                        launch_attempted = True
                        ok, h = _safe(lambda: self.thermal.start(
                            THERMAL_DURATION_S, THERMAL_DUTY, THERMAL_WORKERS))
                        if ok and isinstance(h, ThermalHandle):
                            handle = h
                        else:
                            pre_reason = "worker-launch-unknown"
        except Exception as exc:
            commit_error = type(exc).__name__
        if not entered:
            return self._not_committed(ticket, "commit-denied:" + str(commit_error))
        if handle is None:
            if not launch_attempted:
                outcome = (Outcome.FAILED
                           if pre_reason and pre_reason.startswith("launch-guard-")
                           else Outcome.ABORTED)
                return self._finish(ticket, outcome, pre_reason or "aborted")
            ok, none_left = _safe(self.thermal.stop_orphans)
            if ok and none_left is True:
                return self._finish(ticket, Outcome.FAILED, pre_reason or "worker-launch-unknown",
                                    {"orphans_stopped": True})
            return self._blocked(ticket, "worker-launch-unknown-orphans-not-stopped")
        details: dict = {}
        if commit_error is not None:
            reason = "commit-exit-error:" + commit_error
        else:
            try:
                reason = self._monitor(ticket, handle, details)
            except Exception as exc:  # supervisor fault: stop, never PASS
                reason = "supervisor-error:" + type(exc).__name__
        stopped, stop_s = self._stop(handle)
        details.update(stopped=stopped, stop_latency_s=stop_s)
        if not stopped:
            # Nothing disarmed; RuntimeMaxSec stays the backstop.  Leave the
            # committed op active so the engine blocks further actions.
            return self._blocked(ticket, "stop-not-confirmed-watchdog-backstop", details)
        if reason == "duration-reached":
            if stop_s > THERMAL_STOP_TARGET_S:
                return self._finish(ticket, Outcome.FAILED, "stop-latency-exceeded", details)
            if _finite(details.get("elapsed_s")) is None or details["elapsed_s"] < THERMAL_DURATION_S:
                return self._finish(ticket, Outcome.FAILED, "duration-unverified", details)
            return self._finish(ticket, Outcome.PASS, reason, details)  # no audit_evidence
        if reason in ("worker-exited-early", "worker-state-unknown",
                      "watchdog-unconfirmed", "clock-error", "duration-unverified") \
                or reason.startswith(("supervisor-error", "commit-exit-error")):
            return self._finish(ticket, Outcome.FAILED, reason, details)
        return self._finish(ticket, Outcome.ABORTED, reason, details)

    @staticmethod
    def _blocked(ticket: Any, reason: str, details: Optional[dict] = None) -> ActionResult:
        d = dict(details or {})
        d["active_left_blocked"] = True
        return ActionResult(ticket.action, ticket.op_id, Outcome.BLOCKED_ACTIVE, reason, d)

    def _monitor(self, ticket: Any, handle: ThermalHandle, details: dict) -> str:
        ok, wd = _safe(handle.watchdog_max_s)
        if not ok or not _watchdog_bound_ok(wd):
            return "watchdog-unconfirmed"
        details["watchdog_max_s"] = _finite(wd)
        start = _finite(self.clock.monotonic())
        if start is None:
            return "clock-error"
        prev = start
        samples, max_soc = 0, None
        try:
            while True:
                now = _finite(self.clock.monotonic())
                if now is None or now < prev:
                    return "clock-error"
                prev = now
                ok_a, alive = _safe(handle.alive)
                if not ok_a or not isinstance(alive, bool):
                    return "worker-state-unknown"
                if not alive:
                    return "worker-exited-early"
                if not self._lease_ok(ticket):
                    return "lease-invalid"
                env_ok, why, soc = _sample_envelope(self.inspector, starting=False)
                samples += 1
                if soc is not None:
                    max_soc = soc if max_soc is None else max(max_soc, soc)
                if not env_ok:
                    return why
                if now - start >= THERMAL_DURATION_S:
                    if samples < 2:
                        return "duration-unverified"
                    return "duration-reached"
                self.clock.sleep(THERMAL_SAMPLE_S)
        finally:
            details.update(samples=samples, max_soc_c=max_soc,
                           elapsed_s=prev - start)

    def _stop(self, handle: ThermalHandle) -> tuple[bool, float]:
        t0 = _finite(self.clock.monotonic())
        if t0 is None:
            _safe(handle.stop)
            return False, THERMAL_STOP_TARGET_S
        prev = t0
        _safe(handle.stop)
        while True:
            ok, alive = _safe(handle.alive)
            now = _finite(self.clock.monotonic())
            if now is None or now < prev:
                return False, max(0.0, prev - t0)
            prev = now
            waited = now - t0
            if ok and alive is False:
                return True, waited
            if waited >= THERMAL_STOP_TARGET_S:
                return False, waited
            ok_s, _ = _safe(lambda: self.clock.sleep(0.05))
            if not ok_s:
                return False, waited


class RecoverySupervisor:
    """Independent recovery unit entry (controller restart, executor crash,
    client loss).  Serialised with in-flight R0 through ``RecoveryLock``.
    Restores R0 with unload_result "fail" (unload outcome unknown here) and
    stops orphan thermal workers."""

    def __init__(self, recovery: RecoveryManager, lock: RecoveryLock,
                 thermal: ThermalLauncher):
        self._recovery = recovery
        self._lock = lock
        self._thermal = thermal

    def run_once(self) -> dict:
        ok, orphans = _safe(self._thermal.stop_orphans)
        with self._lock.hold():
            rec = self._recovery.restore(unload_ok=None)
        return {"thermal_orphans_stopped": bool(ok and orphans is True), "recovery": rec}


__all__ = [n for n in dir() if not n.startswith("_")]
