# XPS-HIB-01 — Integración upstream-first Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Formalizar e implementar la integración entre Canonical, Dell, Qualcomm y referencias comunitarias con versiones verificables y sin alterar el XPS operativo.

**Architecture:** Registro de fuentes Git fijadas por SHA separado del manifiesto de parches Qualcomm. Gate read-only con validación de procedencia, detección de drift remoto y prohibición explícita de instalación; las comparativas quedan fuera del grafo de build.

**Tech Stack:** Git/Launchpad/GitHub, Ubuntu ARM64, Python stdlib unittest, CI GitHub Actions, git worktrees, scripts existentes de auditoría Canonical y Qualcomm.

**Spec:** `docs/superpowers/specs/2026-11-07-upstream-projects-integration-design.md`

## Global Constraints

- Mantener `7.3.0-10-generic`, EC activo, GRUB, EFI, `efi=noruntime`, BIOS, swap e initramfs sin modificaciones.
- Todo staging de código externo bajo `.local` ignorado; no importar terceros sin licencia y procedencia.
- El SHA de `resolute-x1e` **no** demuestra equivalencia con el binario PPA `7.3.0-31.31`.
- Omarchy y NixOS: solo referencias; no instalar sus sistemas, scripts ni paquetes.
- No permitir que cambios en ramas remotas actualicen los pins o autoricen boot.

## Review Focus

1. **Mutable branch HEAD:** verificar SHA, marcar drift y no mutar lock automáticamente (prueba `test_remote_branch_drift_blocks`).
2. **Source-swap malicioso:** URL/identidad/ref/rol cambian → rechazo (pruebas de remote y role).
3. **Manifest ambiguo:** duplicados, SHA corto, gates retirados → rechazo (pruebas de invalidación).
4. **Licencia/atribución:** referencia Dell sin licencia confirmada → no importar código; inspección documental de la fuente.
5. **Falso READY:** una referencia Git válida no significa que Hibernate, packaging ABI ni recuperación funcionen (test `test_offline_lock_valid_but_never_boot_authorized`).

### Task 1 — Regla arquitectónica y fuente de verdad

**Files:** `docs/adr/ADR-0001-upstream-first-xps-hibernation.md`, `docs/superpowers/specs/2026-11-07-upstream-projects-integration-design.md`, `docs/hibernate-upstream-projects.lock.json`.

- [x] **Step 1:** Registrar las cuatro fuentes con roles explícitos (Canonical base, Dell referencia hardware, Omarchy/NixOS comparativas).
- [x] **Step 2:** Consultar refs remotas en XPS y fijar SHA sin clonar fuente del kernel completo.
- [x] **Step 3:** ADR y contrato separados del inventario Qualcomm existente; desconocida identidad source ↔ paquete.
- [ ] **Step 4:** Revisar y fusionar PR del ADR + contrato, con CI.

### Task 2 — Verificador de origen y cambio

**Files:** `scripts/verify-hibernate-upstream-lock.py`, `tests/test_verify_hibernate_upstream_lock.py`.

**Interfaces:** `load_manifest(path: Path) -> dict`; `evaluate(manifest: dict, check_remote: bool) -> dict`; CLI `--manifest`, `--check-remote`, `--json`.

- [x] **Step 1:** Crear tests RED por ausencia de implementación.
- [x] **Step 2:** Implementar validación de fuentes allowlist, roles y gates; comparación read-only `git ls-remote`.
- [x] **Step 3:** Tests GREEN: 13 tests; suite completa 202/202 (2 omitidas).
- [x] **Step 4:** Ejecutar auditoría remota XPS `PIN_MATCH` para las cuatro fuentes; `install_authorized=false`.
- [ ] **Step 5:** PR + CI + merge; verificar postmerge.

### Task 3 — Primer staging Dell y contrato de procedencia

**Files:** `docs/hibernate-upstream-onboarding.md` y staging privado `.local/upstreams/dell-tributo`.

- [x] **Step 1:** Clonar únicamente el repositorio Dell Tributo en `.local` y comparar SHA con el pin.
- [x] **Step 2:** Identificar que su historial está probado sobre `linux-next 2025-05-21`, EC WIP y no demuestra hibernación.
- [x] **Step 3:** Registrar ausencia de licencia raíz identificable; no importar código del Dell en main en este hito.
- [ ] **Step 4:** Buscar delta exacto contra `resolute-x1e` y paquete Canonical en una tarea sucesora.

### Task 4 — Siguiente milestone de integración real Canonical

**Files futuros:** nueva rama para fuente/annotations/paquetes, artefactos solo bajo `.local`.

- [ ] **Step 1:** Comprobar commit exacto de fuente Canonical utilizado para PPA `7.3.0-31.31`, no inferirlo del HEAD móvil.
- [ ] **Step 2:** Preparar árbol fuente reproducible/eficiente, revisar annotations, Dell DTS y driver EC v8.
- [ ] **Step 3:** Cruzar manifiesto Qualcomm con inclusión exacta de PDC/clocks/PCIe/PAS, sin recrear parches existentes.
- [ ] **Step 4:** Compilar variante offline si las dependencias y gates lo permiten. **No instalar ni arrancar kernel**.

### Task 5 — Consolidación e informes

- [ ] **Step 1:** Test suite completa, check de sintaxis y `git diff --check`.
- [ ] **Step 2:** Abrir PR, esperar checks, fusionar, revalidar sobre `main`.
- [ ] **Step 3:** Actualizar Epic #21, enlazar issue sucesor y explicar limitaciones de hardware.

**Definition of done de esta iteración:** I0 integrado en `main`, SHA de cuatro fuentes verificados, gates de modificación probados y plan para obtener fuente Canonical exacta. El **Epic H0–H5 no se declara terminado**.
