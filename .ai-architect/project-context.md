# XPS AUTHZ v1.1 — contexto

Decisión del propietario: 2026-11-24. Alcance exclusivo XPS-03, Dell XPS 13 9345 Ubuntu ARM64. AGENTS.md gobierna ejecución, evidencia y autorizaciones. #58 es el checkpoint.

La XPS ejecuta 7.3.0-11-generic. Observación de 14:01–14:02 CST: ambos MCP (anima-xps-direct-native y desktop-commander-remote) activos bajo UID 1000, con grupos sudo, docker y lxd. Socket Docker root:docker 0660. No se observó cuenta xps-agent ni controlador instalado. El piloto v1 queda NO_GO. Una identidad nueva no basta si los agentes conservan rutas administrativas antiguas. La auditoría EC H01 se ejecutó; no implica permiso de arranque ni R0.

Objetivo: autoridad del propietario separada de la identidad agente; operaciones deterministas, acotadas, auditables y reversibles. Mantener administración local y acceso de recuperación. Paseo/LUCIFER01 coordina ingeniería, Claude implementa, Codex revisa; la XPS ejecuta aceptación nativa. ADR-001 y contrato revisión 2. La aprobación de diseño no concede privilegios operativos. No almacenar secretos.

**Reconciliación M0, 14:11 CST:** revisión independiente Codex CHANGES_REQUIRED. Revisión 2 precisa frontera de ambas rutas MCP, compromiso irreversible, caducidad/revocación, persistencia antes de efectos, recuperación de Iris y pruebas negativas. No modifica la decisión aprobada ni amplía operaciones. M1/M2 siguen sin aceptación nativa. La TTY no prueba presencia física; el agente nunca solicita credenciales del propietario.
