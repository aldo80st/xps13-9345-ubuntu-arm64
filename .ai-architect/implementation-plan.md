# Architecture-Driven Implementation Plan — Hexagon NPU XPS 9345

## Accepted decisions
**ADR-001:** OPT-001 integración directa, aceptado el 2026-11-05. **Contrato:** `.ai-architect/architecture-contract.yaml`, rev. 1. Este handoff no autoriza ejecución ni cambios.

## Milestones

### M0 — Inventario de solo lectura
**Resultado:** kernel, FastRPC, permisos, firmware Dell y estado ADSP/CDSP revalidados. **Ámbito:** /sys, /dev y logs filtrados. **Restricciones:** ADR-001, privacidad/estabilidad. **Verificación:** evidencia anonimizada, ninguna mutación.

### M1 — Auditoría de dependencias
**Resultado:** versiones, arquitecturas, licencias y SHA256 de QAIRT/QNN/Genie, shells DSP y referencias upstream. **Ámbito:** investigación estática y guía t14s-x1e-npu. **Restricciones:** no blobs Lenovo; revisar scripts antes de root. **Verificación:** matriz de compatibilidad/procedencia y rollback; Q-001/Q-002 resueltas o documentadas.

### M2 — FastRPC y QNN (autorización operativa posterior)
**Resultado:** prueba calculadora FastRPC y `qnn-platform-validator --backend dsp --testBackend`. **Ámbito:** dependencias mínimas, aisladas si posible. **Restricciones:** no modificar kernel, firmware ni Secure Boot. **Verificación:** ejecución en CDSP sin regresión, procedimiento de aborto y reversión. Detener ante cuelgue.

### M3 — Inferencia real
**Resultado:** modelo pequeño ejecutado en NPU por QAIRT/Genie. **Ámbito:** modelo cuantizado compatible. **Restricciones:** no fallback CPU silencioso ni inferencia de éxito por presencia CDSP. **Verificación:** respuesta correcta, backend Hexagon observado, repetibilidad sin bloqueos.

### M4 — Comparar y resolver Go/No-Go
**Resultado:** CPU/GPU/NPU con latencia, tokens/s de prompt y decode, memoria; energía si medible. **Ámbito:** mismas entradas y versiones. **Restricciones:** no extrapolar TOPS o pruebas Lenovo. **Verificación:** tabla reproducible; No-Go si inestable o sin beneficio objetivo.

### M5 — API local opcional (nueva decisión)
**Resultado:** si M4 es Go, evaluar servidor ya existente en loopback. **Ámbito:** sin nuevo daemon salvo justificación y ADR. **Restricciones:** no exposición remota; agentgateway sigue siendo único acceso MCP de Ánima. **Verificación:** diseño aprobado antes de implementar.

## Cross-cutting constraints
Aplicar ADR-001 y restricciones del contrato. Privilegios mínimos, fuentes verificadas, rollback, evidencia anonimizada. No SIGKILL indiscriminado en FastRPC activo; exigir recuperación documentada. Cambios en rama/worktree, sin merge ni despliegue automático.

## Explicit non-goals
Driver/kernel/firmware propios, redistribuir blobs, código de aplicación en esta fase, producción, integración de Nexora o Ánima.

## Unresolved questions
Q-001 y Q-002 bloquean M2; Q-003 condiciona medición de M4. Toda instalación, compilación, ejecución de herramientas, cambio de permisos o reinicio requiere autorización específica.
