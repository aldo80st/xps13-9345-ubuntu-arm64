# XPS-HIB-01 — Registro de ejecución GitHub y agentes

Epic: https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/21
Baseline merged PR #11 (CPU Oryon): https://github.com/aldo80st/xps13-9345-ubuntu-arm64/pull/11
Baseline merged PR #20 (Dell EC v8 + M1–M3): https://github.com/aldo80st/xps13-9345-ubuntu-arm64/pull/20

## Milestones e issues

| Milestone | Issues | Gate |
| --- | --- | --- |
| H0 Baseline | [#22](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/22) | M2 CLEAN y M3 REVIEW_REQUIRED evidenciados en main |
| H1 Qualcomm | [#23](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/23), [#24](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/24), [#25](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/25) | No saltar PCIe v2/v7 ni SMP2P/remoteproc |
| H2 Dell EC y SCMI | [#26](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/26), [#27](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/27) | Compilación y Kconfig, sin instalación; fan/termistores reales H4 |
| H3 Kernel alternativo | [#28](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/28) | Requiere H1 y H2 admitidos |
| H4 Arranque | [#29](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/29) | Requiere backup restaurable, clave BitLocker disponible y autorización |
| H5 Restore sesión | [#30](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/30) | Requiere H4, tres ciclos, EC/SCMI sin regresión |

## Primer ciclo de ejecución — 2026-11-07

- H1: Paseo en STOLAS02, Claude Code Sonnet 5.5, worktree `feat/xps-hib-h1-qualcomm-audit-20261107`, sesión de agente aislada. Investigación/manifest P1–P5, no kernel compilado en Raspberry.
- H2: Paseo en STOLAS02, Codex, worktree `feat/xps-hib-h2-ec-offline-build-20261107`. Harness de compilación aislada, TDD y docs; prueba de compilación real en Docker ARM64 sobre el XPS por integrador.
- Integrador: confirma de forma independiente salidas de agentes, prueba suite completa, opera GitHub PRs, no configura sistema ni arranca kernel.
- Estados H1/H2 deben actualizarse con evidencia de commit/PR y resultados concretos. **La creación de issues no significa que el milestone esté completo.**
- No fusionar PR #14/#16 GPU/NPU, PR #18 LLM, PR #19 Hexagon ni trabajos de otro subsistema como prerrequisito de hibernación.

## I0 — Integración upstream-first (2026-11-07)

- [ADR-0001](adr/ADR-0001-upstream-first-xps-hibernation.md): Canonical base, Dell Tributo referencia y Qualcomm fuente de correcciones, Omarchy/NixOS comparativas.
- [Registro Git fijado](hibernate-upstream-projects.lock.json): 4 referencias, URLs, ramas y SHA. Checker en `scripts/verify-hibernate-upstream-lock.py`; solo lectura, sin actualizaciones automáticas ni autorización de instalar.
- [Runbook](hibernate-upstream-onboarding.md), [contrato](superpowers/specs/2026-11-07-upstream-projects-integration-design.md) y [plan](superpowers/plans/2026-11-07-upstream-projects-integration.md).
- **I1 pendiente:** correspondencia exacta fuente Canonical → paquete 7.3.0-31.31 y revisión de annotations; el pin de Git NO demuestra identidad del paquete. I2 Dell y I3 Qualcomm pendientes.

## I1 — Auditoría de fuente Canonical PPA (2026-11-07)

- [Fuente exacta y evidencia](hibernate-canonical-source-i1.md) y [manifest de 8 hashes](hibernate-canonical-source-i1-evidence.json); `.dsc` de 7.3.0-31.31 y tar.gz verificado por SHA oficial.
- [Validador reproducible](../scripts/audit-canonical-source-i1.py) y [plan TDD](superpowers/plans/2026-11-07-canonical-source-i1.md): NO_GO aunque los hashes sean correctos porque CONFIG_HIBERNATION=n y faltan garantías de recuperación.
- DTS Dell y cinco controladores revisados son byte-idénticos a la fuente Ubuntu generic 7.3.0 en los seis archivos comparados. EC v8 no está incluido en fuente PPA.
- Firma del archivo fuente validada criptográficamente con clave pública del firmante, pero GPG `TRUST_UNDEFINED`; origen de commit Git↔tar de release no demostrado.
- **Siguiente gate #44**: auditar restauración PDC, clocks, PCIe, SMP2P/remoteproc sobre este archivo exacto, sin instalar kernel; I2 DTS/EC y H2 build offline aún pendientes.
