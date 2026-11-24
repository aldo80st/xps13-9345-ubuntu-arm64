# XPS AUTHZ v1.1 — interfaz candidata del broker local (M1/M3)

Estado: **diseño candidato para laboratorio**. No es unidad instalable, no autoriza instalación ni activación y no contiene scripts de elevación. Ningún privilegio concedido.

| Ámbito | Estado |
|---|---|
| Transporte IPC v1 de laboratorio (parser/handler, sin daemon ni socket instalado) | **PASS** 11 pruebas en ARM64 nativo (XPS) y en LUCIFER01 |
| Transporte IPC v2 (`operation_phase`, `operation_outcome`, `status_provider`) | **PASS** 13/13 en LUCIFER01; ARM64 nativo NOT_RUN, **superado por v3** (no se convierte retroactivamente en PASS) |
| Transporte IPC v3 | **PASS** 14/14 en aarch64 nativo (XPS) y en LUCIFER01; revisión estática **PASS** |
| Broker de laboratorio | 9/9 pruebas; revisión independiente **PASS** v3 aislado; integración real pendiente |
| Política, ledger durable, ejecutores, recuperación R0 | **NOT_RUN** (no integrados) |
| Migración de identidades y MCP (`docs/xps-authz-migration.md`) | **NOT_RUN** |
| Registro de tramas rechazadas | no durable todavía; sin afirmación de durabilidad |

El PASS de transporte no acredita aislamiento, migración, durabilidad ni autoridad. Gobiernan `AGENTS.md`, ADR-001 rev. 2, `.ai-architect/architecture-contract.yaml` rev. 2 e `.ai-architect/implementation-plan.md`. Ver también `docs/xps-authz-migration.md`.

## 1. Por qué un socket y no sudo

Los MCP actuales corren con `NoNewPrivileges=1` y `CapEff=0`: un servicio NNP no puede usar binarios setuid, por lo que `sudo` desde el servicio no es un canal válido ni debe intentarse habilitar. Tampoco se usa NOPASSWD ni capacidades en la identidad agente. La resolución observada de NNP **no** se presenta como prueba de ausencia de acceso root: las rutas por grupo (`docker`, `lxd`) y por sockets siguen abiertas en la línea base.

El canal agente → autoridad es un socket Unix local con autenticación por credenciales del kernel (`SO_PEERCRED`) y un catálogo cerrado. La concesión y revocación quedan en un canal separado del propietario.

## 2. Componentes y privilegios

| Componente (contrato) | Identidad candidata | Privilegios | Notas |
|---|---|---|---|
| `agent-adapter` (MCP migrado) | `xps-agent`, UID/GID dedicados no root, sin grupos suplementarios | ninguno; NNP, `CapEff=0` | solo conecta al socket agente; runtime fuera del home del propietario |
| broker (`policy-engine` + escucha) | UID 0 sin capacidades (`CapabilityBoundingSet` vacío), NNP, sistema de archivos de solo lectura salvo el estado propio | sin `CAP_SYS_MODULE`, sin `CAP_SYS_ADMIN` | propietario root de estado, política y recibos; inicia solo unidades de trabajador con nombre fijo |
| trabajador `audit` | sin `CAP_SYS_MODULE`; filtro de syscalls que niega `init_module`, `finit_module`, `delete_module` | lectura de módulos y fuentes de auditoría | no usar aislamiento que oculte archivos de módulos (G-AUDIT) |
| trabajador `iris-r0` + `recovery-manager` | unidad fija aislada, única con `CAP_SYS_MODULE` en su conjunto delimitador | solo nombre de módulo, kernel y hash oficiales fijados en configuración root | sin argv del cliente; marcador durable antes de descargar (G-R0) |
| trabajador `thermal` | usuario dinámico sin privilegios | ninguno | un trabajador, 10 s, ~25 % de un núcleo; watchdog 12 s (G-THERM) |
| `owner-control` | propietario autenticado en consola local | autenticación administrativa interactiva | grant/revoke; nunca accesible al agente |

Alternativa a evaluar en laboratorio: broker con usuario de sistema propio y regla polkit limitada a `StartUnit` de los nombres de unidad exactos. Se prefiere UID 0 sin capacidades porque el contrato exige estado y recibos protegidos por root; la decisión final se toma con evidencia de M4, no aquí.

## 3. Socket agente (protocolo candidato fijo)

