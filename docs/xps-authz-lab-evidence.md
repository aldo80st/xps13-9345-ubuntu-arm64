# XPS-03 AUTHZ v1.1 — laboratory integration checkpoint (2026-11-24)

**Not a deployable controller.** ADR-001 r2 is in main (#61); reviewed transport, native read-only inspector and broker/migration design are in main (#62). This package integrates the deterministic policy engine with inert abstract effect adapters. There is no installed listener, account, credential, privileged command entry point, real worker, grant or native hardware effect.

## Iterations and evidence

- Claude produced initial M2A/M2B; quota reached at 20:49Z. Codex took over M2A and Antigravity took over M2B. Codex reviewer c609f0b remained independent and read-only. Rejected actions and review findings preserved in isolated worktrees.
- Policy: 65 tests. Strict durable state pre-invalidation, shared incarnation fault gate, new-incarnation denial, durable revoke retry, conservative 1200 s grant, exact true check_launch under commit flock, ledger sequence and fixed use limits. Restart test launches a new unprivileged Python process. Crash/power-loss and deployed identity provenance remain untested.
- Actions: 74 tests with memory-only adapters. Audit guard and bounded evidence; R0 marker before effect, boot/hash/budget checks before load and clear, both 120-frame smoke proofs simulated; thermal 58 nonbattery values, expiry/revoke/final sample, prearmed watchdog assumption. No actual module or load tests.
- Broker: 10 tests, exact new receipt ID/action/sequence; no ACK on faulted ledger. Eight integration tests use actual policy with temp-directory state and fake hardware, including a failure after publishing the result but before healthy token publication. No transport retry.
- IPC v3: 14 tests; native inspector v3: 15; both already tested on XPS ARM64. Six systemd fixture invariants pass statically; all fixtures inert, no Install section, condition blocks startup, ExecStart=/usr/bin/true. systemd-analyze verify blocked in agent sandbox; no attempt to remove that sandbox. Native unit configuration and runtime isolation NOT_RUN.
- Independent M2 and M4 static review: PASS for laboratory only, not acceptance or installation. Final test and exact Git commit hashes recorded in PR / issue #58.

## Remaining gates

G-ID: actual xps-agent absent; both legacy MCP under owner UID 1000. New service credentials, per-connector isolation, loopback and abstract socket checks, retire both legacy access routes and test rollback. G-LEDGER: real root-owned report storage and rejected-frame durable logging, broker lifecycle incarnation, native failure scenarios. G-R0/G-THERM/G-AUDIT: real fixed adapters, independently supervised workers, root-owned installed code, bounded launch/recovery, actual security controls and native acceptance. No privileges enabled.

HUMAN_REQUIRED only after autonomous lab work: locally authenticated diagnostic migration, service credentials for both connectors, removal/revocation of old access after verification, reviewed installation and separate grant. Physical readiness required for R0. Do not run the obsolete v1 installer. No boot, firmware, Secure Boot, partition, experimental module or reboot action.
