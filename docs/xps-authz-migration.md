# XPS AUTHZ v1.1 — migración de identidades y canales MCP (M1/M3)

Estado: **diseño de integración**. Sin cambios en host, cuentas, credenciales, servicios, red ni XPS. Sin unidades instalables ni scripts de elevación. Ningún privilegio concedido.

| Ámbito | Estado |
|---|---|
| Transporte IPC de laboratorio v1 | **PASS** 11 pruebas, ARM64 nativo y LUCIFER01 |
| Transporte IPC v2 (`operation_phase`, `operation_outcome` nullable, `status_provider`) | **PASS** 13/13 LUCIFER01; nativo NOT_RUN, superado por v3 (no PASS retroactivo) |
| Transporte IPC v3 | **PASS** 14/14 aarch64 nativo y LUCIFER01; revisión estática **PASS** |
| Broker de laboratorio | 10/10 pruebas; revisión independiente **PASS**; ocho pruebas de composición con política real y hardware simulado |
| Migración S0–S9, R1–R16, gates G-* | **NOT_RUN** |
| Registro durable de tramas rechazadas | no implementado; sin afirmación |

El PASS de transporte valida solo parser/handler sin daemon ni socket instalado; no acredita aislamiento, migración ni autoridad. El gate M0 r2 está integrado (`6d6ddd9`); este documento no solicita otra aprobación general. Interfaz del broker: `docs/xps-authz-broker-interface.md`.

## 1. Línea base observada (metadatos, sin secretos)

| Hora CST | Observación |
|---|---|
| 14:01–14:02 | Dos MCP (`anima-xps-direct-native`, `desktop-commander-remote`) bajo UID 1000; grupos `sudo`, `docker`, `lxd`. `NoNewPrivileges=1`, `CapEff=0`, `ProtectHome=no`, `ProtectSystem=no`. Socket Docker `root:docker 0660`. Cuenta `xps-agent` ausente. Kernel 7.3.0-11-generic. |
| 14:20 | systemd 261.3, cgroup2. Home del propietario 0750; `.config` y `.ssh` 0700; `/run/user/1000` 0700. `tunnel-client` v0.0.21 y Node v24.22.1 residen en el home, UID 1000, modo 0700. `.config/anima/xps-local-mcp` y `.openclaw` 0700. |
| 14:20 | 15 listeners TCP, 8 en loopback (visibles: gjs, GNOME Remote Desktop, ollama, tunnel-client); 3 sockets Unix abstractos. |

Interpretación:

- NNP impide que `sudo` funcione desde los servicios, pero **no** elimina rutas administrativas: pertenencia a `docker`/`lxd` equivale a root en la práctica, y los servicios actúan como el propietario (archivos, bus de sesión, `/run/user/1000`). No se afirma ni se niega acceso root a partir de la prueba NNP.
- El runtime actual (Node, tunnel-client) vive en el home 0700 del propietario: una identidad nueva **no puede** reutilizarlo sin aflojar permisos del home, lo cual está prohibido. Se requiere runtime independiente.
- Los listeners loopback y los sockets abstractos son alcanzables por cualquier proceso local sin control de permisos de archivo (abstractos) o solo con autenticación de aplicación (TCP). Son rutas candidatas hacia la autoridad del propietario.

## 2. Principios reconciliados con el diseño previo

1. No shell root abierta, ni para el agente ni como solicitud al propietario.
2. No borrar directorios, cuentas, identidades, respaldos ni evidencias.
3. No `chmod` del home del propietario ni de sus directorios; no modificar home ni grupos del propietario.
4. No nftables de forma general. Restricción de red solo por unidad del agente (filtros cgroup de systemd) y validada en laboratorio.
5. No volcar `ExecStart`, `Environment`, archivos de credenciales ni tokens en inventarios, issues o recibos.
6. El rollback **jamás** reabre un canal administrativo a agentes; el estado de reposo seguro es "agente desconectado", con la consola local del propietario intacta.
7. Revocar tokens de conectores requiere al propietario.
8. Sin `sudo` desde servicio NNP, sin NOPASSWD, sin capacidades en la identidad agente, sin shell/argv/rutas arbitrarios.
9. Fail closed: si una ruta no puede aislarse, no se habilita ninguna operación privilegiada.

## 3. Arquitectura objetivo

```
ChatGPT / Paseo ──► MCP migrado (xps-agent, runtime root-owned fuera de home, credencial nueva)
                        │  AF_UNIX root:xps-agent 0660, SO_PEERCRED exacto
                        ▼
                    broker (UID 0 sin capacidades, sin CAP_SYS_MODULE) ──► unidades fijas
                        ▲                                                   audit │ iris-r0 │ thermal
Propietario (consola local autenticada) ── grant/revoke (canal separado)
```

## 4. Inventario M1 por metadatos (lista de campos permitidos)

Recolectar solo los campos listados; cualquier otro queda fuera.

