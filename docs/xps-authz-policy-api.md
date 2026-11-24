# XPS AUTHZ v1.1 — policy engine API (M2-A)

Library: `scripts/xps_authz_policy.py` (stdlib only). Tests: `tests/test_xps_authz_policy.py`.
**Policy and ledger only.** It never runs commands and never touches modules or hardware.
It is not a general-purpose privileged command executor. ADR-001 r2, contract revision 2.

## Trust model

- `caller_uid` is injected **only** by the trusted root broker, from the kernel
  (`SO_PEERCRED` on the connecting socket). It must never come from client data.
- Supply a fresh random `incarnation` on every trusted broker process start.
  The broker's owner, admission and launch engines share the process, incarnation and state directory.
  The in-process fault gate is shared for that ledger and incarnation across engine instances.
- `Identities(owner, agent, recovery)`: the agent uid must differ from the owner uid, the recovery uid and 0.
  Owner control (`OwnerControl`) and recovery (`clear_recovery`) are separate entry points. The agent adapter never sees either one.
- State directory: a real directory (not a symlink), owned by `expected_uid` (root in production), mode `0700`.
  Protected files must be regular files with `0600`, one link, and the same owner. Anything else raises `UnsafeStorage`.
- One authoritative store, `state.json`: a `{sha256, state}` envelope. Every write goes through a
  temp file, `fsync(file)`, `rename`, then `fsync(dir)`. A single `flock` on `lock` serializes every mutation.

## Fixed catalog

| action | uses / grant | time reserved before effect |
|---|---|---|
| `audit` | 5 | 60 s |
| `iris-r0` | 1 | 300 s (includes restore budget) |
| `thermal` | 1 | 15 s (worker max 12 s) |

A grant expires at `floor(CLOCK_BOOTTIME at issuance) + 1200`. The ledger stores integer grant times.
The lease lasts at most 1200 seconds and is bound to the boot ID and broker incarnation.
Reservation and expiry checks use the current clock, including fractions.

## Agent / executor API (`PolicyEngine`)

| call | contract |
|---|---|
| `admit({"action": name}) -> Ticket` | The request must be exactly that one-key dict with a `str` value from the catalog. Under the lock the engine checks: no ledger fault, no R0 marker, receipt capacity available, no active op, a grant for this boot and broker incarnation that is not revoked or expired, enough time left for the reservation, uses left, and an R0 pin that matches the running kernel. It consumes one use and writes the `admit` receipt durably **before** returning. Write failure means no ticket. |
| `with commit(ticket) as op:` | `op` is a frozen `CommittedOp` with `op_id`, `action` and `check_launch()`. **Every** ticket field and its exact type must match the active op (the digest is recomputed). Phase must be `admitted`. It rechecks the 30 s commit window, lease, boot and pin, then writes the `commit` receipt durably. For `iris-r0`, the commit receipt and `r0_marker` go in **one** atomic replace. After the fsync it **revalidates clock and lease** before yielding: if the lease is no longer valid there is no launch, the use is not refunded, and any R0 marker already persisted is kept. The lock is held throughout the `with` body. Perform preflight and launch inside it. |
| `op.check_launch() -> bool` | Call after preflight, immediately before irreversible unload or spawn. Proceed only when the result is exactly `True`. Under the existing lock it validates the committed ticket, ledger, boot, pin, incarnation, revocation, expiry and time reserve. A failed check raises. The check is valid only inside the commit block on the thread that entered it. Denial keeps the use consumed and any R0 marker available for recovery. |
| `finish(ticket, result, audit_evidence=None)` | `result` ∈ `pass\|fail\|aborted`. `pass` is accepted only for a **committed** `audit` or `thermal` op. `iris-r0` accepts only `fail` or `aborted`, and those **never** remove the marker. An audit `pass` requires `audit_evidence`. Nothing is ever refunded. |
| `lease_valid(ticket) -> bool` | Lock-free thermal poll (target 250 ms). Returns True only for a matching ticket in phase `committed`, on the same boot, grant and broker incarnation, not revoked or expired, with no fault and no poison. Any exception returns False. |
| `status() -> dict` | Sanitized (see below). |
| `pending_recovery() -> dict` | Still works when writes fail. Possible `state` values: `none`, `restore_same_boot` (includes marker fields), `reconcile_required` (boot or kernel changed), or `unknown` (corrupt or unreadable state; **no automatic load**, owner reconciliation required). |
| `clear_recovery(evidence, unload_result) -> final` | Recovery uid only. Same boot only. Exact evidence required (below). Clears the marker and writes the `recovery_cleared` receipt with `final` atomically. `final` is `pass` only if `unload_result == "pass"` **and** no fail, aborted or closed receipt exists for the op. Otherwise `final` is `fail`: a verified restore after a failed unload is still FAIL. If evidence is bad or the write fails, the marker is kept. After a clear, `finish` on that ticket is denied. |

