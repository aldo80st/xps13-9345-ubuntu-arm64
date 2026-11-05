---
schema_version: "1.0.0"
revision: 1
decision:
  id: "ADR-001"
  title: "Integración directa y reversible de NPU Hexagon en Dell XPS 9345"
  status: "accepted"
  context: "Snapdragon X Elite X1E80100 en Ubuntu 26.10 ARM64, kernel 7.3.0-10-generic. El 2026-11-05 se observaron FastRPC cargado, dispositivos /dev/fastrpc-cdsp y -secure, firmware Dell HAMOA-1, ADSP/CDSP running. No se demostró inferencia NPU. El repositorio público exige cambios reversibles, trazabilidad y no redistribución de blobs."
  drivers:
    - "Usar componentes existentes, sin crear controlador ni motor de inferencia."
    - "Preservar la estabilidad del XPS y minimizar privilegios."
    - "Medir inferencia verdadera, rendimiento y rollback."
  considered_option_ids:
    - "OPT-001"
    - "OPT-002"
    - "OPT-003"
  selected_option_id: "OPT-001"
  decision: "Se acepta OPT-001: integración directa, primero con QAIRT/QNN/Genie y FastRPC existente. Utilizar t14s-x1e-npu solo como referencia, sin instalar firmware Lenovo; evaluar GenieX/llama.cpp como rutas opcionales. No construir APIs ni abstracciones hasta demostrar necesidad. Esta aprobación autoriza documentación, NO ejecutar código de aplicación ni instalar o alterar el sistema."
  positive_consequences:
    - "Menos código y mantenimiento propios."
    - "Validación incremental antes de cualquier instalación."
    - "Posibilidad futura de integración local."
  negative_consequences:
    - "Compatibilidad X Elite + Linux ARM64 no garantizada en QAIRT/GenieX."
    - "Riesgo de cuelgues FastRPC/dspqueue y licencias propietarias."
    - "La NPU podría rendir menos que la GPU."
  assumptions:
    - "Kernel y firmware son observaciones puntuales, no garantías."
    - "No hay todavía validación de inferencia NPU."
    - "Cambios de sistema requerirán nueva autorización."
  validation_criteria:
    - "FastRPC y qnn-platform-validator comprueban uso real de CDSP sin regresiones."
    - "Un modelo pequeño genera salida válida en NPU, sin fallback oculto."
    - "Benchmarks reproducibles de CPU/GPU/NPU registran latencia y tokens/s."
    - "Cada intervención aprobada tiene criterio de aborto y rollback documentado."
  supersedes: []
---

# ADR-001: Integración directa y reversible de NPU Hexagon en Dell XPS 9345

**Aceptada el 2026-11-05.**

## Contexto
Snapdragon X Elite X1E80100 en Ubuntu 26.10 ARM64, kernel 7.3.0-10-generic. El 2026-11-05 se observaron FastRPC cargado, dispositivos /dev/fastrpc-cdsp y -secure, firmware Dell HAMOA-1, ADSP/CDSP running. No se demostró inferencia NPU. El repositorio público exige cambios reversibles, trazabilidad y no redistribución de blobs.

## Opciones consideradas
- OPT-001: integración directa (elegida).
- OPT-002: arquitectura por capas con servicio propio (diferida).
- OPT-003: puertos y adaptadores (diferida).

## Decisión
Se acepta OPT-001: integración directa, primero con QAIRT/QNN/Genie y FastRPC existente. Utilizar t14s-x1e-npu solo como referencia, sin instalar firmware Lenovo; evaluar GenieX/llama.cpp como rutas opcionales. No construir APIs ni abstracciones hasta demostrar necesidad. Esta aprobación autoriza documentación, NO ejecutar código de aplicación ni instalar o alterar el sistema.

## Consecuencias positivas
- Menos código y mantenimiento propios.
- Validación incremental antes de cualquier instalación.
- Posibilidad futura de integración local.

## Consecuencias negativas
- Compatibilidad X Elite + Linux ARM64 no garantizada en QAIRT/GenieX.
- Riesgo de cuelgues FastRPC/dspqueue y licencias propietarias.
- La NPU podría rendir menos que la GPU.

## Supuestos
- Kernel y firmware son observaciones puntuales, no garantías.
- No hay todavía validación de inferencia NPU.
- Cambios de sistema requerirán nueva autorización.

## Criterios de validación
- FastRPC y qnn-platform-validator comprueban uso real de CDSP sin regresiones.
- Un modelo pequeño genera salida válida en NPU, sin fallback oculto.
- Benchmarks reproducibles de CPU/GPU/NPU registran latencia y tokens/s.
- Cada intervención aprobada tiene criterio de aborto y rollback documentado.
