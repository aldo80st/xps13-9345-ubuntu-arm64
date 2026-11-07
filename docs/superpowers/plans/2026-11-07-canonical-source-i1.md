# I1 — Canonical exact source package admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps are scoped to a safe read-only lab milestone and use checkbox tracking.

**Goal:** Make the exact Canonical Ubuntu Concept `linux-qcom-x1e 7.3.0-31.31` source reproducibly auditable, without implying it has working hibernation.

**Architecture:** Verify source tar SHA256 against the official `.dsc`, inspect only selected archive members without extracting code, compare Canonical arm64 annotations with released ARM64 buildinfo and preserve all existing NO_GO gates. Hardware kernel, firmware and boot are untouched.

**Tech Stack:** Python 3 stdlib, unittest, tarfile streaming, hashlib, Debian `.dsc`, Ubuntu annotations, GitHub CI.

**Spec:** [ADR-0001](../../adr/ADR-0001-upstream-first-xps-hibernation.md), [Integration spec](../specs/2026-11-07-upstream-projects-integration-design.md).

## Global Constraints

- All downloads and source checks stay in `.local`, ignored by Git. Publish only provenance, digests, documentation and tests.
- No kernel installation or changes to `/boot`, `/lib/modules`, GRUB, EFI, BIOS, swap, Dell EC/SCMI or reboot.
- Cryptographic digest matching against `.dsc` and GPG signer verification with untrusted key do not prove binary reproducibility or Git commit ancestry.
- Do not import Dell Tributo code while SPDX/license and semantic applicability remain unresolved.
- An annotations/config match does **not** authorize H4/H5; PCIe, PAS/SMP2P, PDC/clocks are independently blocked.

## Review Focus

1. Tampered source tarball → refuse even if the file is a valid compressed archive; test `test_tampered_archive_fails`.
2. Mismatch in package identity/release → refuse; tests `test_wrong_source_package_fails`, `test_wrong_release_fails`.
3. Missing Dell DTS or annotations → refuse; tests `test_missing_dts_fails_closed` and `test_missing_annotations_fails_closed`.
4. Divergent annotations/buildinfo configuration → refuse, including SCMI and SMP2P; tests `test_source_and_binary_config_disagreement_fails`, `test_smp2p_config_drift_fails`.
5. Enabled CONFIG_HIBERNATION without hardware PM restore → still NO_GO; test `test_annotations_enable_does_not_mean_restore`.

### Task 1 — Admit the exact source archive

**Files:** `docs/hibernate-canonical-source-i1.md` and `docs/hibernate-canonical-source-i1-evidence.json`; tar and `.dsc` stay under `.local/source-audit`.

- [x] Download `.dsc` and source tar from PPA; sha256 archive equals declaration `41e6c1e13aa14a6c4bc66f8e8faa33d6364eb309fa8f8c726a1e0ebee84a4051`.
- [x] Read actual changelog `7.3.0-31.31`, Debian qcom annotations, XPS DTS and six Qualcomm/Dell target files.
- [x] Compare 5 critical annotations with buildinfo ARM64, `CONFIG_HIBERNATION=n`.
- [x] Signer key downloaded into isolated keyring, `VALIDSIG` with `TRUST_UNDEFINED`; do not claim full trust.
- [x] Record absent Dell EC source and identical SHA for six kernel files compared with generic 7.3.0.

### Task 2 — Fail-closed reusable source audit

**Files:** `scripts/audit-canonical-source-i1.py`, `tests/test_audit_canonical_source_i1.py`.

**Interfaces:** `audit(dsc:Path, archive:Path, config:Path)->dict`; CLI `--dsc --tarball --buildinfo-config --json`. A valid source with unverified restore returns NO_GO exit 1; invalid input exits 2.

- [x] Write tests and prove RED with missing implementation.
- [x] Implement source digest/version/entry inspection and annotation cross-check without executing or extracting code.
- [x] Run 12 focused tests GREEN and apply against real PPA `7.3.0-31.31` with expected NO_GO.
- [ ] Execute entire regression suite, `py_compile`, Bash syntax, JSON validation and `git diff --check`; commit then PR + CI.
- [ ] Merge only if CI passes; post-merge full suite verifies the same NO_GO conditions.

### Task 3 — Dell source delta classification

**Files:** `docs/hibernate-canonical-source-i1.md`; staging scratch `.local/dell-patch-check`.

- [x] Confirm Dell Tributo remote SHA `2c5a57875dc4bc62e179a785e290a91bebfde2c6`.
- [x] Compare the two historical DTS patches with the exact Canonical XPS DTS using strict, no-write forward/reverse dry runs.
- [x] Record neither directly applicable/reversible; do not infer patch inclusion and do not import unlicensed code.
- [ ] Next I2 branch: semantic DTS differences, EC v8 and SCMI contract reviewed against this exact version.

### Task 4 — Continue rather than declaring I1 complete

- [ ] Resolve source Git SHA ↔ PPA release lineage and establish archive signer's trust chain (not simply `GOODSIG`).
- [ ] Issue #44: PDC/clocks/PCIe/remoteproc inclusion and PM restores audited against this exact source, not `resolute-x1e` HEAD.
- [ ] Issue #45: Canonical packaging and optional EC v8/DTB offline build only after H1 gates; do not boot.

**Done criterion for this turn:** source integrity, diff and tests archived in `main` by reviewed PR, with a concise list of remaining blockers. **Not a working hibernation kernel.**