| Objeto | Campos permitidos | Prohibido |
|---|---|---|
| Unidades MCP | nombre, `User`, `Group`, `SupplementaryGroups`, `NoNewPrivileges`, `CapabilityBoundingSet`, `AmbientCapabilities`, `ProtectHome`, `ProtectSystem`, `PrivateNetwork`, `IPAddressDeny/Allow`, `RestrictAddressFamilies`, `ActiveState`, `FragmentPath` (ruta), hash SHA-256 del fragmento | `ExecStart`, `Environment`, `EnvironmentFile`, `LoadCredential*`, contenido de archivos |
| Procesos MCP | PID, UID/GID real y efectivo, grupos, `NoNewPrivs`, `CapEff/CapBnd/CapAmb`, cgroup | `cmdline`, `environ` |
| Archivos/directorios relevantes | ruta, propietario, grupo, modo, tipo | contenido |
| Listeners TCP | dirección, puerto, proceso/UID propietario | conexión al servicio |
| Sockets Unix (ruta y abstractos) | nombre, propietario/modo (ruta), proceso/UID propietario | conexión ciega |
| Credenciales | existencia, propietario, modo, fecha | valor, hash del valor |

Los 8 listeners loopback y 3 sockets abstractos se inventarían y se determina en laboratorio su autenticación; **no se cierran ni se conectan a ciegas** en la XPS.

## 5. Secuencia de migración (laboratorio primero)

| Paso | Acción | Ejecuta | Aceptación |
|---|---|---|---|
| S0 | Inventario §4 en la XPS, solo metadatos | agente bajo autorización vigente de M1 | evidencia sin secretos, SHA-256 |
| S1 | Reproducir línea base en laboratorio (VM/contenedor ARM64 o amd64 con systemd ≥ 261, cgroup2): UID 1000 con `sudo/docker/lxd`, NNP, listeners equivalentes | Claude/Paseo | entorno documentado |
| S2 | En laboratorio: crear `xps-agent` sin grupos, runtime root-owned fuera de home, broker y unidades fijas desde M2 | Claude | R1–R16 PASS en laboratorio |
| S3 | En XPS: el propietario instala y verifica runtime independiente (Node/tunnel-client) root-owned fuera de home, con hash verificado | **propietario** | hash y propietario root; no copia desde home |
| S4 | En XPS: el propietario crea `xps-agent` y emite **credenciales de servicio nuevas** en cada conector; no se copian secretos del home | **propietario** | credenciales en almacén root-owned legible solo por la unidad agente |
| S5 | Dos reemplazos diagnósticos bajo `xps-agent`, AUTHZ disabled: solo transporte/lectura de estado y pruebas de aislamiento; sin ejecutores privilegiados ni grant. M5 reserva la instalación revisada de broker/ejecutores fijos. | propietario instala; agente prueba | R1–R12, R14–R15 aplicables por cada reemplazo; sin autoridad |
| S6 | Inventariar y verificar por separado los dos reemplazos y las dos rutas heredadas, desde cliente agente; caracterizar todas las rutas alternativas antes del corte. | agente | matriz por conector, reemplazo, alternativa y evidencia; ambos reemplazos aislados |
| S7 | Retirar ambas rutas heredadas UID 1000 y revocar sus credenciales por separado, sin borrar evidencia. | **propietario** (revocación) | R13 PASS desde cliente agente para cada conector antiguo y todas las rutas alternativas |
| S8 | Ensayo de rollback: desactivar ambos reemplazos; consola local intacta; ambas rutas heredadas siguen retiradas. | propietario + agente | R16 PASS y repetir R13 desde cliente agente para ambos conectores y alternativas |
| S9 | M4 revisión Codex; M5 instalación sin autorización activa; luego grant separado de 20 min (M6) | Codex / propietario | gates M4/M5 del plan |

### Matriz de evidencia nominativa obligatoria (NOT_RUN)

| Conector heredado | Reemplazo diagnóstico | Antes del corte S6 | Después de S7 | Después del rollback S8 |
|---|---|---|---|---|
| anima-xps-direct-native | identidad dedicada, credencial independiente | aislamiento del reemplazo y alternativas: NOT_RUN | antiguo inaccesible: NOT_RUN | antiguo inaccesible: NOT_RUN |
| desktop-commander-remote | identidad dedicada, credencial independiente | aislamiento del reemplazo y alternativas: NOT_RUN | antiguo inaccesible: NOT_RUN | antiguo inaccesible: NOT_RUN |

Cada celda requiere identidad observada, fecha, ID de prueba y recibo sin secretos desde cliente agente. No se considera aislada una ruta por el resultado de la otra. Cualquier acceso administrativo alternativo bloquea M5.

La autorización no se habilita (AUTHZ disabled) hasta que S6–S8 y R1–R16 pasen en la XPS. Si cualquier ruta del agente conserva autoridad administrativa → **NO_GO**, fail closed.

