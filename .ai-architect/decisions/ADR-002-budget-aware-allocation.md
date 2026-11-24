---
schema_version: "1.0.0"
revision: 1
decision:
  id: ADR-002
  title: Asignación adaptativa consciente de cuotas y presupuesto
  status: accepted
  context: El propietario aprobó la política v0.3 el 24 de noviembre de 2026. Dispone de suscripciones OpenAI y Anthropic y desea aprovechar modalidades gratuitas como Google. Se necesita maximizar trabajo aceptado sin gasto adicional ni roles fijos.
  drivers:
    - Aprovechar cuotas contratadas y gratuitas sin doble conteo.
    - Calidad y revisión independiente por clase de tarea.
    - No conceder privilegios ni exponer datos por ahorro.
    - Evitar duplicar trabajos cuando Paseo no confirma despacho.
  considered_option_ids: [OPT-004, OPT-005, OPT-006]
  selected_option_id: OPT-006
  decision: Adoptar un coordinador determinista de asignación presupuestaria sobre Paseo existente, inicialmente en modo sombra XPS, con inventario de recursos, reservas, evidencia de desempeño y reconciliación. Cero MXN de gasto adicional por defecto. ADR-001 permanece vigente; la transición operativa necesita aceptación separada.
  positive_consequences:
    - Selección de modelo y esfuerzo según resultados y capacidad utilizable.
    - Conservación de capacidad para revisar, corregir y cerrar.
    - Decisiones reproducibles con procedencia y motivos.
  negative_consequences:
    - Telemetría de cuotas heterogénea e incompleta.
    - Calibración requiere evidencia comparable y tiempo.
    - No se garantiza presupuesto exacto sin visibilidad de consumo externo.
  assumptions:
    - Las reservas iniciales son parámetros provisionales, no mediciones.
    - Las modalidades gratuitas se validan individualmente para privacidad y facturación.
    - La reutilización futura en Ánima no autoriza modificar ese proyecto.
  validation_criteria:
    - No gasto adicional, ni cambio silencioso de autenticación o facturación.
    - Todos los límites aplicables se evalúan sin duplicar cuotas compartidas.
    - Recomendación reproducible con entradas y versión fijas; UNKNOWN explícito.
    - Despacho incierto conserva reserva y se reconcilia antes de reasignar.
    - Modo sombra no despacha ni altera agentes, privilegios o configuración.
    - Activación futura requiere pruebas de concurrencia, revisión independiente, aceptación y rollback.
  supersedes: []
---

# ADR-002: Asignación adaptativa consciente de cuotas y presupuesto

Aceptado por el propietario el 2026-11-24 tras aprobar v0.3. Complementa ADR-001 y no lo sustituye.

OPT-004: asignación manual con roles fijos; limitada frente a cambios de cuota y clase de tarea. OPT-005: ranking ponderado individual v0.1; insuficiente para límites compartidos y dependencias. OPT-006: política determinista de admisibilidad, asignación colectiva, presupuestos y adaptación; seleccionado.

Usar primero herramientas deterministas cuando sean suficientes y preferir modalidades gratuitas aptas; aprovechar capacidad pagada próxima a renovar sin consumir por consumir. Reservas iniciales propuestas en v0.3: pagadas 65/25/10, gratuitas 85/10/5 para ejecución, revisión y contingencia. Registrar unidad real de cada límite, tokens observables por separado, incertidumbre y resultados aceptados. Cero gasto adicional. Implantación inicial observacional; no habilitar control automático hasta P7. El ámbito actual es exclusivamente XPS.
