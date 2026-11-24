# Plan de implementación — XPS AUTHZ v1.1

## Decisiones aceptadas

ADR-001, contrato revisión 1. XPS-03; AGENTS.md y #58 gobiernan. No instalar el piloto v1. Diseño aprobado no es autorización operativa.

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

## No objetivos

Sin arranque, reinicio, firmware, módulos experimentales, Secure Boot/BitLocker, particiones, ajustes persistentes de ventilador, root general ni otros endpoints. No instalar v1.

## Preguntas pendientes

Q-001 bloquea migración real M1/M3. Q-002 bloquea M4/M5. Confirmar preparación física y activar localmente cuando los gates técnicos estén cerrados; TTY sola no acredita presencia. Auditoría EC/SB y arranque experimental continúan como gates separados.
