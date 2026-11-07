# EPIC XPS-HIB-01 — Hibernación ARM64 sin regresiones Dell EC ni SCMI

Fecha: 2026-11-07. Repositorio: aldo80st/xps13-9345-ubuntu-arm64. Estado: H0 alcanzado a nivel laboratorio; H1/H2 ejecutables en paralelo.

## Objetivo observable
Restaurar la MISMA sesión de Ubuntu 26.10 ARM64 después de hibernar/apagar el Dell XPS 13 9345, conservando control térmico Dell EC v8, ventiladores/termistores, SCMI CPUFreq, NVMe y todos los subsistemas Qualcomm. Proteger arranque dual Windows + BitLocker y ofrecer rollback.

CONFIG_HIBERNATION=y, compilación o /sys/power/state=disk NO prueban restauración funcional.

## Evidencia inicial
- GitHub PR #11 (métricas Qualcomm) y PR #20 (hibernación M1–M3 + EC v8) fusionadas a main, SHA 6afc093.
- Kernel activo 7.3.0-10-generic; hibernación no habilitada. Controlador Dell EC v8 activo en entrada experimental separada; SCMI CPUFreq y ondemand en tres grupos.
- Fuente Ubuntu 7.3.0-10.10, Docker Ubuntu 26.10 con GCC15 Rust1.97 LLVM22, M2 auditor CLEAN (8 símbolos directos + 2 dependencias LZ4); M3 en fuente integrada REVIEW_REQUIRED (10/10 checks estáticos). Ningún kernel alternativo booteado.
- La NAS degradada no es respaldo único fiable. Las claves BitLocker deben permanecer bajo control del usuario.

## Milestones de GitHub

| Hito | Entregable y prueba de aceptación | Estado |
| --- | --- | --- |
| H0 — Baseline y herramientas | M2 Kconfig CLEAN; M3 fuente EC v8/SCMI REVIEW_REQUIRED; código, pruebas, docs integrados en main | Completo en laboratorio |
| H1 — Pila Qualcomm | Matriz P1 pinctrl, P2 PCIe, P2a shutdown, P3 smp2p, P4 UART, P5 Bluetooth con estado upstream/Ubuntu, SHA y resolución PCIe v2 vs shutdown v7; pruebas de aplicación o NO_GO fundamentado | Pendiente |
| H2 — EC/SCMI/DTB compilables | Compilar EC módulo y DTB en imagen Docker aislada; probar Kconfig sin regresiones; hashes y artefactos locales; nunca instalar | Pendiente |
| H3 — Kernel alternativo reproducible | Kernel ARM64 + DTB + módulos + initramfs como paquetes no instalados; tests offline; H1 y H2 sin bloqueos críticos | Bloqueado H1/H2 |
| H4 — Arranque experimental controlado | Respaldo restaurable, clave BitLocker a mano, USB rescate, GRUB rollback, consentimiento específico; probar arranque y dispositivos/EC/SCMI | Bloqueado por autorización |
| H5 — Hibernación y restauración real | 3 ciclos controlados, misma sesión recuperada, térmica/ventiladores, frecuencias, periféricos y almacenamiento correctos, documentación y rollback | Bloqueado H4 |

## Agentes y límites
- Paseo / Claude Code STOLAS02: investigación de patches y herramientas manifest H1, unidades TDD. No construir kernel pesado en Raspberry de 4 GiB.
- Paseo / Codex: revisar dependencias PCIe shutdown v7 y smp2p/remoteproc, verificar independencia técnica, revisar diff/seguridad.
- Integrador XPS: usar Docker ARM64 aislado para build H2/H3; mantener cada tarea en worktree/branch normalizada, pruebas completas antes de PR.
- Usuario: únicamente para H4–H5, con respaldo y clave BitLocker local, autorización de instalación y arranque.

No modificar EFI/noruntime, BIOS, swap, dracut, Secure Boot, GRUB, kernel activo ni procesos térmicos durante H0–H3. No aplicar parches semánticamente incompatibles solo porque patch --dry-run pase. No mezclar las PRs GPU/NPU encadenadas con el epic. El commit a main no despliega un kernel.

## Dependencias y definición de terminado
H0 precede H1/H2. H1 y H2 paralelos, ambos son requisito para H3. H3 y recuperación satisfactoria preceden H4. H4 precede H5.

El epic cierra SOLO con hibernación real y restauración de la misma sesión en tres ciclos, control térmico/SCMI/periféricos comprobados, posibilidad de rollback probada y documentación sin secretos.
