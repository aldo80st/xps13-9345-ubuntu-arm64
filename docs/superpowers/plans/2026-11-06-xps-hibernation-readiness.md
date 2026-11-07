# XPS ARM64 Hibernate Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Diagnosticar y documentar prerequisitos para hibernación real sin cambiar la configuración de arranque actual.

**Architecture:** Herramienta Python read-only con fixture root para pruebas; informe limitado a campos no sensibles. Runbook separa bloqueos locales del firmware y trabajo upstream. Cualquier etapa de kernel/BIOS queda en gate separado.

**Tech Stack:** Python 3 stdlib, unittest, GRUB, Dracut, ext4, Ubuntu 26.10 ARM64.

**Spec:** docs/superpowers/specs/2026-11-06-xps-hibernation-readiness-design.md

## Global Constraints

- No sudo; no modificar EFI, BIOS, arranque, swap ni kernel durante esta iteración.
- No publicar cmdline completo, UUID, serial, MAC, IP, nombre de usuario ni claves.
- No intentar hibernación hasta que CONFIG_HIBERNATION=y, disk y pruebas de recuperación sean explícitas.
- El resultado UNKNOWN no debe confundirse con READY_FOR_EVALUATION.
- BitLocker y otras instalaciones quedan intactas. No push/merge automático.

## Review Focus

1. CONFIG_HIBERNATION deshabilitado aunque aparezca disk: BLOCKED.
2. CONFIG_HIBERNATION habilitado sin disk: BLOCKED.
3. Swap ilegible o vacío: UNKNOWN y nunca asumir memoria suficiente.
4. EFI configurado y EFI activo distintos: registrar ambas dimensiones sin inferir fallo firmware.
5. Identificadores sensibles en fixture: nunca incluirlos en salida JSON o texto.

---

### Task 1: Preflight sin privilegios

**Files:**
- Create: scripts/hibernate-preflight.py
- Create: tests/test_hibernate_preflight.py

**Interfaces:**
- Produces: inspect(root: pathlib.Path, kernel: str) -> dict; assess(observation: dict) -> dict; main() -> int.
- CLI: --root para fixture (default /), --kernel opcional, --json.

- [x] Step 1: tests unittest para bloqueos y casos READY_FOR_EVALUATION, UNKNOWN, identidad.
- [x] Step 2: correr python3 -m unittest discover -s tests -p test_hibernate_preflight.py -v; Expected FAIL (script aún ausente).
- [x] Step 3: implementar lectura no privilegiada de /boot/config-*, /sys/power/state, /proc/{meminfo,swaps,cmdline}, grub x1e settings; suprimir campos sensibles.
- [x] Step 4: repetir suite; Expected all PASS.
- [x] Step 5: correr python3 scripts/hibernate-preflight.py --json sobre el equipo; Expected BLOCKED kernel/no disk, swap deficit, efi noruntime.
- [x] Step 6: commit feat(xps): add read-only hibernation preflight.

### Task 2: Procedimiento y clasificación de tickets

**Files:**
- Create: docs/hibernation-arm64.md
- Modify: README.es.md

**Interfaces:** Consume informe de Task 1; produce runbook con criterios Dell/Canonical/Qualcomm.

- [x] Step 1: documentar preflight, peligros del swapfile y de reanudar desde diferente estado del FS.
- [x] Step 2: documentar pruebas/reversión y árbol de escalamiento: Ubuntu CONFIG_HIBERNATION; Dell sólo EFI Runtime reproducible; kernel/Qualcomm para restauración de drivers.
- [x] Step 3: enlazar guía desde README.es.md; Expected test -f docs/hibernation-arm64.md y grep de enlace exit 0.
- [x] Step 4: commit docs(xps): document ARM64 hibernation gates.

### Task 3: Evidencia y gate de siguiente milestone

**Files:**
- Modify: docs/hibernation-arm64.md

- [x] Step 1: registrar preflight observado y limitaciones.
- [x] Step 2: establecer qué se valida antes de actualizar BIOS o probar EFI Runtime o kernel nuevo.
- [x] Step 3: verificar que el runbook no instruye aplicar cambios automáticamente; Expected gate explícito.
- [x] Step 4: commit docs(xps): record hibernation decision gate.

## Hitos diferidos, no autorizados en esta ronda

M1: comparar parches Qualcomm con kernel Ubuntu y construir kernel alternativo trazable, sin sustituir kernel principal.
M2: validación de recuperación BitLocker, EFI, medio de rescate y pruebas de hardware con entrada de GRUB separada.
M3: dimensionar swap apropiadamente (~32 GiB como objetivo conservador, no mínimo universal), configurar resume/resume_offset y Dracut de modo reversible.
M4: realizar prueba real de hibernación y 3 ciclos íntegros sin regresiones de disco, gráficos, redes y periféricos.
M5: decidir escalamiento a Canonical o Dell con repro exacto; merge tras revisión.

## Acceptance

- python3 -m unittest discover -s tests -p test_hibernate_preflight.py -v → PASS.
- python3 scripts/hibernate-preflight.py --json → resultado BLOCKED coherente.
- git diff --check → PASS.
- Ningún archivo de /etc, /boot, swap, BIOS o arranque modificado.

## Registro de ejecución verificada (2026-11-06)

- Worktree: /home/amarquez/labs/xps13-9345-hibernation; rama: feat/hibernate-readiness-20261106; base: origin/main (5d8addf).
- Task 1: first test run failed because script did not exist; after implementation 9/9 PASS. Commit f016650.
- Task 2: runbook, clasificación de tickets, enlace README y verificaciones de archivos; commit 0061cfa.
- Task 3: criterios GO/NO-GO, reversión y autorización documentados en runbook; no se modificaron arranque/firmware/swap.
- Revisión posterior: dos nuevas pruebas se observaron fallar primero (estado de energía vacío e intento de atravesar rutas con kernel malformado), se corrigieron; 11/11 PASS. **No hay revisión independiente por subagente**.
- Verificación final ejecutada: python3 -m unittest discover -s tests -p test_hibernate_preflight.py -v (11 tests OK); python3 -m py_compile scripts/hibernate-preflight.py (exit 0); bash -n scripts/*.sh (exit 0); git diff --check (exit 0).
- Observación XPS: BLOCKED por kernel_config_disabled y disk_state_unavailable; warnings swap_below_ram_conservative_target y efi_runtime_disabled_at_boot.
- Gate siguiente: sin clave de recuperación BitLocker validada, respaldo verificable y confirmación de parches/kernel para XPS, **NO-GO para instalación/BIOS o hibernación real**.
- Deuda previa: shellcheck del script existente scripts/diagnose-readonly.sh emite SC1091 informativo (lectura /etc/os-release); no se modificó ese script.
