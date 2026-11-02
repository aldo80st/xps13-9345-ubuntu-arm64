# Sprint cycle — evidencia redactada

Iteración: 5. Fecha UTC: 2026-11-02T05:40:41.646239+00:00.
Parada: `assistant_work_pending`.

El gate es una referencia histórica; no se confirmó una nueva release en línea.

| Issue | Estado | Responsable |
| --- | --- | --- |
| #1 | INVESTIGATION_NEEDED | ASSISTANT |
| #2 | INVESTIGATION_NEEDED | ASSISTANT |
| #3 | INVESTIGATION_NEEDED | ASSISTANT |
| #4 | INVESTIGATION_NEEDED | ASSISTANT |
| #5 | BLOCKED_USER | USER |
| #6 | BLOCKED_USER | USER |
| #7 | VERIFIED | NONE |
| #8 | NOT_PLANNED | NONE |

Los estados VERIFIED tienen alcance limitado al criterio indicado.

## #1

Fuente: Ubuntu LP #2131181 / DisplayLink signed DKMS.
Decisión: ADAPTAR.
Responsable: ASSISTANT
Criterio: Dos pantallas DisplayPort con video funcional observado; firma y Secure Boot conservados.
Siguiente paso: Revisar integración de kernel firmado y confianza MOK con autorización; probar ambas DisplayPort físicamente.

## #2

Fuente: Dell KPF2C / V4L2 IRIS; guía Qualcomm de otro BSP.
Decisión: ADAPTAR.
Responsable: ASSISTANT
Criterio: Tres frames H.264 sintéticos por decoder V4L2 hardware hasta EOS, sin render ni archivos personales.
Siguiente paso: Revisar caps V4L2 y disponibilidad de decoder hardware; elevar permisos solo con intervención humana.

## #3

Fuente: Dell EC PATCH v8 / Ubuntu LP #2172131.
Decisión: ESPERAR.
Responsable: ASSISTANT
Criterio: Control EC y ventilación funcional demostrados; sensores solos no bastan.
Siguiente paso: Esperar integración demostrada en kernel firmado; validación térmica funcional supervisada.

## #4

Fuente: Dell tributo / AudioReach / UCM / Ubuntu LP #2172596.
Decisión: ESPERAR.
Responsable: ASSISTANT
Criterio: Protección demostrada y prueba funcional segura L/R y micrófonos supervisada.
Siguiente paso: Comparar topología/UCM y protección del amplificador antes de autorizar prueba acústica.

## #5

Fuente: Dell BIOS PK3V5; referencia histórica 2.15.0.
Decisión: ESPERAR.
Responsable: USER
Criterio: Validación humana por procedimiento Dell soportado; no se actualiza en este runner.
Siguiente paso: Confirmar versión vigente Dell, alimentación y recuperación BitLocker; requiere autorización explícita.

## #6

Fuente: docs/desktop-commander-systemd.md.
Decisión: DIRECTO.
Responsable: USER
Criterio: Servicio activo, una instancia y operación remota tras login comprobada.
Siguiente paso: Validar conexión de relay y continuidad tras login/reinicio de forma supervisada; no reiniciar aquí.

## #7

Fuente: docs/pd-mapper-overlay-regression.md.
Decisión: DIRECTO.
Responsable: NONE
Criterio: Alcance: regresión de overlay recuperada; servicio activo, mapas base y firmware oficial, sin overlay.
Siguiente paso: Si hay regresión, investigar permisos/mapas y SHA; restauración global requiere intervención humana.

## #8

Fuente: Ubuntu LP #2169496: reintento intencional según gate.
Decisión: DESCARTAR.
Responsable: NONE
Criterio: No planificado; no se afirma prueba gráfica funcional.
Siguiente paso: No modificar dracut; abrir investigación solo ante fallo gráfico funcional reproducible.
