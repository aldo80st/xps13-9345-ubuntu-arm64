# XPS ARM64 — M2 Reproducible Kernel Kconfig Toolchain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans task by task. Use checkbox tasks and record evidence before success claims.

**Goal:** Reproduce the Ubuntu 7.3.0-10.10 ARM64 kernel Kconfig toolchain in an isolated container, ensure hibernation-only config changes, and document any residual drift without touching the installed kernel.

**Architecture:** Reuse existing Ubuntu 26.10 ARM64 Docker builder image as an optional cache; specify a reproducible Dockerfile with exact pinned package versions where practical and explicit provenance. Mount official Ubuntu source and separate candidate output read-write ONLY inside .local. Compare against /boot/config-7.3.0-10-generic read-only with scripts/audit-hibernate-config.py. Distinguish configuration equivalence from boot, suspend or resume support.

**Tech Stack:** Docker ARM64, Ubuntu 26.10 kernel source 7.3.0-10.10, GCC 15.3, Rust 1.97.1, Clang/LLVM 22, Bindgen 0.72.1, pahole 1.31, Python unittest, Git.

**Spec:** docs/superpowers/specs/2026-11-06-xps-hibernation-readiness-design.md

## Global Constraints

- Work in existing isolated worktree: /home/amarquez/labs/xps13-9345-hibernation, branch feat/hibernate-readiness-20261106.
- Never modify /boot, EFI, NVRAM, GRUB, initramfs, installed kernel, BIOS, Windows, BitLocker, swap, system package selection or host services. No reboot or hibernate.
- Docker build may create image/layers; sandboxed Docker containers mount only specific .local scratch and source read-only where possible, with no privileged mode or new Linux capabilities.
- No repo push, merge, PR, exposed credentials, sharing of XPS private data or download of proprietary firmware. Inputs are Ubuntu kernel config and official package sources only.
- Initial 50 unexpected symbols represent 68 diff lines; allowlist is deliberately narrow. Success requires **0 unrelated changed symbols**, with 8 expected hibernation changes and no parser errors. If not met, record residual and exact reasons, not forced options.
- Agent on STOLAS02 uses Claude Code for isolated code/docs; actual Kconfig run occurs on XPS where the source exists. No kernel build or install during M2.

## Review Focus

1. Host vs container compiler identity: preserve CONFIG_CC_VERSION_TEXT with explicit aarch64-linux-gnu-gcc instead of generic gcc.
2. Rust 1.97.1 + rust-src + bindgen and libclang: do not silently disable Rust-enabled modules.
3. pahole 1.31 + BTF module support: refuse success if tool not discovered.
4. LLVM 22 version/Clang flags: verify tool version by output and Kconfig, not assumed package existence.
5. Source and output mounts: Docker entrypoints must not write to live /boot nor kernel config, and on failure leave XPS unchanged.

### Task 1 — Claude Code on Paseo: reproducible Kconfig harness
**Files:** create scripts/hibernate-m2-config.sh, tests/test_hibernate_m2_harness.py, docs/hibernate-m2-toolchain.md; optional container/Dockerfile.hibernate-kconfig.
**Interface:** shell entrypoint accepts --source, --baseline, --output and --image and emits audit JSON, status with clear exit codes.
- [x] Write tests verifying read-only mounts, no privileged/system mutation, required tool versions, missing dependency failure and nonzero drift exit; run RED first.
- [x] Implement smallest safe Docker harness with non-root sandboxed Kconfig run and manifest/provenance logs in output.
- [x] Verify TDD GREEN, lint (bash -n), document actual commands and cleanup behavior.
- [x] Commit only independent implementation assets on STOLAS02 branch; do not push.

### Task 2 — XPS: build isolated dependency image and run
**Inputs:** official Ubuntu source and 7.3.0-10.10 config already in .local/kernel-source.
- [x] Confirm docker safety and base image/tool versions.
- [x] Create isolated builder layer with rust-src/bindgen/clang-22/pahole/flex/bison/m4 and no host apt install.
- [x] Run kernel olddefconfig with CC=aarch64-linux-gnu-gcc and necessary Rust env against scratch-only output; no full kernel build.
- [x] Execute scripts/audit-hibernate-config.py against baseline and candidate, record actual counts.
- [x] Retry only deterministic differences (tool detection/toolchain arguments) based on evidence, never hand-force Kconfig feature values.

### Task 3 — Close M2 with proof
- [x] Re-run full hibernation unittest suite.
- [x] Record status CLEAN (only if true) or BLOCKED with precise residual differences; update M2 doc.
- [x] Commit to local XPS branch only. Confirm original live kernel /sys/power/state and Git cleanliness.
- [x] M3 remains NO-GO for installation while Qualcomm P2 v2 vs shutdown v7 and remoteproc lifecycle lack proven integration.

## Evidence

At 2026-11-07 outset: XPS kernel 7.3.0-10-generic, Ubuntu 26.10 ARM64, 172 GiB free, Docker available, builder image xps-resources-arm64-builder:ubuntu26.10 present (Rust 1.97.1 GCC 15.3). Host lacks rustc, clang, bindgen, pahole; apt offers matching packages. Current candidate reports UNRELATED_DRIFT (8 expected, 50 unexpected). None of that is proof of runtime hibernation.

## Registro de cierre — 2026-11-07

- Paseo orquestó Claude Code en STOLAS02 y preparó el ejecutor Docker y sus pruebas; validación e integración realizadas después en el worktree XPS.
- Imagen ARM64 Docker `xps-hibernate-kconfig:ubuntu26.10` compilada y verificada localmente; herramientas en contenedor, sin `apt install` en el anfitrión.
- Segunda ejecución aislada `hibernate-m2-config.sh`: exit 0. `olddefconfig` conserva toda la configuración no relacionada con hibernación, excepto dos promociones LZ4 requeridas por dependencias Kconfig.
- Auditor sobre artefactos reales: CLEAN, 8 símbolos propios de hibernación, 2 dependencias LZ4, 0 no relacionados y 0 errores. `CONFIG_HIBERNATION=y` existe únicamente en `.local/m2-out/.config`.
- Revalidación al recuperar conexión: unittest 66/66 PASS; `bash -n` PASS; `py_compile` PASS; `git diff --check` PASS.
- Regla de reversibilidad: kernel 7.3.0-10-generic conserva `/sys/power/state = freeze mem`, no se instaló kernel, no se editó /boot, EFI, BIOS ni swap.
- M2 completado únicamente para Kconfig. La pila Qualcomm (PCIe v2 vs shutdown v7, SMP2P/remoteproc, periféricos) y respaldos/BitLocker requieren gate previo a M3 de kernel arrancable.