## 6. Rollback

- Objetivo: volver a un estado seguro, no al estado anterior. Estado seguro = canal nuevo detenido, broker en denegación, MCP heredados **no** reactivados para agentes, consola local del propietario sin cambios.
- Recuperación R0 pendiente se completa antes de detener el broker; el rollback no cancela una restauración comprometida.
- Reactivar los MCP heredados bajo UID 1000 es una decisión del propietario fuera de AUTHZ y anula cualquier declaración de aislamiento.
- Sin borrar recibos, marcadores, identidades ni respaldos.

## 7. Pruebas negativas R1–R16 (especificación, NOT_RUN)

Ejecutar desde cada ruta MCP disponible al agente (nueva y heredada). Ninguna ha sido ejecutada; no se reporta resultado.

| ID | Ruta comprobada | Esperado desde agente |
|---|---|---|
| R1 | `sudo -n` / binarios setuid | denegado (NNP y sin sudoers); no se interpreta como prueba de ausencia de root |
| R2 | pertenencia a `sudo`, `adm`, `docker`, `lxd`, `wheel` u otros administrativos | `id` sin grupos suplementarios |
| R3 | socket Docker | sin acceso (permiso denegado) |
| R4 | socket/API LXD | sin acceso |
| R5 | bus de sesión y `/run/user/1000` del propietario | sin acceso |
| R6 | bus de sistema: gestión de unidades (`StartUnit`, `Manage*`) y polkit | denegado |
| R7 | home del propietario, `.config`, `.ssh`, `.config/anima/xps-local-mcp`, `.openclaw` | sin lectura ni escritura |
| R8 | credenciales de conectores heredados y del propietario | inaccesibles; la credencial nueva no es la heredada |
| R9 | listeners TCP loopback (gjs, GNOME Remote Desktop, ollama, tunnel-client y resto inventariado) | bloqueados por filtro de la unidad agente o con autenticación verificada sin autoridad; sin cerrar servicios del propietario |
| R10 | 3 sockets abstractos | inventariados; sin vía administrativa comprobada; si no puede bloquearse ni autenticarse → NO_GO |
| R11 | socket del broker instalado: comandos fuera de catálogo, `grant`, `revoke`, >8 bytes, sin EOF | `DENIED`/`ERROR` sin consumo (casos P de la interfaz; el PASS de transporte de laboratorio no sustituye esta prueba sobre el socket instalado) |
| R12 | `SO_PEERCRED` con UID/GID distinto | rechazo |
| R13 | canal MCP heredado tras S7 | inaccesible a agentes |
| R14 | estado, política, recibos, marcador, código y configuración del broker | sin escritura; lectura solo de estado sanitizado |
| R15 | capacidades y syscalls de módulos desde agente y trabajador `audit` | sin `CAP_SYS_MODULE`; carga/descarga denegada (solo en laboratorio) |
| R16 | rollback (S8) | no reabre canal administrativo; consola local intacta |

Además aplican G-LEASE, G-THERM, G-LEDGER, G-R0 y G-AUDIT del plan (M4).

## 8. Stoppers

| Estado | Elemento | Evidencia | Acción mínima / prueba posterior |
|---|---|---|---|
| HUMAN_REQUIRED | Runtime independiente (S3) | Node y tunnel-client solo en home 0700 | Propietario instala y verifica runtime root-owned fuera de home; prueba: hash, propietario, ejecución bajo `xps-agent` en laboratorio y luego XPS. Razón: instalación en sistema requiere autenticación local |
| HUMAN_REQUIRED | Cuenta `xps-agent` y credenciales nuevas (S4) | `xps-agent` ausente; credenciales actuales en home | Propietario crea la cuenta y emite credenciales nuevas por conector; prueba: R2, R8. Razón: creación de cuentas y emisión de credenciales son del propietario |
| HUMAN_REQUIRED | Revocación de tokens heredados (S7) | MCP heredados activos bajo UID 1000 | Propietario revoca tokens tras aceptar S5–S6; prueba: R13. Razón: irreversible para la sesión actual |
| TECHNICAL_BLOCKED | Sockets abstractos y listeners loopback | 3 abstractos, 8 loopback sin autenticación caracterizada | Caracterizar en laboratorio (S1–S2); si no aislables → fail closed |
| TECHNICAL_BLOCKED | Q-001 (contrato) | mecanismo de credenciales por conector no verificado | resolver con S2–S5 |
| PASS laboratorio / producción pendiente | Broker | 10/10 pruebas, revisión PASS y composición real de política; sin ACK ante ledger_fault | validar registro durable de rechazos, servicio instalado e identidad real; no habilitar producción |
| NOT_RUN | R1–R16, P13–P16, G-*, migración S0–S9 | sin ejecución | laboratorio primero; XPS después de S3–S5 |

No se solicita shell root, cambios en el home o grupos del propietario, ni otra aprobación general del diseño.