### `audit_evidence` schema (exact keys, no other keys)

```json
{"report_sha256": "<64 lowercase hex>", "report_bytes": 1..16777216 (int), "findings": 0..10000 (int)}
```

Technical limitation: the engine cannot prove these values came from the root audit unit.
The broker must take them from the executor's root-owned output, never from the client.

### `clear_recovery` / `reconcile_marker` evidence schema (exact keys)

```json
{"op_id": "<marker op_id>", "boot_id": "<current boot>", "kernel_release": "<current == pinned>",
 "module_sha256": "2183021a89244ad917b3afcbe24f2515c5d671033082f783c22ab817e6c6236b",
 "module_srcversion": "<== pinned srcversion>", "stock_module_verified": true, "devices_present": true,
 "cpu_smoke_frames": 120, "cpu_smoke_pass": true, "iris_smoke_frames": 120, "iris_smoke_pass": true}
```

`unload_result` ∈ `"pass" | "fail"`. Booleans must be the literal `true`, and frame counts must be `int` exactly 120.
`R0Pin(kernel_release, srcversion)` is root-owned install config. The SHA is fixed to the constant above.
`srcversion` must match `[0-9A-F]{23}`. The marker stores the kernel release, SHA and srcversion.

### `status()` (sanitized: no paths, uids, grant ids or receipt bodies)

```json
{"state": "ok", "new_actions": "allowed|denied", "reason": null | "ledger_fault|r0_recovery_pending|ledger_capacity|operation_active|owner_reconciliation_required|no_grant|stale_boot|stale_incarnation|revoked|expired",
 "remaining_seconds": int, "uses_left": {"audit": n, "iris-r0": n, "thermal": n},
 "active": null | {"op_id", "action", "phase"},
 "ledger_seq": int,
 "last_operation": null | {"seq", "op_id", "action", "event", "phase", "outcome"},
 "recovery_required": bool, "reconciliation_required": bool}
```

If the state is unreadable, `status()` returns `{"state": "unavailable", "new_actions": "denied", "recovery_required": "unknown", "ledger_seq": null, "last_operation": null}`.
`ledger_seq` only ever increases, including across archival. `last_operation` survives archival.
A client whose response was dropped can correlate using `op_id`, `seq` and `phase`.

## Owner API (`OwnerControl`, owner uid only)

`initialize()` (refuses to overwrite) · `grant()` (denied on ledger fault, active op, R0 marker or capacity) ·
`revoke()` (durable under the commit lock **before** the ack, so no launch can follow an ack.
A retry that sees the grant already revoked synchronizes the directory again before acknowledging. R0 recovery remains available) · `reconcile_marker(evidence)` (after a boot change, final is always `fail`,
nothing loads automatically) · `close_unknown_operation(op_id, "verified_ended"|"verified_failed")`
(committed audit or thermal ops are **never** closed by timeout) · `archive_receipts()` (writes a durable
archive file, then records `archived` with its SHA-256, `count`, `first_seq` and `last_operation`; refused while an op or marker is pending) ·
`clear_ledger_fault()`.

## Failure semantics

- Corruption fails closed. This covers bad JSON, duplicate keys, NaN or Infinity, checksum mismatch, unknown or missing keys, out-of-range quotas,
  broken cross-references (active→grant, committed R0→marker, receipt sequence and head), and a missing state file.
- Each state update unlinks `ledger-ok` and synchronizes the directory before replacing the state.
  The token is restored for a healthy ledger only after the state is durable. A failed pre-invalidation
  aborts before state replacement and poisons all engines for that ledger in the broker, even if the
  token remains visible. A fresh broker incarnation rejects the old grant. An absent token requires
  owner inspection and `clear_ledger_fault()` before a new grant.
- Receipts are never truncated. New admissions and grants stop at `MAX_RECEIPTS - RESERVED_RECEIPTS`.
  An in-flight op can still commit, finish or recover inside the reserve. Reaching the hard cap is a persistent ledger fault.
- Uncommitted admissions are closed automatically after 30 s or a boot change, without refund. No effect can have started, because commit refuses them.
- Tests use temporary directories, new broker incarnations and injected ENOSPC, unlink and fsync failures.
  Physical power-loss and kernel-crash durability, broker integration and native XPS acceptance remain untested.
