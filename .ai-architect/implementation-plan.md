# Plan de implementación — XPS AUTHZ v1.1 y asignación v0.3

## Decisiones aceptadas

ADR-001 y ADR-002, contrato revisión 4. Los hitos M0–M6 de AUTHZ permanecen independientes. XPS-03; AGENTS.md y #58 gobiernan. No instalar el piloto v1. Diseño aprobado no es autorización operativa.

## Milestones

| Hito | Resultado y alcance | Dependencia y aceptación |
|---|---|---|
| M0 | ADR, contexto, contrato y handoff en un único commit. | Validadores canónicos, escaneo de secretos, lectura exacta posterior; revisión independiente antes de integrar. |
| M1 | Inventario por metadatos de ambos MCP, identidades, sockets, credenciales, rutas alternativas; diseño de migración y rollback. | M0; laboratorio sin cambios al host, sin exponer secretos; identidad no administrativa. |
| M2 | Claude implementa catálogo, política, ejecutores, recuperación y recibos en rama aislada. | M0; reutilizar v1 solo tras revisar; tests de boot, consumo, caducidad, concurrencia, revocación, fallos y hash. Auditoría lee módulos sin poder cargarlos. |
| M3 | Adaptador MCP de identidad restringida, paralelo para validación; migración controlada. | M1/M2; verificar identidad de proceso y ausencia de rutas administrativas; retirar canales heredados de agentes tras aceptar nuevo canal y rollback; conservar administración local. |
| M4 | Codex revisa independientemente; pruebas de instalación en laboratorio y validación de sudoers/unidades, propietarios, permisos y fallos. | M2/M3; pruebas negativas de escalamiento, manipulación, reutilización, desconexión, expiración, revocación, recuperación. CI y revisión PASS. |
| M5 | Instalación autenticada por propietario, sin autorización activa. | M4 y autorización local; comprobar denegación y separación efectiva. Grant separado 20 min. |
| M6 | Auditoría, R0 oficial y térmica nativas, una a una. | M5; trabajo guardado, video/cámara cerrados, energía y sensores válidos. R0 restaura stock y pasa smoke CPU/Iris 120 cuadros. Térmica aborta por umbral y revocación. No candidato ni reinicio. |

## Restricciones transversales

ADR-001: separar autoridad de identidad; proteger código, políticas y evidencias; registrar ID, hashes y resultados. Consumir antes de efectos; un efecto admitido por vez; recuperación prioritaria. No autorizar intérpretes o scripts de home como root. Ensayar cambios de kernel, artefacto, procesos ocupados, timeout y pérdida de sesión. No heredar credenciales personales. Ingeniería LUCIFER01, aceptación XPS; no simular aislamiento usando canal administrativo. Registrar gates en #58; distinguir PASS estático, NOT_RUN, TECHNICAL_BLOCKED y HUMAN_REQUIRED.

## Gates de corrección M0 / M4 (revisión 2)

| Gate | Prueba negativa / aceptación |
|---|---|
| G-ID | Desde cada MCP y el canal heredado, probar ausencia de escalamiento por grupos, sockets de Docker/LXD, sesión/bus, archivos/credenciales del propietario y gestión de servicios; si existe ruta administrativa accesible, M3/M5 NO_GO. Rollback no restablece esa ruta; conservar consola local. |
| G-LEASE | Simular reloj BOOTTIME, expiración entre admisión y compromiso, revocación concurrente, reinicio de controlador, nuevo boot, duplicación de solicitudes. No efectos nuevos sin lease vigente; consumo durable, no devuelto por fallo. |
| G-THERM | Expiración/revocación durante carga, sensor ausente o umbral; observar parada en hasta 2 s en host responsivo con muestreo objetivo 250 ms y supervisor con límite de trabajador 12 s; nunca afirmar tiempo real. |
| G-LEDGER | Fallo de escritura/fsync, disco lleno, corte antes/después del consumo, permisos y manipulación. Recibo durable antes de efectos y resultado correlacionado; fallo niega operaciones nuevas, no cancela recuperación de seguridad pendiente. |
| G-R0 | Marcador durable antes de descargar; supervisor recupera módulo oficial tras caída del ejecutor/controlador, desconexión o timeout. Presupuesto de fase/restauración alineado. No reintentar descarga. Si falla carga o smoke, conservar marcador y bloqueo. Verificar stock y smoke 120 cuadros antes de quitarlo. Boot distinto: reconciliación local sin carga automática. |
| G-AUDIT | Auditoría lee los archivos necesarios sin CAP_SYS_MODULE ni syscalls de carga/descarga; comprobar ambos efectos negativos en laboratorio, no ejecutar carga de prueba en XPS. Recibo durable obligatorio. |