| Propiedad | Valor |
|---|---|
| Familia / tipo | `AF_UNIX`, `SOCK_STREAM`, ruta en sistema de archivos bajo `/run` (no socket abstracto) |
| Propiedad y modo | `root:xps-agent`, `0660`; directorio padre no escribible por el agente |
| Autenticación | `SO_PEERCRED`: `uid` y `gid` deben ser **exactamente** los de `xps-agent`; se rechaza UID 0, UID 1000 y cualquier otro. El PID solo se registra, no autoriza |
| Petición | un único comando ASCII por conexión, terminado en LF; el cliente hace `shutdown(SHUT_WR)` y el broker exige EOF |
| Comandos válidos | `status\n`, `audit\n`, `iris-r0\n`, `thermal\n` — cuatro opciones, comparación exacta de bytes |
| Tamaño máximo | 8 bytes (`iris-r0\n` y `thermal\n` = 8) |
| Plazo de lectura | 2 s hasta EOF; excederlo es rechazo |
| Rechazo | bytes extra, falta de LF, falta de EOF, mayúsculas, espacios, NUL, CR, UTF-8 no ASCII, prefijos/sufijos, segunda línea, `grant`, `revoke` o cualquier otro token |
| Argumentos | ninguno: sin shell, argv, rutas, variables de entorno, comodines ni parámetros |

Un rechazo de trama o peer anterior a la admisión no consume usos ni inicia efectos. Un fallo después de la admisión puede dejar consumo y efectos registrados; nunca se supone que ERROR equivale a ausencia de efectos. La respuesta no hace eco de la entrada. **Registro de tramas rechazadas:** el handler de laboratorio aún no lo persiste de forma durable; no se afirma durabilidad ni trazabilidad completa de rechazos. Objetivo de integración (NOT_RUN): registrar el rechazo y, si el registro falla, denegar nuevas acciones (G-LEDGER).

### Respuesta (IPC de laboratorio)

Claves documentadas desde IPC v2; IPC v3 (14/14 PASS) es la versión vigente del laboratorio y su handler es la referencia exacta ante cualquier diferencia con esta tabla. Un objeto JSON pequeño por conexión, sin secretos, rutas, argumentos, entorno, nombres de unidad internos ni datos del propietario.

| Clave | Contenido |
|---|---|
| `result` | uno de `STATUS`, `ACCEPTED`, `DENIED`, `BUSY`, `ERROR` (mayúsculas exactas) |
| `reason` | código corto sanitizado; nunca eco de la entrada ni ruta |
| `operation_id` | identificador opaco de la operación (o de la última, en `STATUS`) |
| `lease_remaining_s` | segundos restantes del lease (`CLOCK_BOOTTIME`, boot ID); sin lease vigente ninguna acción se admite (representación exacta: la del handler vigente IPC v3) |
| `remaining` | usos restantes por acción: `audit`, `iris-r0`, `thermal` |
| `recovery_pending` | booleano; `true` bloquea nuevas acciones hasta conciliación |
| `operation_phase` | enumerado *nullable*: etapa de la última operación; `null` si no hay operación o dato |
| `operation_outcome` | enumerado *nullable*: resultado correlacionado por `operation_id`; `null` mientras no exista resultado |

Los valores exactos de `reason`, `operation_phase` y `operation_outcome`, y la asignación `DENIED`/`ERROR` por caso, son los definidos por el handler IPC v3 de laboratorio; este documento no los redefine ni los amplía. Un valor `null` o desconocido nunca se interpreta como éxito.

- `STATUS`: respuesta a `status\n`; no consume usos. Se obtiene de un **`status_provider` separado** del camino de admisión: solo lectura de estado sanitizado, sin capacidad de consumir, conceder ni iniciar efectos.
- `ACCEPTED`: identifica una admisión durable nueva, vinculada a acción, ID y secuencia posterior al inicio de la solicitud. Compromiso y marcador R0 durables preceden a cualquier efecto; el ACK no significa éxito. El broker v3 se probó con fixtures; su integración con la política real aún es gate.
- `DENIED`: política (sin lease, caducado, revocado, sin cupo, peer no autorizado, `recovery_pending`).
- `BUSY`: otra operación admitida en curso (un efecto por vez); sin consumo.
- `ERROR`: fallo interno o resultado incierto. Puede ocurrir antes o después de admisión/compromiso/efecto. No reintentar ni asumir devolución de cupo: consultar estado y recibos; si no se puede reconciliar, bloquear la continuación.

### Reconciliación de fase/resultado

