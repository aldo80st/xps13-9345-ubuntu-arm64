# M3 Thermal × Hibernate Compatibility Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materializar matriz de compatibilidad y gate no destructivo que impida perder Dell EC v8 y SCMI cpufreq al preparar un kernel ARM64 de hibernación.

**Architecture:** Matriz humana en docs y validador Python stdlib de rutas de entrada explícitas. El validador lee únicamente fuente/config/patches, expone razones no sensibles y distingue NO_GO de REVIEW_REQUIRED (nunca GO autorizado).

**Tech Stack:** Python 3.14 stdlib, unittest, kernel Kconfig, fuentes Linux, SHA256, Markdown.

**Spec:** docs/superpowers/specs/2026-11-07-m3-thermal-hibernate-contract.md

## Global constraints

- Sin sudo, cambios del host, push, merge, pruebas de energía, cambios /boot, GRUB, EFI, BIOS, swap, kernel, EC, cpufreq ni ramas térmicas.
- No publicar rutas absolutas locales, seriales, UUID, clave BitLocker, MAC ni cmdline completa.
- El diagnóstico no demuestra que un kernel pueda arrancar ni hibernar. `REVIEW_REQUIRED` no constituye aprobación.
- No autocorregir opciones ni aplicar parches. Patches SHA son procedencia, no firmas de autenticidad upstream.

## Review focus

1. Candidato tiene hibernación y SCMI, pero no EC/DT: NO_GO.
2. Se agregó driver EC pero CONFIG_EC_DELL_XPS no habilitado: NO_GO.
3. CONFIG_ARM_SCMI_CPUFREQ u otros cuatro símbolos pierden su valor: NO_GO.
4. Parches EC tienen hash distinto/faltan: NO_GO, nunca autoseleccionar.
5. Todas las señales estáticas presentes: REVIEW_REQUIRED, no GO; sin pruebas de restauración.

### Task 1 — Matriz y contrato con fuentes comprobadas

**Files:** docs/superpowers/specs/2026-11-07-m3-thermal-hibernate-contract.md; docs/hibernate-thermal-m3.md; docs/superpowers/plans/2026-11-07-m3-thermal-hibernate-gate.md.

- [x] Capturar evidencia EC, Device Tree, cpu frequency, GRUB experimental y hashes.
- [x] Añadir matriz de compatibilidad y secuencia de integración sin fusionar worktrees.
- [x] Registrar riesgos de PM `SYSTEM_SLEEP_PM_OPS` para freeze/thaw y poweroff/restore.

### Task 2 — Gate estático con TDD

**Files:** scripts/hibernate-thermal-m3-gate.py; tests/test_hibernate_thermal_m3_gate.py.

- [x] Tests fixtures para los 5 Review Focus y no filtración de rutas. **Expected RED** por script ausente.
- [x] Implementar `inspect(source_tree: Path, baseline: Path, candidate: Path, patches_dir: Path) -> dict`; cli `--source-tree --baseline --candidate --ec-patches --json`.
- [x] Tests `python3 -m unittest discover -s tests -p test_hibernate_thermal_m3_gate.py -v`. **Expected GREEN**.
- [x] Ejecutar sobre fuente Ubuntu y archivos M2 reales. **Expected NO_GO**: no EC integrado y config EC ausente, aunque SCMI se conserve.

### Task 3 — Consolidación y verificación

**Files:** docs/hibernation-arm64.md, docs/hibernate-thermal-m3.md, README.es.md, plan.

- [x] Enlazar contrato y matriz en documentación existente.
- [x] Verificar suite completa + auditor M2 CLEAN + gate M3 NO_GO razonado.
- [x] Comprobar host intacto, diff check, commit local en rama aislada sin merge/push.
- [x] Dejar señaladas dependencias P1–P5 y experimental EC v8, sin instalar kernel.

## Ejecución verificable — 2026-11-07

- Se inspeccionaron el árbol Ubuntu 7.3 de M2, configuración actual y experimental, la sesión EC v8 con `xps_ec_trial=20261107-stubble` y los 3 parches EC v8. Se verificaron SHA256 de cada parche y los símbolos SCMI/cpufreq existentes.
- TDD: suite inicial no podía importar `scripts/hibernate-thermal-m3-gate.py` (RED); después 14/14 nuevos tests verdes, incluidos EC ausente, Kconfig sin EC, degradación SCMI, Device Tree ausente, callbacks PM, hashes cambiados y seguridad de la salida.
- Gate contra archivos XPS: `NO_GO` (exit 1 esperado), `approval=not_authorized`. Hibernación M2, SCMI y procedencia EC válidos; faltan `CONFIG_EC_DELL_XPS`, driver/PM, binding, Kconfig/Makefile y DT Dell en fuente Ubuntu.
- Suite global `python3 -m unittest discover -s tests -p 'test_*hibernate*.py' -q` → 80 tests OK. Auditor M2 sigue `CLEAN` y `git diff --check` PASS.
- No se modificó /boot, EFI/GRUB, kernel cargado, BIOS, swap, política de energía, valores cpufreq, módulo o DTB EC, ni ninguna rama/worktree térmica. Kernel operativo `7.3.0-10-generic` con `/sys/power/state = freeze mem` (sin hibernación real).
- Integración de EC v8 y parches Qualcomm en un futuro árbol de kernel **no realizada** en este hito: queda explícitamente bloqueada detrás del gate y revisión técnica; no hubo merge, push, PR ni despliegue.
