---
schema_version: "1.0.0"
revision: 1
decision:
  id: ADR-001
  title: Separación de identidades y autoridad privilegiada acotada
  status: accepted
  context: El piloto AUTHZ v1 comparte cuenta administrativa con los MCP. La auditoría debe leer archivos de módulos sin poder cargar módulos. El propietario aprobó v1.1 el 24 de noviembre de 2026.
  drivers:
    - Privilegio mínimo y denegación predeterminada.
    - Autonomía temporal sin compartir credenciales.
    - Recuperación independiente de la sesión MCP.
    - Migración reversible conservando administración local.
  considered_option_ids:
    - OPT-001
    - OPT-002
    - OPT-003
  selected_option_id: OPT-002
  decision: Adoptar identidad de servicio xps-agent no administrativa separada del propietario, controlador local determinista, catálogo fijo, política y recibos protegidos por root y ejecutores systemd diferenciados. El agente no puede otorgarse autoridad. No declarar aislamiento efectivo mientras existan rutas administrativas disponibles al agente.
  positive_consequences:
    - Separación entre solicitante y autoridad de aprobación.
    - Vigencia, consumo, revocación y recuperación verificables.
    - No requiere microservicios, base de datos ni otro gateway.
  negative_consequences:
    - Migración controlada de ambos conectores y sus credenciales.
    - Instalación y activación requieren autenticación local.
    - Aislamiento y recuperación deben verificarse en Ubuntu ARM64.
  assumptions:
    - Root y kernel no comprometidos; el propietario conserva administración local.
    - Una TTY no demuestra presencia física; la confirmación de preparación es separada.
    - Las rutas antiguas se retiran del alcance agente después de validar el nuevo canal y su rollback.
  validation_criteria:
    - El agente no concede, renueva ni altera permisos, código o recibos.
    - Denegación antes del grant, tras caducidad, revocación o agotamiento.
    - Pruebas negativas de rutas administrativas alternativas desde los conectores agente, grupos, sockets y credenciales.
    - Auditoría solo lectura con acceso a archivos de módulos; R0 exclusivamente oficial, recuperación sin reinicio automático.
    - Prueba térmica sin privilegios, límites y aborto comprobados.
  supersedes: []
---

# ADR-001: Separación de identidades y autoridad privilegiada acotada

Aceptado el 2026-11-24. No es grant operativo ni permiso de instalación.

OPT-001: piloto v1 con identidad administrativa compartida; descartado por falta de frontera efectiva. OPT-002: controlador local con identidad dedicada y operaciones fijas; seleccionado. OPT-003: servicio remoto de administración privilegiada general; descartado por complejidad y superficie innecesarias.

Conservar política inicial de 20 minutos, cinco auditorías, un R0 y una térmica. Recuperación incluida exclusivamente para R0 admitido. Excluir arranque, firmware, reinicios y módulos experimentales. Mantener cuenta del propietario y rollback de migración sin devolver acceso administrativo a agentes. Ver contrato y plan.
