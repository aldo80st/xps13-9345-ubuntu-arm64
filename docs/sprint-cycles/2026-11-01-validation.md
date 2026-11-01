# Validación del ciclo Superpowers — 2026-11-01

## Ejecución observada

Codex CLI 0.166.0 con Superpowers 7.0.1 en un worktree aislado. Las pruebas fueron escritas antes de la implementación (RED inicial: 9 tests; después RED: 10 tests de loop; regresiones RED para caché y seguridad de IRIS). Validación final fuera del sandbox: **22 pruebas unitarias PASS**, `python3 -m py_compile scripts/sprint_cycle.py` PASS, `bash -n scripts/*.sh` PASS y `git diff --check` PASS.

**Cuatro checkpoints privados** en el sistema original, en `.local/sprint-cycles/iterations`. No publicar esos JSON: contienen metadatos privados como boot ID.

| Iteración | Entorno | Resultado | Interpretación |
| --- | --- | --- | --- |
| 000001 | Codex sandbox de workspace | `external_actions_only` | **No usar como evidencia del sistema:** sandbox bloqueaba consultas systemd, USB y GStreamer; algunos campos fueron `unknown`. |
| 000002 | Desktop Commander, acceso normal sin privilegios | `external_actions_only` | Lectura fiable de `pd-mapper`, dock, firma, Secure Boot, Desktop Commander. |
| 000003 | Desktop Commander tras corregir caché privada GStreamer | `external_actions_only` | Plugin V4L2 ya detectable; el ensayo H.264 sintético no completó EOS. |
| 000004 | Desktop Commander con prueba activa IRIS deshabilitada | `external_actions_only` | Sin nuevos ensayos potencialmente inestables de VPU; sistema continúa accesible. |

## Resultados precisos por componente

- **#1 EVDI/DisplayLink:** Secure Boot habilitado, dock D6000 por USB, módulo EVDI firmado y `vermagic` correcto. El kernel sigue rechazando la carga: **no resuelto**. La mera firma no prueba confianza MOK; inspeccionar `.machine`/`.platform` requiere acceso administrativo. Ubuntu LP #2131181 tiene parche pero su presencia en el kernel actual no fue verificada.
- **#2 Qualcomm IRIS:** firmware oficial `qcvss8380.mbn` íntegro; el kernel expone decoder V4L2, pero los intentos de decodificación H.264 terminan en `not-negotiated`. Durante este arranque también se observaron errores de sesión fatal `0x4000003` del driver. **No verificado y no apto para reintentos automatizados**; la relación causal entre estos errores y cada intento todavía necesita investigación.
- **#3 Térmico/EC:** sensores presentes, no se aplicó driver EC experimental. La serie v8 sigue como referencia; los datos pasivos **no validan regulación dinámica de ventiladores**.
- **#4 Audio:** no se modificaron topologías ni se activaron amplificadores. Falta demostrar protección de altavoces antes de pruebas acústicas.
- **#5 BIOS:** 2.14.0; no actualizado. El salto de versión requiere BitLocker y aprobación.
- **#6 Desktop Commander:** servicio de usuario activo, una instancia; falta prueba independiente de persistencia tras un nuevo reinicio.
- **#7 pd-mapper:** **VERIFIED** dentro del alcance de la regresión previa. Servicio activo, mapas `.jsn` presentes, overlay eliminado, firmware Dell con SHA-256 esperado.
- **#8 Adreno:** no planificado por comportamiento documentado de reintento exitoso.

## Interacciones o dependencias restantes

1. **Permisos administrativos:** lectura de keyrings del kernel, contraste de parche Canonical y posible actualización a kernel firmado si Canonical ya la distribuye. No modificar MOK/EFI hasta contar con diagnóstico y autorización.
2. **Prueba física DisplayLink:** verificar ambas pantallas DisplayPort; posible HDMI Alt Mode para una salida provisional.
3. **Investigación de IRIS:** no repetir pruebas de decodificación a ciegas tras detectar errores fatales del driver; esperar técnica reproducible sin bloqueo o corrección upstream.
4. **Audio/EC:** validar protección del amplificador y disponibilidad de driver térmico en kernel oficial antes de modificar.
5. **Reinicio supervisado:** comprobar persistencia de Desktop Commander cuando el usuario pueda reiniciar con seguridad.
6. **BIOS:** solo con aceptación explícita y clave de recuperación BitLocker disponible localmente.

La prueba y la evidencia son independientes de la cantidad de iteraciones. **No se ha cerrado el sprint global**.