Los gates precisan la decisión aceptada sin ampliar catálogo. M2 se implementa aislado; M3/M5 no habilitan acceso hasta completar las negativas. M6 requiere propietario autenticado, preparación física, grant vigente; no reinicio ni candidato.

## No objetivos

Sin arranque, reinicio, firmware, módulos experimentales, Secure Boot/BitLocker, particiones, ajustes persistentes de ventilador, root general ni otros endpoints. No instalar v1.

## Preguntas pendientes

Q-001 bloquea migración real M1/M3. Q-002 bloquea M4/M5. Confirmar preparación física y activar localmente cuando los gates técnicos estén cerrados; TTY sola no acredita presencia. Auditoría EC/SB y arranque experimental continúan como gates separados.

## Carril de asignación presupuestaria (ADR-002)
IDs P0–P7 separados de AUTHZ. No ejecutar paquetes de aplicación por la sola aprobación de arquitectura.

| Hito | Resultado, alcance y dependencia | Aceptación observable |
|---|---|---|
| P0 | ADR-002 y bundle completo, revisión 3. | Validación canónica, escaneo y lectura exacta; revisión independiente. |
| P1 | resource-inventory, adaptadores de observación Paseo y límites por cuenta/modelo/ventana. | Fixtures de cuota compartida, múltiple ventana, expiración, UNKNOWN, modalidad y privacidad; no secretos. |
| P2 | performance-history, taxonomía y registro de paquetes. | Métricas separadas por modelo/versión/esfuerzo/clase; distinguir fallo de entorno y ausencia de datos. |
| P3 | allocation-policy, recomendación determinista en sombra. | Replay estable; elegibilidad antes de ranking; cero despacho y gasto; elegir herramienta no generativa cuando suficiente. |
| P4 | budget-ledger, reservas simuladas simultáneas, dependencias y revisores. | Carrera, doble conteo, agotamiento, renovación, uso externo y cuota desconocida; reserva de revisión y contingencia. |
| P5 | paseo-adapter, correlación y reconciliación simulada/observacional. | Timeout sin ID, respuesta tardía, caída, duplicado y checkpoint; ningún reenvío sin reconciliar. |
| P6 | Comparación en sombra XPS, calibración propuesta. | Resultados aceptados, consumo cuando observable, duración y retrabajo; cero despachos del selector y ningún gasto extra; informe de incertidumbre. |
| P7 | Activación futura revisada de asignación con Paseo existente. | P1–P6 PASS, Q-003/Q-004 resueltas por modalidad, revisión independiente, aceptación explícita de transición AGENTS.md, rollback a coordinación manual sin duplicar paquetes. |

Restricciones: presupuesto adicional 0 MXN; cuotas de suscripción no equivalen a tokens API; aplicar todos los límites sin doble conteo. Reservas iniciales pagadas 65/25/10 y gratuitas 85/10/5, ajustables solo con evidencia y aprobación. No confundir disponibilidad anunciada con despacho confirmado. No usar otros proyectos como banco de pruebas ni introducir infraestructura redundante. Mantener autorización hardware ADR-001 intacta, incluido G-ID. No activar facturación ni comprar créditos. Datos y cuotas desconocidos se registran como tales. La coordinación manual continúa hasta P7.

### Precisión de calidad (revisión 4)
P1: identificar versión y arnés realmente disponibles; conservar referencias externas fechadas y condiciones de evaluación. P2: taxonomía con implementación, pruebas, refactorización, comprensión, diagnóstico, seguridad y herramientas. P3: probar precedencia de calidad sobre gratuidad cuando existe diferencia material y umbral de calidad; si candidatos equivalentes dentro de incertidumbre, elegir menor coste de oportunidad. P6: comparar paquetes equivalentes, resultados independientes, consumo y retrabajo; no promover un modelo por ranking genérico. P7: mantener presupuesto cero y gates de ADR-001. Ningún benchmark autoriza instalar, despachar o facturar.
