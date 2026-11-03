# Sprint Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ejecutar ocho frentes de diagnóstico seguro, producir evidencia privada y decisiones públicas conservadoras, y detenerse con causa explícita.

**Architecture:** Un módulo separa adquisición por lista blanca, evaluación pura y persistencia. La evaluación no convierte enumeración en funcionalidad. El loop usa huellas de evidencia estable y acciones pendientes únicas; los checkpoints completos permiten reanudar una nueva invocación sin perder rondas.

**Tech Stack:** Python 3 stdlib, unittest; herramientas locales opcionales, sin instalaciones.

**Spec:** docs/superpowers/specs/2026-11-01-sprint-cycle.md

## Global Constraints

- Máximo 6 rondas por invocación y 20s por comando; no bucles infinitos ni acciones repetidas idénticas.
- No escribir en /etc, /usr, /lib/firmware, /boot, /sys, systemd global, módulos del kernel ni invocar sudo/pkexec.
- No publicar secretos, tokens, logs crudos, datos identificadores ni contenido de /proc/keys.
- No activar amplificadores sin protección; evitar parámetros `i_accept_the_danger`, volumen forzado o audio peligroso.
- No reiniciar computadora, Docker, red, agente Desktop Commander ni interfaces vitales.
- Gate vinculante: docs/sprint-2026-11-01-upstream-solutions-review.md. Su investigación es un snapshot, no prueba actual de Fix Released.
- Solo este worktree y rama sprint/superpowers-cycle-20261101; no push ni merge.

## Review Focus

- Herramientas ausentes, permisos denegados o timeout: datos desconocidos, nunca VERIFIED por defecto.
- Salida con hostnames, secretos o rutas: publicar únicamente hechos tipados de lista blanca, nunca texto arbitrario.
- Symlinks y output-dir externo: rechazar antes de escribir; JSON 0600 y directorios 0700.
- Interrupción/checkpoint corrupto: no sobrescribir evidencia, fallo explícito y nueva secuencia verificable.
- Enumeración y evidencia antigua: exigir prueba funcional actual, preservar hipótesis y alcance limitado.

### Task 1: Diagnóstico y clasificación de los ocho frentes

**Files:** Create `tests/__init__.py`, `tests/test_sprint_cycle.py`, `scripts/sprint_cycle.py`.

**Interfaces:** `command(name: str) -> dict`, `collect() -> dict`, `evaluate(facts: dict) -> list[dict]`. Los resultados de comandos solo viven en memoria; collect devuelve tipos seguros y hashes, no logs. evaluate produce issue, estado, decisión, ADR, evidencia, acción humana y criterio.

- [ ] Escribir pruebas antes del módulo: falta de evidencia bloquea; dock no valida monitores; IRIS requiere decode sintético hardware con EOS; pd-mapper exige activo, mapas base, overlay ausente y SHA oficial; audio/EC/BIOS bloqueados sin prueba segura; Adreno NOT_PLANNED.
- [ ] Añadir tests para comando no autorizado, timeout y herramienta ausente; fake de adquisición exclusivamente en frontera subprocess/sistema.
- [ ] Ejecutar `python3 -m unittest discover -v`; observar RED por módulo ausente mediante aserción explícita.
- [ ] Implementar whitelist exacta, subprocess sin shell con timeout de 20s y terminación del grupo propio; lectura acotada de rutas fijas. Un ensayo IRIS de 3 buffers, 64x64, fakesink, solo si encoder, parser y decoder V4L2 están disponibles. No tocar altavoces ni sesiones.
- [ ] Ejecutar la suite y verificar GREEN; refactorizar únicamente en verde.
- [ ] Commit con tests y motor después de verificación.

### Task 2: Loop, checkpoints, CLI y ejecución real

**Files:** Extend `tests/test_sprint_cycle.py`, `scripts/sprint_cycle.py`; create `docs/sprint-cycle-method.md`, `docs/sprint-cycles/2026-11-01-validation.md` y reportes redactados.

**Interfaces:** consume `collect/evaluate`; produce `run(root: Path, output_dir: Path, max_rounds: int, once: bool, collector=collect) -> dict`, `main(argv=None) -> int`. JSON incluye schema, secuencia, timestamps UTC, hashes de gate/spec, etapas ordenadas, facts, issues, fingerprint, stop_reason y checkpoint de acciones.

- [ ] Tests RED: --once una ronda; --run repite ante acción segura nueva, stop por convergencia, dos rondas sin progreso, tope 6, límites inválidos; reanudación preserva historial; JSON privado y resumen sin datos inyectados; rechazar symlink/output externo y checkpoint malformado.
- [ ] Ejecutar suite y observar fallos de comportamiento antes de implementar.
- [ ] Implementar persistencia atómica en `.local/sprint-cycles/iterations/`, Markdown por secuencia en `docs/sprint-cycles/`, sin texto crudo; lock de invocación y directorios privados. No reejecutar acción idéntica sin nueva evidencia.
- [ ] Documentar límites, alcance de VERIFIED, CLI y reanudación; ejecutar unittest GREEN.
- [ ] Ejecutar realmente `python3 scripts/sprint_cycle.py --run`; inspeccionar JSON local sin publicar identificadores y guardar resumen.
- [ ] Verificar `python3 -m unittest discover -v`, `bash -n` para cada `scripts/*.sh`, `git diff --check`, privacidad y permisos. Esperado: exit 0 y ocho frentes por ronda.
- [ ] Revisión crítica fresca del cambio completo según executing-plans, corregir hallazgos con RED/GREEN, registrar limitaciones y resultados; commit final en esta rama.

## Decisiones y seguimiento

El usuario ya aprobó spec y ejecución continua: se omite el gate de nueva aprobación del plan. No hay cambios globales autorizados. No consultar credenciales ni claves. La recuperación tras una interrupción usa snapshots completos y numerados; un checkpoint corrupto falla sin sobreescritura. Lo no confirmado upstream permanece BLOCKED_UPSTREAM, nunca WAITING_RELEASE por inferencia.
