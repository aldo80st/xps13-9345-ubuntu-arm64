# XPS — contrato de ejecución de agentes

**Decisión del propietario — 2026-11-24.** Obligatoria para los sprints de este repositorio, sus agentes y la coordinación desde ChatGPT/Paseo.

## Objetivo y distribución

Optimizar Dell XPS 13 9345 Ubuntu ARM64: estabilidad, seguridad, eficiencia energética, refrigeración, compatibilidad y aprovechamiento de hardware. Paseo en LUCIFER01 coordina ingeniería; Claude implementa, Codex revisa independientemente; la XPS ejecuta pruebas deterministas y compilaciones ARM64 indispensables. OpenProject registra trabajo cuando está disponible; GitHub conserva código, decisiones y evidencia. No ampliar alcance hacia otros proyectos.

## ITERA — contrato de cada sprint

1. Recuperar estado vivo, evidencia, issues existentes, sesiones de Paseo, restricciones y permisos. Reutilizar trabajo; evitar duplicar agentes, repositorios o soluciones.
2. Separar paquetes independientes; ejecutar en paralelo cuando capacidad y aislamiento lo permitan. No confundir despacho de agente con entrega.
3. **DIAGNOSTICAR → PROPONER → IMPLEMENTAR → PROBAR → REVISAR → CORREGIR → VOLVER A PROBAR.** Cada sprint comprende varias iteraciones con resultados verificables, no una sola pasada de planificación. Repetir mientras existan acciones autorizadas factibles que reduzcan una brecha o resuelvan un bloqueo.
4. Ante fallo, conservar evidencia, aislar causa, ensayar la siguiente corrección mínima y reversible. No repetir intentos idénticos ni eludir controles, cuotas, permisos o gates. Si una rama está bloqueada, continuar las demás.
5. Integrar únicamente candidatos con evidencia de aceptación y revisión aplicable; distinguir pruebas de laboratorio, aceptación física y despliegue. No inventar resultados ni porcentajes de progreso.
6. Destilar los stoppers al final: **HUMAN_REQUIRED** solo cuando la acción dependa realmente del propietario (autorización explícita, acceso legítimo, acción física, decisión irreversible); **TECHNICAL_BLOCKED** para limitaciones técnicas externas o evidencias insuficientes; **IN_PROGRESS** para trabajo delegado en ejecución; **NOT_RUN** si no fue probado. Para cada stopper humano: evidencia, acción mínima exacta, razón y prueba posterior. No pedir al propietario tareas que el agente pueda realizar legítimamente.
7. Cerrar el ciclo de conversación solo tras agotar el trabajo autónomo factible en ese ciclo, o si un límite real de ejecución lo impide. No prometer ejecución futura desde el chat. Conservar checkpoint verificable y estado de agentes ya ejecutándose; no atribuirles resultados no recuperados.

## Límites

- No modificar kernel activo, cargar módulos experimentales, firmware, BIOS, DTB de arranque, GRUB, EFI, Secure Boot, BitLocker, particiones o reiniciar sin superar sus gates y obtener autorización específica.
- No borrar respaldos originales, ramas, worktrees ni evidencias sin permiso y recuperación comprobada. Mantener configuraciones y datos de terceros fuera de alcance.
- Preservar cambios locales ajenos y no debilitar permisos, sandbox, autenticación ni controles de herramientas.
- Usar scripts deterministas acotados, artefactos privados, SHA-256 y rollback. Las compilaciones aisladas no autorizan instalar ni activar artefactos.

## Cierre

Registrar en los issues rectores [#50](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/50) y [#58](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/58) las iteraciones, operaciones reales, métricas antes/después, pruebas, commits y dictámenes, estados de paquetes, stoppers y checkpoint. No detener el trabajo técnico por indisponibilidad de OpenProject. El cierre de un ciclo no implica cierre de un sprint cuyos criterios de aceptación sigan pendientes.
