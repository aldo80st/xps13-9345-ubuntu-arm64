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
