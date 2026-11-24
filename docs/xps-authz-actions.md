# XPS AUTHZ v1.1 (M2-B) — Action Executor & R0 Recovery

**Scope:** LAB-ONLY component (`action-executor`, `recovery-manager`, `RecoverySupervisor`) implementing ADR-001 / architecture contract revision 2 inside `authz-actions-worktree`. Not production-validated; not an authorization to install, enable, or run privileged operations on the XPS host.

## Files & Integrity (SHA-256)

| File | Role | SHA-256 |
|---|---|---|
| `scripts/xps_authz_actions.py` | Inert fixed-catalog executor & R0 recovery logic | `255bd39ef02a76e815224340bfd5883644e33e289e135a9004fe5ecde68a7a96` |
| `tests/test_xps_authz_actions.py` | In-memory unit tests using abstract/fake adapters only | `685590d467adee9b77b84b2db19909a5daf27e557cea6d702be48048cfcc6c79` |
| `docs/xps-authz-actions.md` | M2-B documentation, test evidence, blockers & limitations | *(see report)* |

## Architecture & Consumed M2A Interface

`scripts/xps_authz_actions.py` delegates all durable state, consumption, locking, and receipts to the M2A `PolicyEngine` (via abstract interfaces only; no filesystem, subprocess, shell, `sudo`, environment inheritance, or `__main__` entrypoint):

1. **Strict catalog (`parse_request`)**: accepts only `{"action": <id>}` with `<id>` in `("audit", "iris-r0", "thermal")`; fixed systemd unit catalog (`UNIT_CATALOG`, `RECOVERY_UNIT`) and `CLEAN_ENVIRONMENT`.
2. **M2A surface consumed**:
   - `engine.admit({"action": action}) -> Ticket` (durable consumption before effects).
   - `with engine.commit(ticket) as committed:` (holds common `flock`; revalidates lease after fsync; persists `iris-r0` recovery marker).
   - `committed.check_launch() -> bool` (launch guard called under the already-held commit `flock` immediately before `collect_audit()`, `unload_official()`, or `thermal.start()`; requires exact `True` with no `None` fallback, no nested `engine.lease_valid(ticket)` inside `commit`, and fails closed if absent or invalid).
   - `engine.lease_valid(ticket) -> bool` (called with the original `Ticket`, strictly outside `commit`).
   - `engine.finish(ticket, "pass"|"fail"|"aborted", audit_evidence=None)` (`audit_evidence` only on `audit` `PASS`, bounded to `AUDIT_MAX_BYTES = 16384`, `AUDIT_MAX_FINDINGS = 64`).
   - `recovery_engine.pending_recovery() -> dict` (flat record with `state` in `("none", "restore_same_boot", "reconcile_required", "unknown")` and top-level `MARKER_FIELDS`).
   - `recovery_engine.clear_recovery(evidence, unload_result) -> "pass"|"fail"` (exact `RECOVERY_EVIDENCE_KEYS`, dedicated recovery engine identity).
3. **Lock order (no nesting)**: `RecoveryLock` -> engine common `flock`. `ActionExecutor` enforces `self.recovery.engine is not self.engine`.

## Key Controls & Codex Review Fixes

- **Audit (`G-AUDIT`, no secrets)**:
  - Calls `committed.check_launch()` immediately before `collect_audit()` inside the held `commit` `flock`; cannot start capture after revoke/expiry or when `check_launch()` is missing or returns non-`True` (`None`, etc.).
  - Rejects `CAP_SYS_MODULE` present/unknown (`FAILED`). When `loaded=True`, requires strict `srcversion`, `refcnt`, and `holders`; missing/invalid required reads yield `Outcome.PARTIAL` (recorded as `"fail"`, never `PASS`). Output is sanitized strictly to `AUDIT_ALLOWED_KEYS` with regex/bounds checks so arbitrary strings or secrets never propagate into reports or `audit_evidence`.
