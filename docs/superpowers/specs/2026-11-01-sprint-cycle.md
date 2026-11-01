# Especificación aprobada: ciclo determinista para cerrar sprint Dell XPS ARM64

**Solicitante:** usuario. **Fecha:** 2026-11-01. **Ámbito:** repositorio `aldo80st/xps13-9345-ubuntu-arm64`, XPS 13 9345 Snapdragon X Elite, Ubuntu 26.10 aarch64. **Objetivo:** repetir rondas completas de diagnóstico→selección upstream→cambio reversible permitido→verificación→evidencia→clasificación, hasta que ya no exista trabajo seguro y automático pendiente.

## Reglas de autoridad

- Seguridad no negociable: conservar Secure Boot, shim, sistema de arranque EFI, Windows/BitLocker. No cambiar MOK, kernel firmado, EFI, BIOS, firmware de placa ni initramfs sin aprobación explícita.
- No escribir en /etc, /usr, /lib/firmware, /boot, /sys, systemd global, módulos del kernel ni invocar sudo/pkexec. Las acciones fuera de la rama aislada requieren gate humano.
- No activar amplificadores sin protección; evitar parámetros `i_accept_the_danger`, volumen forzado o audio peligroso.
- No desactivar servicios para esconder fallas; no reiniciar computadora, Docker, red, agente Desktop Commander ni interfaces vitales mientras la conexión dependa de ellas.
- No tratar `Fix Committed` como `Fix Released`; seguir `docs/sprint-2026-11-01-upstream-solutions-review.md`.
- No ejecutar borrado de otros proyectos ni sobrescribir modificaciones existentes. El trabajo se realiza en esta rama Git aislada.
- No publicar secretos, tokens, logs crudos, datos identificadores ni contenido de `/proc/keys`. Guardar evidencia privada en `.local/sprint-cycles/` (ignorado por Git).
- Cada cambio de software: prueba RED→GREEN→REFACTOR; antes de declarar solución, verificar funcionalidad real. Los frentes independientes no deben bloquearse entre sí.

## Etapas de una iteración (en este orden)

1. **BASELINE**: snapshot mínimo y anónimo de hardware/software/servicios, firmado con timestamps y hashes cuando aplique. Los comandos deben ser de solo lectura, con lista blanca y timeout. Registrar `boot_id` solo en evidencia privada.
2. **DISCOVER**: relacionar resultados con issues #1 EVDI+MOK, #2 IRIS, #3 EC, #4 audio, #5 BIOS, #6 Desktop Commander, #7 pd-mapper corregido, #8 Adreno no planificado.
3. **DECIDE**: identificar alternativas upstream ya documentadas y elegir DIRECTO, ADAPTAR, ESPERAR, DESCARTAR. Registrar causa, riesgo, pruebas requeridas y reversión.
4. **PLAN**: definir una acción mínima segura por issue o registrar bloqueo; nunca intentar cambiar EFI/firmware/arranque.
5. **EXECUTE**: realizar únicamente diagnósticos y pruebas funcionales no intrusivas, o cambios reversibles explícitamente autorizados en el árbol de trabajo; no interferir con aplicaciones abiertas.
6. **VERIFY**: comparar con baseline y criterio de aceptación real. No considerar un dispositivo funcional porque aparece enumerado.
7. **PERSIST**: archivo JSON privado por ronda y resumen Markdown redactado, con correlación issue/evidencia/estado; reportes públicos sin secretos.
8. **LOOP GATE**: repetir si hay **nuevo trabajo automatizable y seguro con probabilidad de avance real**. Detener cuando solo queden `BLOCKED_USER`, `BLOCKED_PHYSICAL`, `BLOCKED_UPSTREAM` o `WAITING_RELEASE`, o cuando dos rondas no producen progreso. Máximo 6 rondas por invocación y 20s por comando; no bucles infinitos ni acciones repetidas idénticas.

## Forma y estados

Estados permitidos: `PENDING`, `DIAGNOSING`, `READY_SAFE_ACTION`, `VERIFIED`, `BLOCKED_USER`, `BLOCKED_PHYSICAL`, `BLOCKED_UPSTREAM`, `WAITING_RELEASE`, `NOT_PLANNED`, `INVESTIGATION_NEEDED`.
`VERIFIED` exige prueba final funcional, timestamp y evidencia. `WAITING_RELEASE` sólo cuando se confirme que aún no hay paquete integrado. Evitar atribuciones causales sin evidencia.

Crear herramienta Python estándar `scripts/sprint_cycle.py` con CLI `--run`, `--once`, `--max-rounds` y `--output-dir`, tests `tests/test_sprint_cycle.py` con `unittest`, documentación operativa `docs/sprint-cycle-method.md`; aislamiento de datos privados.

## Primer ciclo ejecutable

- #1 verificar firma EVDI, kernel y Secure Boot **sin modificar claves**, confirmar DisplayLink USB, snapshot de fallos del servicio; referencia upstream #2131181.
- #2 comprobar nodo V4L2 y pruebas de GStreamer H.264 con bitstream sintético (sin archivos personales); clasificar resultado honradamente.
- #3 sólo sensores/estado EC y fuente upstream; **sin estrés ni carga térmica**.
- #4 inspeccionar topologías, PipeWire, UCM en modo lectura; **sin sonido por altavoces hasta confirmar protección**.
- #5 versión BIOS disponible / bloqueo por BitLocker; no actualizar.
- #6 comprobar service systemd --user y agentes duplicados, sin reiniciarlos.
- #7 `pd-mapper` activo y SHA oficial, sin modificar.
- #8 comportamiento Adreno ya clasificado por Ubuntu como intencional; no actualizar dracut.
- Generar reporte local y resumir bloqueos. El ciclo puede terminar tras una ronda si no queda ninguna acción segura que pueda mejorar la situación.

## Entrega

Repo con especificación, plan Superpowers, código con tests, ejecución real de al menos una ronda, resumen de decisiones, commits en rama, y, cuando corresponda, PR. No fusionar directamente sin revisión. Hacer explícito lo que sigue necesitando aprobación o pruebas físicas. Nunca prometer ejecución en segundo plano: completar las rondas en la ejecución actual.
