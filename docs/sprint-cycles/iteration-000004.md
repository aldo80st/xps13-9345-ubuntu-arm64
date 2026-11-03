# Sprint cycle — evidencia redactada

Iteración: 4. Fecha UTC: 2026-11-01T19:28:31.070468+00:00.
Parada: `external_actions_only`.

El gate es una referencia histórica; no se confirmó una nueva release en línea.

| Issue | Estado | Decisión |
| --- | --- | --- |
| #1 | BLOCKED_USER | ADAPTAR |
| #2 | BLOCKED_UPSTREAM | ADAPTAR |
| #3 | BLOCKED_UPSTREAM | ESPERAR |
| #4 | BLOCKED_UPSTREAM | ESPERAR |
| #5 | BLOCKED_USER | ESPERAR |
| #6 | BLOCKED_USER | DIRECTO |
| #7 | VERIFIED | DIRECTO |
| #8 | NOT_PLANNED | DESCARTAR |

Los estados VERIFIED tienen alcance limitado al criterio indicado.

## #1

Fuente: Ubuntu LP #2131181 / DisplayLink signed DKMS.
Criterio: Dos pantallas DisplayPort con video funcional observado; firma y Secure Boot conservados.
Acción humana/upstream: Revisar integración de kernel firmado y confianza MOK con autorización; probar ambas DisplayPort físicamente.

## #2

Fuente: Dell KPF2C / V4L2 IRIS; guía Qualcomm de otro BSP.
Criterio: Tres frames H.264 sintéticos por decoder V4L2 hardware hasta EOS, sin render ni archivos personales.
Acción humana/upstream: Revisar caps V4L2 y disponibilidad de decoder hardware; elevar permisos solo con intervención humana.

## #3

Fuente: Dell EC PATCH v8 / Ubuntu LP #2172131.
Criterio: Control EC y ventilación funcional demostrados; sensores solos no bastan.
Acción humana/upstream: Esperar integración demostrada en kernel firmado; validación térmica funcional supervisada.

## #4

Fuente: Dell tributo / AudioReach / UCM / Ubuntu LP #2172596.
Criterio: Protección demostrada y prueba funcional segura L/R y micrófonos supervisada.
Acción humana/upstream: Comparar topología/UCM y protección del amplificador antes de autorizar prueba acústica.

## #5

Fuente: Dell BIOS PK3V5; referencia histórica 2.15.0.
Criterio: Validación humana por procedimiento Dell soportado; no se actualiza en este runner.
Acción humana/upstream: Confirmar versión vigente Dell, alimentación y recuperación BitLocker; requiere autorización explícita.

## #6

Fuente: docs/desktop-commander-systemd.md.
Criterio: Servicio activo, una instancia y operación remota tras login comprobada.
Acción humana/upstream: Validar conexión de relay y continuidad tras login/reinicio de forma supervisada; no reiniciar aquí.

## #7

Fuente: docs/pd-mapper-overlay-regression.md.
Criterio: Alcance: regresión de overlay recuperada; servicio activo, mapas base y firmware oficial, sin overlay.
Acción humana/upstream: Si hay regresión, investigar permisos/mapas y SHA; restauración global requiere intervención humana.

## #8

Fuente: Ubuntu LP #2169496: reintento intencional según gate.
Criterio: No planificado; no se afirma prueba gráfica funcional.
Acción humana/upstream: No modificar dracut; abrir investigación solo ante fallo gráfico funcional reproducible.
