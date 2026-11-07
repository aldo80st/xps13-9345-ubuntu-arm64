# M1 — Candidato de kernel ARM64 para hibernación (investigación y preparación)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task by task. Steps use `- [ ]`. No installation or boot modification.

**Goal:** Identificar si existe una base de kernel candidata que soporte hibernación y preparar una variante aislada y trazable para Dell XPS 13 9345 sin sustituir el kernel de Ubuntu.

**Architecture:** Reproducir kernel Ubuntu 7.3.0-10.10 como baseline de fuente y examinar su configuración por separado. Registrar dependencias de las correcciones X1E80100 con referencias primarias; si alguna es incompleta, detener cualquier compilación para arranque y dejar sólo preparación en laboratorio.

**Tech Stack:** Git, Ubuntu apt .deb, dpkg-deb, tar, kernel Kconfig, Python unittest, documentación Markdown.

**Spec:** docs/superpowers/specs/2026-11-06-xps-hibernation-readiness-design.md

## Global Constraints

- No sudo, no instalación de paquetes, no tocar /boot, GRUB, EFI, dracut, BIOS, swap ni particiones.
- No empaquetar/instalar un kernel listo para uso diario sin dependencia integrada y pruebas comparables en Dell.
- No asumir que un parche accepted/applied en árbol del mantenedor está ya presente en mainline o Ubuntu.
- No copiar firmware propietario ni claves. No publicar ruta de usuario, serial/UUID, tokens, BitLocker, cmdline.
- El Debian .deb de fuente se descarga sólo en `.local/kernel-source/` ignorado por Git, con versión y hash reproducibles.

## Review Focus

- Paquete no coincidente con kernel instalado -> bloquear.
- Config con HIBERNATION=y sin parches de restauración X1E -> marcar experimental NO-GO.
- Estado upstream de PCIe con serie v7 más nueva -> no aplicar v2 sobre base v6 sin cotejo.
- Parche aprobado en árbol de mantenedor -> no declarar incluido en Ubuntu.
- Falta un compilador o dependencia -> registrar y no mutar paquetes del sistema.

### Task 1: Inventario de kernel y parches

**Files:**
- Create: docs/hibernate-kernel-m1.md
- Modify: docs/hibernation-arm64.md

**Interfaces:** produce matriz con enlace, fecha, estado y dependencia de cada parche, y una decisión GO/NO-GO.

- [x] Step 1: verificar kernel, Kconfig, candidatos apt y toolchain local con comandos de sólo lectura.
- [x] Step 2: rastrear evidencia upstream y distinguir accepted vs merged vs packaged.
- [x] Step 3: redactar tabla de variantes y decisión técnica; validar presencia de links, cinco subsistemas y etiquetas de incertidumbre.
- [x] Step 4: commit docs(xps): inventory X1E hibernation kernel blockers (c838fa2).

### Task 2: Preparar fuente Ubuntu en entorno aislado

**Files:** `.local/kernel-source/` (git-ignored), `docs/hibernate-kernel-m1.md`.

**Interfaces:** produce fuente Ubuntu con hash, versión, opciones Kconfig y límites de build; no modifica equipo.

- [x] Step 1: `apt download linux-source-7.3.0` para versión 7.3.0-10.10, sin install.
- [x] Step 2: comprobar versión con `dpkg-deb -f`, checksum SHA256 y `dpkg-deb -x` dentro de .local.
- [x] Step 3: extraer sólo fuente para examen, sin scripts de instalación. Identificar Kconfig y comparar configuración Ubuntu.
- [x] Step 4: generar `.config` aislado y validar `make olddefconfig` (PASS con flex/bison/m4 extraídos sin instalación). **Advertencia:** 68 líneas de opciones difieren de config Ubuntu por toolchain, no apto para build final.
- [x] Step 5: documentar limitaciones/resultado y dejar fuente reutilizable; nunca concluir booteabilidad.

### Task 3: Gate y verificación

**Files:** `docs/hibernate-kernel-m1.md`, plan y script de diagnóstico existente.

- [x] Step 1: correr suite de preflight y revisar matriz de parches; `git diff --check` sin errores (11/11 PASS).
- [x] Step 2: dejar gate de fase M2 en NO-GO mientras PCIe + restore y recuperación BitLocker sigan sin validación.
- [x] Step 3: commit docs(xps): record isolated kernel source inspection and decision (c838fa2).

## Stop conditions

Bloquear instalación/flasheo, cambios boot, pruebas de energía y archivos de swap. La meta de M1 es **candidato de laboratorio con trazabilidad**; su funcionalidad real en Dell no puede verificarse sin etapas posteriores autorizadas.

## Iteración delegada Paseo + Claude Code (2026-11-07)

- Paseo 0.15.2 en STOLAS02: proveedor Claude Code 2.1.318 se detectó, pero **falló por OAuth expirado** (sin ejecución); no se copiaron credenciales.
- Claude Code en XPS sí estaba autenticado y creó audit script/test/doc, pero su modo acceptEdits no pudo ejecutar Python ni leer /boot. No registró validación ni commit; se asumió la verificación directamente desde el XPS.
- Se añadió una regresión observada RED → GREEN: los símbolos Kconfig admiten minúsculas, p. ej. CONFIG_MT76x02_LIB. El analizador originalmente devolvía UNKNOWN para el kernel real.
- Verificación directa en XPS: **27/27 unittest PASS**, py_compile PASS, auditoría real **UNRELATED_DRIFT** (exit 1 esperado): 8 símbolos de hibernación, 50 ajenos, 0 errores de parseo; clasificación rust 26, bpf 6, pahole 2, compiler 1 (categorías parciales).
- Paseo en STOLAS02 ejecutó revisión de parches P1–P5 con Codex y creó docs/hibernate-patch-review-20261107.md (commit aislado STOLAS02 fbc4685ff059d7733ea013b16bd4f7d372041cc3). Se revisó y trasladó el informe al worktree XPS; el modelo no puede validar inclusión mainline/Ubuntu sin comprobar la ascendencia.
- NO-GO mantiene vigencia: resolver equivalencia de toolchain y serie PCIe v7 ↔ parche hibernación v2; validar remoteproc y firmware Dell; no instalar kernel ni cambiar boot/swap/EFI.