- **Thermal (`G-THERM`)**:
  - `ThermalLauncher.watchdog_ready()` checked before `admit()` (avoids consuming uses if unit `RuntimeMaxSec` is missing or `> 12.0s`) and rechecked under the held commit `flock`, followed immediately by `committed.check_launch()`.
  - `soc_max()` enforces exact `SOC_SENSOR_COUNT = 58` non-battery thermal readings per pinned XPS schema (any missing `< 58`, extra `> 58`, or non-finite/out-of-range reading yields `None` -> `soc-sensor-invalid`, denying/aborting; real M3–M5 host adapter must enforce exact pinned sensor identity names). Start requires `< 55.0 C`, abort at `>= 65.0 C`, battery `>= 30%` and `< 40.0 C`, external power `True`.
  - `_monitor` checks `handle.alive()`, `lease_valid(ticket)`, and `_sample_envelope(inspector, starting=False)` (all 58 sensors + power) **at the `THERMAL_DURATION_S` boundary** before returning `"duration-reached"` (`41` samples at `0.25s` cadence over `10.0s`), checks monotonic finite clock readings (`clock-error`), requires `samples >= 2` (`duration-unverified`), and verifies `elapsed_s >= THERMAL_DURATION_S` and `stop_latency_s <= THERMAL_STOP_TARGET_S` (`2.0s`) via `_stop` before `PASS`.
- **R0 & Recovery (`G-R0`)**:
  - Strict marker identity pinning (`IRIS_KERNEL_RELEASE = "7.3.0-11-generic"`, `IRIS_OFFICIAL_SHA256`, `IRIS_OFFICIAL_SRCVERSION`, valid `_BOOT_ID_RE`, valid non-empty/finite `committed_at`).
  - `RecoveryManager.restore()` enforces monotonic finite clock/budget (`recovery-clock-error` / `budget-exceeded`) and rechecks `boot_id`, pinned `kernel_release` / `verify_official()`, and budget: (1) initially, (2) immediately before `load_official()`, (3) after load / before CPU smoke, (4) between CPU and Iris 120-frame smoke tests, and (5) after Iris smoke immediately before `clear_recovery()`. Any boot change (`BOOT_CHANGED_BLOCKED`) or timeout/clock error (`RECOVERY_PENDING`) fails closed and preserves the marker.
- **Static & Test Harness Guards**:
  - `FakeThermal.watchdog_ready()`, `CommittedOp.check_launch()`, and 58-sensor fake fixtures implemented in `tests/test_xps_authz_actions.py`.
  - `StaticSafetyTests.test_no_process_shell_fs_or_cli` excludes AST docstring nodes when checking for `"__main__"` / forbidden tokens while inspecting all AST imports, constants, names, attributes, and non-docstring lines.

## Test Verification (Fake Adapters Only)

- Command: `python3 -m unittest -v tests/test_xps_authz_actions.py`
  - Result: **74 passed, 0 failed, 0 skipped** (in-memory fakes only; does **not** represent native XPS sysfs or M2A composition testing).
- Command: `python3 -m unittest discover -s tests -p 'test_*.py' -q`
  - Result: **306 tests ran, OK (`skipped=2` in unrelated repository tests; 0 skipped in `test_xps_authz_actions.py`)**.

## Explicit Blockers & Limitations

1. **M2A Composition & `CommittedOp.check_launch()` Exact-`True` Contract**:
   - M2B requires `committed.check_launch() is True` (rejects `None`, non-bool values, exceptions, or missing attribute) under the held `commit` `flock`.
   - M2A policy-engine code is outside `authz-actions-worktree`; only `FakeEngine` / `CommittedOp` was executed here. Cross-component composition was subsequently tested in the separate integration worktree (8 integration tests PASS); effects remain simulated. See the lab evidence document.
2. **NOT_RUN — Real Adapters & Host Acceptance (M3–M6)**:
   - The 58-sensor count is verified only against an in-memory 58-float fake fixture; real M3–M5 `HostInspector` adapters must bind and enforce the 58 pinned XPS non-battery sensor identity names deterministically.
   - No real systemd units, `flock` files, sysfs sensors, kernel module loads/unloads, `sudo`/root operations, MCP connector isolation, or Dell XPS 13 9345 ARM64 native tests were executed here.

Final integration delta: recheck boot, kernel and remaining recovery budget after hashing and final identity reads, immediately before the next fixed operation. Negative tests preserve marker on boot change during hash or exhausted budget during final verification.
