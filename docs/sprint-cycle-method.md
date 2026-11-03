# Método Superpowers: sprint iterativo, verificable y reanudable

**Modelo de trabajo:** brainstorming/spec aprobada → plan concreto → TDD RED/GREEN → depuración sistemática → revisión → verificación → checkpoint. La implementación se apoya en Superpowers **7.0.1** instalado en Codex, pero el ejecutable del ciclo usa exclusivamente Python estándar.

## Ejecución

Desde el repositorio, sobre una rama aislada, ejecutar sin sudo:

```bash
python3 -m unittest discover -v
python3 scripts/sprint_cycle.py --run --max-rounds 6
```

Para una ronda solamente: `python3 scripts/sprint_cycle.py --once`.

El proceso **se ejecuta en primer plano y termina en la misma invocación**. No es un daemon, automation ni tarea en segundo plano. La repetición se limita a un máximo de 6 rondas, y detiene la ejecución si no queda una acción nueva segura, si el estado converge o si los siguientes pasos necesitan autorización, prueba física o cambios upstream. No repetirá deliberadamente una acción fallida sin evidencia nueva.

## Etapas por iteración

`BASELINE → DISCOVER → DECIDE → PLAN → EXECUTE → VERIFY → PERSIST → LOOP_GATE`.

La adquisición usa una lista blanca de comandos sin shell ni permisos elevados, con timeout de 20 s y terminación de sus propios grupos de procesos. Toda escritura pertenece al worktree del sprint.

## Estados

| Estado | Interpretación |
| --- | --- |
| `VERIFIED` | Criterio preciso de aceptación probado **para ese alcance**, no necesariamente todo el subsistema. |
| `BLOCKED_USER` | Requiere autorización, acceso administrativo, prueba física o reinicio supervisado. |
| `BLOCKED_PHYSICAL` | Falta equipo conectado o comprobación presencial. |
| `BLOCKED_UPSTREAM` | Requiere soporte/solución no acreditada en el kernel actual o el diagnóstico ya no puede continuar de manera segura. **No implica causalidad upstream demostrada.** |
| `INVESTIGATION_NEEDED` | Evidencia insuficiente y todavía no hay solución ni bloqueo clasificado con precisión. |
| `WAITING_RELEASE` | Se conoce corrección propuesta, pero no hay versión publicada verificable. |
| `NOT_PLANNED` | Intervención descartada por redundante, innecesaria o insegura. |

`assistant_work_pending` significa que **el ejecutor llegó al límite de sus acciones, pero aún quedan investigaciones asignadas al asistente**. Este resultado no autoriza pedir al usuario que haga el trabajo técnico. `external_actions_only` se reserva para los casos en que todos los frentes restantes estén verificados, descartados o verdaderamente bloqueados por autorización, verificación física o dependencia externa demostrada.

Cada issue incluye el campo tipado `next_owner` (`ASSISTANT`, `USER`, `UPSTREAM` o `NONE`); los informes muestran quién debe ejecutar el siguiente paso. Los reportes 000001–000004 se generaron antes de esta distinción y son históricos: consultar la iteración 000005 o posterior.

## Evidencia y privacidad

- `.local/sprint-cycles/iterations/000NNN.json`: checkpoints privados ignorados por Git; contienen `boot_id`, pero nunca comandos crudos, logs personales ni identificadores USB completos.
- `docs/sprint-cycles/iteration-000NNN.md`: resumen restringido a campos permitidos. Revisar antes de publicar.
- Los directorios privados se crean `0700`, sus archivos `0600`, y se rechazan symlinks de salida y rutas fuera del repositorio.
- El proceso toma un lock y no sobreescribe checkpoints previos; en caso de interrupción reanuda desde el último checkpoint íntegro.
- Variables `HOME`, `XDG_CACHE_HOME`, `GST_REGISTRY` se aíslan en caché privada para evitar modificaciones en el perfil del usuario; la caché de plugins GStreamer **sí puede construirse dentro de ese directorio**.

## Prevención de bucles peligrosos

Por defecto, el runner **no invoca pruebas activas del decodificador Qualcomm IRIS**. Hubo errores de negociación `not-negotiated`, y el kernel registró `session error received 0x4000003: fatal error` en este arranque. Una sesión de video problemática no debe convertirse en un bucle de prueba. Se requiere investigación específica y aprobación antes de reactivar diagnósticos capaces de bloquear el controlador.

Tampoco ejecuta: `sudo`, `pkexec`, `modprobe`, reinicios, acciones sobre el arranque, cambios MOK, pruebas acústicas de altavoces sin protección, estrés térmico, cambios de servicio systemd ni flasheo de BIOS.

## Qué NO hace este proyecto

No implementa automáticamente drivers no publicados, no completa pruebas físicas de pantallas, no sustituye supervisión humana de Secure Boot o BitLocker, y no presenta un contador de rondas como evidencia de corrección. Las correcciones de sistema siguen requiriendo planes separados, con TDD, análisis de riesgos y aceptación antes de cambiar componentes sensibles.

## Referencias vinculantes

- [Gate de soluciones upstream](sprint-2026-11-01-upstream-solutions-review.md)
- [Especificación](superpowers/specs/2026-11-01-sprint-cycle.md)
- [Plan de implementación](superpowers/plans/2026-11-01-sprint-cycle.md)
- [Guía Desktop Commander](desktop-commander-systemd.md)
- [Corrección ya validada pd-mapper](pd-mapper-overlay-regression.md)
- [Superpowers (obra)](https://github.com/obra/superpowers)
