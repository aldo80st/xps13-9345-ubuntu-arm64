# XPS-VAL-01 — Ejecución inicial y evidencia 2026-11-21

**Estado general:** PARTIAL / REVIEW_REQUIRED · Epic [#50](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/50) · Paquetes [V0 #51](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/51) a [V6 #57](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/57).

## Reconciliación V0 (fuente de verdad y límites)

- Fuente única: `aldo80st/xps13-9345-ubuntu-arm64`, `origin/main` desde SHA `9ed5a51292419ebc2a1a4d1e0c1ad3bd16e92a96` al crear el worktree el 2026-11-21.
- Worktree aislado: `feat/xps-val01-evidence-compat-20261121` (no altera ramas de hibernación ni el workspace principal).
- Entorno previo encontrado: el workspace principal está en rama `fix/resources-51-qualcomm-cpu-metrics`, limpio; existen múltiples worktrees específicos de #21, EC y NPU. Staging térmico previo existe separado. No copiar parches/DTB/EFI del staging a esta rama.
- Reutilizar `scripts/diagnose-readonly.sh`, `docs/thermal-ec.md`, `docs/thermal-hibernation-integration.md`, `docs/qcom-iris.md`, `scripts/stage-dell-ec-v8.py`. No crear otro EC ni clonar #21.
- Revisión de privacidad: campos de instantánea exclusivamente por allowlist; se omiten los IDs reales de interfaz, EDID, MAC, SSID, serie, nombres de usuario, rutas personales, tokens y contenido de journal.

## V1 — Línea base auditada (OBSERVADO en host)

| Evidencia | Resultado | Precisión / limitación |
| --- | --- | --- |
| Sistema | Ubuntu 26.10 ARM64, `7.3.0-11-generic` | observado 2026-11-21 |
| BIOS | 2.14.0 | **NO** actualizado a 2.15.0; cuestión #5 |
| CPUFreq | `scmi`, `ondemand`, policies 0/4/8, 710400–3417600 kHz | tres clusters visibles; no equivale a prueba de throttling |
| EC experimental | `dell-xps-ec` no disponible por `modinfo`, `dell_xps_ec` no cargado | no concluye estabilidad |
| Iris | `qcom_iris` cargado, V4L2 decoder y encoder presentes | decodificación H.264 directa pasó en prueba previa; Chrome VA-API no |
| DisplayLink | D6000 USB 17e9:6006 presente; `evdi` cargado | dos HP E273 a 1920×1080 @60 Hz; pantalla interna conectada no necesariamente activa |
| Audio | servicios `pipewire` y `wireplumber` activos | funcionamiento de altavoces sin validar en esta entrega |
| Almacenamiento raíz | 90 % usado, ~27 GiB libres en revisión | riesgo operativo; no borrar archivos ajenos |
| Energia | perfil `balanced`; alimentación USB `online=1`, batería `Not charging` | sin atribuir razón del estado de batería |
| Kernel actual, `journalctl -k -b -p warning` | 26 coincidencias de texto `pmic-glink`, 2 de GPU, 0 de `adc5`, 0 de `dell_ec`, 0 de `panic` | **contadores de coincidencias**, no 26 defectos ni prueba causal |

### Cronología de reinicios

`journalctl --list-boots` lista cierre de boot `-3` a **2026-11-20 19:44:43 CST**, `-2` a **2026-11-20 22:06:56 CST**, `-1` a **2026-11-21 11:44:48 CST** y arranque actual posterior. El mismo inicio 2026-10-02 aparece en múltiples boots: **anomalía de timestamp/retención de logs**, no usarlo como hora real de cada arranque.

El epic #50 documentó en la ventana del incidente del 20 de noviembre timeouts `qcom-spmi-adc5-gen3` y `dell-xps-ec ... sys_therm1: -110`; esta ejecución **no recuperó de nuevo** esa línea del journal mediante la búsqueda cronológica. Clasificación: `OBSERVADO EN REPORTE HISTÓRICO / NO REVALIDADO INDEPENDIENTEMENTE`. La distinción entre el reinicio potencialmente no ordenado ~19:44 y el reinicio ordenado ~22:07 sigue abierta; no atribuir la causa al EC, PMIC ni firmware.

## V2 — Captura de mínimo impacto, sin daemon

`scripts/xps_val01_collect.py` solo imprime JSON a stdout; no se instala, no persiste, no requiere sudo. Incluye versión de esquema, timestamp UTC, hardware/BIOS, kernel, policies CPUFreq, dispositivo Iris, temperatura agregada, EVDI/DisplayLink, clase de interfaces y *contadores* de errores de journal actual. Todas las rutas de sysfs usadas son **lectura**. Los comandos externos tienen tiempo límite, capturan conteos pero **no** incluyen logs en salida.

- `python3 scripts/xps_val01_collect.py` — inventario puntual del host, datos allowlist en terminal.
- `python3 scripts/xps_val01_collect.py --root /ruta/fixture --no-commands` — fixtures aislados; rechazo explícito de `--root` sin `--no-commands`.
- `python3 scripts/xps_val01_compare.py --before SNAPSHOT_1.json --after SNAPSHOT_2.json` — comparación de dos snapshots guardados **solo si se autoriza su captura y retención**.
- `python3 -m unittest discover -s tests -p 'test_xps_val01.py' -v` — batería sintética; 10 pruebas PASS iniciales.

**Contrato para cualquier colector persistente futuro:** requerirá autorización opt-in separada, mínimo intervalo 60 s propuesto, salida privada 0600, límites de retención/espacio/cuota, auditoría, rendimiento medido, verificación de no persistencia de secretos y apagado fail-closed. No se instaló ni se programó servicio.

## V3 — Inventario upstream

Ver [matriz de upstream](./xps-val01-upstream-matrix.md), con referencias de series y clasificación; no se confunde parche propuesto con mergeado o empaquetado en Ubuntu.

## V4 — Laboratorio aislado y pruebas

- Prueba opcional de humo: `bash scripts/xps_val01_video_smoke.sh` genera 120 fotogramas H.264 1080p en directorio temporal, valida FFmpeg y, si está disponible, Iris V4L2; elimina el temporal al salir. No prueba VA-API/Chrome.
- Pruebas unitarias de fixture: salida sin datos privados; root falsificado, sin comandos; tolerancia a sensores inválidos; no auto autorizar adopción; deltas red/kernel; resets de contadores; Iris faltante; esquema inválido.
- `scripts/xps_val01_compare.py` entrega siempre `decision=REVIEW_REQUIRED`, `adoption_authorized=false`, `cause_confirmed=false`.
- Pruebas sintéticas previas de decodificación real: H.264 V4L2 Iris PASS, H.264 FFmpeg PASS; Chrome headless 1080p local sin nuevos frames perdidos después de inicio. No equivale a prueba física de múltiple monitor/compositor ni estrés.
- Pendiente: correlación de segmentación de stream real, versión exacta de fuentes Iris/VA-API, ensayos de regresión con kernel experimental solo en sistema no operativo. **GO-LAB** únicamente para pruebas de fixtures y código, no para instalación.

## V5 — Borrador maintainer-grade

Ver [borrador upstream](./xps-val01-maintainer-draft.md). Ningún email, comentario en lista, PR upstream o petición externa enviada.

## V6 — Estado y decisiones

| Candidato | Estado | Justificación |
| --- | --- | --- |
| Colector puntual / comparador | `ADOPTAR como herramienta de laboratorio` (no como daemon) | suite de tests y privacy checks PASS; review/CI pendientes |
| Dell EC v8 en kernel de uso diario | `NO_GO` | módulo ausente en 7.3.0-11, posible asociación histórica con timeouts; sin validación estable |
| BIOS 2.15.0 | `ESPERAR / #5` | gate BitLocker/Secure Boot/respaldo y cambio firmware independiente |
| `qcom-va-driver` / parches Iris | `GO-LAB / NO_GO HOST` | V4L2 opera; Chromium VA-API falla, kernel fixes ABI sin verificar |
| Hibernación real | `NO_GO / #21` | gates previos pendientes y riesgo recuperación TPM/BitLocker |
| EVDI + Secure Boot | `NO_GO HOST / #1` | módulo cargado con configuración actual; no alterar cadena de confianza |
| Audio / GNOME / NPU | `NO_VERIFICADO` | pruebas funcionales de cada subsistema aún no realizadas |

## Restricciones y criterios de cierre pendientes

No declarar resueltos reinicios o video solo por un baseline bueno. Para cerrar V1 se necesita timeline con el entorno real de boot, orden de eventos y ausencia/presencia de errores reproducida. V3 requiere comprobar estado upstream completo de commits y versiones empaquetadas. V4 requiere revisión independiente del código y hardware opt-in, V5 aprobación de publicación, V6 duración de estabilidad/rollback y decisión final de adopción por cambio.
