# XPS-HIB-01 — Upstream-first Hibernation Pivot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans, with TDD and an isolated worktree. Mark evidence, not intent.

**Goal:** Replace independently maintained Qualcomm kernel backports and packaging with Canonical's qcom-x1e maintained baseline plus upstream components, retaining Dell-only hardware proofs.

**Architecture:** Current XPS running kernel and boot remain untouched. Audit the prebuilt Canonical ARM64 buildinfo, then build a versioned manifest of upstream dependencies and enforce fail-closed NO_GO gates. Use Ubuntu Concept packaging and annotations for any future *lab-only* kernel candidate. No source replacement or boot changes in this milestone.

**Tech Stack:** Ubuntu Concept linux-qcom-x1e 7.3.0-31.31 PPA, Python stdlib, unittest, git worktrees, GitHub Issues/CI, Paseo Claude+Codex.

**Spec:** [Epic XPS-HIB-01](../specs/2026-11-07-xps-hibernation-epic.md); [tracking](../../hibernate-epic-tracking.md)

## Source-of-truth evidence (2026-11-07)

- Repo main at beginning of pivot: `dfb5de9` (merged H1 PCIe/remoteproc audit gates).
- XPS currently running `7.3.0-10-generic`; `/sys/power/state = freeze mem` without `disk`.
- **Canonical buildinfo inspected without installation:** `linux-buildinfo-7.3.0-31-qcom-x1e_7.3.0-31.31_arm64.deb`, SHA256 `120e3bd802af4f4c7a307b46b203662958d9c093a797e1e5cbd58dd39603136c`, release date 2026-10-27, package host `ppa.launchpadcontent.net`. Its extracted config has `# CONFIG_HIBERNATION is not set`. Also `CONFIG_SUSPEND=y`, `CONFIG_ARCH_HIBERNATION_POSSIBLE=y`, `CONFIG_ARM_SCMI_CPUFREQ=m`, `CONFIG_PCIE_QCOM=y`, `CONFIG_QCOM_SMP2P=m`, `CONFIG_QCOM_PDC=y`, `CONFIG_SWAP=y`.
- Official build procedure: https://discourse.ubuntu.com/t/how-to-build-your-own-ubuntu-concept-x-elite-kernel/49941/3 ; packages: https://launchpad.net/~ubuntu-concept/+archive/ubuntu/x1e . Kernel config via Canonical `debian.qcom-x1e/config/annotations` rather than unreviewed ad-hoc /boot changes.
- Dell-specific kernel support: https://github.com/alexVinarskis/linux-x1e80100-dell-tributo (suspend advertised, **not hibernation**).
- General Snapdragon X Elite work reports unsuccessful hibernation restore and patch proposals: https://github.com/omacom/omarchy/discussions/11823 . This does not establish success or failure on the Dell XPS 9345.

## Tasks and acceptance

### Task A — Audit existing qcom-x1e release (issue #39, H1)
- [x] Verify genuine ARM64 buildinfo provenance and `CONFIG_HIBERNATION` flag from downloaded official .deb without installing it.
- [ ] Agent Claude Code adds read-only config drift CLI, focused tests and docs.
- [ ] XPS integrator checks CLI against **real extracted** PPA config and live /boot config with fail-closed result (HIBERNATION_NOT_ENABLED); scan for SCMI/EC divergence.
- [ ] CI and second review; merge a single small PR. Close issue #39 only when verified audit is in main. No permission to install kernel.

### Task B — Reuse upstream patch series (issue #40, H1)
- [ ] Codex inventories existing PCIe/pinctrl/remoteproc/UART/BT work and newer Qualcomm PDC/GCC-clock restore proposals with exact primary references.
- [ ] Each component has status proposed, reviewed, merged upstream, shipped Ubuntu or unknown; **no status inferred from search snippets**.
- [ ] Fail-closed validator and tests; unknown PDC/clocks remain blockers until audited.
- [ ] CI and second review, PR merge. Close issue #40 when inventory is in main but **do not close H1**, since patch/resume engineering may still be required.

### Task C — Use maintained Ubuntu kernel instead of a forked base (future H2/H3)
- [ ] Compare Canonical qcom-x1e branch and annotations against generic, Dell EC v8 & DTB, and SCMI without altering boot.
- [ ] Reuse upstream patches as exact provenance-pinned inputs; avoid copying patch implementations without strong reason.
- [ ] Compile candidate offline using Canonical packaging; prove kernel Image/DTB/modules/Module.symvers/ABI and rollback prerequisites before H4.
- [ ] Stop if PCIe, PAS remoteproc, PDC, clocks or thermal contracts fail.

## Non-negotiable safety gate

No `apt install` kernel, BIOS/EFI/noruntime changes, GRUB/bootloader edit, initramfs/swap mutation, device suspend or reboot until there is a separate user-authorized H4 recovery plan (BitLocker key, reliable backup, rescue boot, alternate GRUB) and H1–H3 evidence. Current repository remains a laboratory and set of tests, **not** a verified working hibernation kernel.

**Design rule:** upstream-first minimizes lifetime maintenance; project-specific glue is justified only when an existing upstream solution demonstrably lacks Dell support.