Implementada en el IPC v2 como forma de respuesta (`operation_phase`, `operation_outcome`, `status_provider`). Su **veracidad** depende del ledger durable (G-LEDGER) y del marcador R0 (G-R0), que no están integrados: hasta la integración, estos campos no acreditan el estado real de ningún efecto en la XPS.

### Reintentos

El cliente **no reintenta** una acción si pierde la respuesta. Consulta `status\n` y reconcilia por `operation_id`, `operation_phase` y `operation_outcome`. El broker no deduplica por reintentos ni devuelve usos tras fallos.

## 4. Canal del propietario (grant / revoke)

- Separado del socket agente: ni el comando ni la ruta existen en el protocolo agente; `grant`/`revoke` en el socket agente es rechazo.
- Autenticación administrativa interactiva del propietario en consola local; sin NOPASSWD, sin token almacenado accesible al agente, sin canal remoto. Una TTY no acredita presencia física; la confirmación de preparación física de M6 es separada.
- `grant` fija: 1200 s `CLOCK_BOOTTIME`, boot ID actual, cinco `audit`, un `iris-r0`, un `thermal`. No hay renovación por agente.
- `revoke` impide nuevos compromisos antes de anunciarse completado, detiene `thermal` activo y no interrumpe una restauración R0 ya comprometida.
- Mientras los MCP heredados sigan bajo UID 1000 con grupos administrativos, el canal del propietario no se habilita (ver migración, gate G-ID).

## 5. Semántica de admisión (resumen de gates)

Bajo un bloqueo común con revocación y caducidad: validar peer, lease, boot, cupo, `recovery_pending` y reserva de tiempo → consumir uso y escribir recibo con fsync de archivo y directorio → persistir compromiso y, para R0, marcador durable en la misma transacción → revalidar vigencia → iniciar unidad fija bajo exclusión común. Fallo de escritura o fsync = denegar. Un reinicio del broker no devuelve usos; un boot distinto invalida el lease. Detalle normativo en el contrato rev. 2 y gates G-LEASE, G-LEDGER, G-R0, G-THERM, G-AUDIT.

## 6. Casos de laboratorio del parser/handler

Especificación de cobertura para el parser/handler de laboratorio (sin daemon ni socket instalado). Resultados reportados por el laboratorio: IPC v1 11 PASS (ARM64 nativo y LUCIFER01); IPC v2 13/13 PASS en LUCIFER01 (nativo NOT_RUN, superado); IPC v3 14/14 PASS en aarch64 nativo y LUCIFER01, revisión estática PASS. Broker v3: 9/9 pruebas y revisión PASS de correlación; P13–P16 aún requieren evidencia de integración completa. La correspondencia exacta entre esas pruebas y los IDs P siguientes se toma del reporte del laboratorio y no se infiere aquí; lo no cubierto queda **NOT_RUN**.

| ID | Entrada / condición | Esperado | Capa |
|---|---|---|---|
| P1–P4 | cada comando válido exacto + EOF | parser acepta; `result` según política | transporte |
| P5 | comando sin LF | rechazo sin consumo | transporte |
| P6 | comando válido + bytes extra / segunda línea | rechazo sin consumo | transporte |
| P7 | >8 bytes | rechazo sin leer más allá del límite + 1 | transporte |
| P8 | sin EOF en 2 s | rechazo por plazo | transporte |
| P9 | `grant\n`, `revoke\n`, mayúsculas, espacios, CR, NUL, no ASCII | rechazo | transporte |
| P10 | peer UID 0, UID 1000, UID correcto con GID distinto | rechazo | transporte |
| P11 | forma de respuesta | solo las claves de §3; `result` en mayúsculas; sin rutas ni secretos | transporte |
| P12 | `operation_phase`/`operation_outcome` nulos o enumerados; `STATUS` vía `status_provider` sin consumo | forma v2 | transporte v2 |
| P13 | fallo simulado de escritura/fsync del recibo de admisión | sin efecto, denegación posterior | integración — NOT_RUN |
| P14 | cliente cierra antes de leer respuesta | sin reintento; `STATUS` refleja fase/resultado durables | integración — NOT_RUN |
| P15 | acción con otra operación en curso | `BUSY`, sin consumo | integración — NOT_RUN |
| P16 | rechazo con registro durable y fallo de registro | registro persistido; fallo → denegar nuevas acciones | integración — NOT_RUN |

El código `DENIED`/`ERROR` concreto de cada rechazo es el del handler de laboratorio.
