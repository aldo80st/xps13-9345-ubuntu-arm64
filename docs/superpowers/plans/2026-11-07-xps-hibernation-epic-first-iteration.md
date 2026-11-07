# XPS-HIB-01 — Primer ciclo H1/H2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Crear epic/milestones/issues auditables y ejecutar H1 revisión Qualcomm y H2 prueba build EC/DTB en paralelo.
**Architecture:** GitHub Issues y milestones como gestión; PRs, fuentes y tests como autoridad. Paseo/Claude Code investiga y desarrolla H1 con revisión Codex; XPS ejecuta H2 dentro Docker. Ninguna instalación del kernel.
**Tech Stack:** GitHub API/gh, Paseo, Claude Code, Codex, unittest, Docker Ubuntu 26.10 ARM64.
**Spec:** docs/superpowers/specs/2026-11-07-xps-hibernation-epic.md

## Global constraints
- No cambios /boot, GRUB, EFI, BIOS, swap, dracut, Secure Boot, kernel activo ni servicios o dispositivos físicos.
- STOLAS02 no construye kernel ni recibe volcado de 1.8GiB de código fuente.
- No declarar candidato apto por solo compilar; no push/merge de ramas no relacionadas como GPU/NPU.
- Cualquier falta de parche coherente mantiene NO_GO y se documenta.
- Salidas GitHub issues/PR incluyen criterios de aceptación y no datos privados.

## Review Focus
1. PCIe freeze v2 + shutdown v7 requiere rebase semántico, no aplicación textual arbitraria.
2. SMP2P/remoteproc no debe omitirse por aceptación de otros parches.
3. Config EC v8 + SCMI no equivale a DTB y módulo compilados.
4. Gate H4 requiere rescate, respaldo, BitLocker y autorización explícita.
5. Los estados proposed/accepted/mainline/Ubuntu han de permanecer distinguidos.

### Task 1 — Epic y milestones
Files: epic spec, esta planificación, docs/hibernate-epic-tracking.md, GitHub issues/milestones.
- [ ] Crear milestones H0–H5 y issue Epic con dependencias.
- [x] Crear issues vinculados por milestones, criterios de aceptación y precedencias (#22–#30).
- [x] Registrar URLs y estado en repo (docs/hibernate-epic-tracking.md).

### Task 2 — Paseo/Claude H1
Files: docs/hibernate-qualcomm-h1.md y tests o manifest estructurado si procede.
- [ ] Investigar y validar P1–P5 contra fuentes rastreables.
- [ ] Separar los bloqueos PCIe v2-v7 y SMP2P/remoteproc; no inventar commits.
- [ ] Revisar mediante agente independiente, correr tests y generar commit/PR de evidencia.

### Task 3 — XPS H2
Files: docs/hibernate-ec-build-h2.md y scripts / tests si proceden.
- [ ] Preparar build del EC v8 y DTS sobre copia de fuentes en Docker sin alterar sistema.
- [ ] Verificar Kconfig, compilación, tipo/ABI de artefacto, hashes y gate de SCMI.
- [ ] Si falla, corregir un problema reproducible y registrar evidencia, sin pretender H3.

### Task 4 — Consolidación
- [ ] Repetir suite completa y review de diff.
- [ ] PRs pequeñas y merge solo con CI y validación, sin instalar.
- [ ] Actualizar issues/milestones, dejar H3 bloqueado hasta evidencia H1+H2.
