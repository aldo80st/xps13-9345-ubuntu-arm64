# Contrato operativo — intervención humana mínima

**Propósito:** resolver los problemas del Dell XPS 13 9345 con la mayor autonomía técnica posible **sin transferir al usuario trabajo que el asistente puede realizar**. Este contrato gobierna el sprint y complementa el [gate de soluciones upstream](sprint-2026-11-01-upstream-solutions-review.md) y el [runner de diagnóstico](sprint-cycle-method.md).

## Regla única

> **El asistente sigue trabajando hasta encontrar un límite real, específico y demostrado. El usuario solo interviene para aprobar una operación protegida o aportar una observación física que no pueda obtenerse por herramientas.**

La falta de capacidades de un script NO significa que el usuario deba actuar ni que el sprint esté resuelto.

## Un ciclo; seis pasos

```
OBSERVAR → CONTRASTAR → DECIDIR → ACTUAR → VERIFICAR → REGISTRAR
     ↑                                                |
     └── repetir si existe una acción nueva segura ───┘
```

**1. Observar.** Recoger una línea base y reproducir el síntoma. Distinguir falla funcional de aviso de arranque, restricción de sandbox y resultado histórico.

**2. Contrastar.** Consultar el paquete oficial, parche upstream y solución comunitaria correspondiente; comprobar aplicabilidad exacta a modelo, versión y configuración. No reinventar lo disponible.

**3. Decidir.** Elegir **APLICAR**, **ADAPTAR**, **ESPERAR** o **DESCARTAR** con causa, riesgo, evidencia necesaria y reversión.

**4. Actuar.** Ejecutar un cambio mínimo autorizado, reversible y aislado. Primero una prueba RED en cambios de software; después GREEN. No repetir acciones idénticas que no produzcan información nueva.

**5. Verificar.** Probar la funcionalidad real, comparar antes/después y vigilar regresiones. Un driver enumerado, un servicio activo o un log limpio **no** validan por sí solos una función.

**6. Registrar.** Persistir evidencia privada, una síntesis publicable sin secretos, estado por issue, propietario del siguiente paso y criterio de terminación.

## Enrutamiento exacto de cada pendiente

| Estado operativo | Quién actúa | Regla |
| --- | --- | --- |
| **TRABAJO_TECNICO** | Asistente | Aún hay investigación, prueba segura, comparación, diseño o corrección posible. **No pedir intervención al usuario.** |
| **AUTORIZACION** | Usuario, **una sola acción** | El asistente ya preparó y verificó el cambio; necesita una aprobación administrativa o decisión de riesgo. Debe indicar efecto exacto, riesgo, reversión y qué aprobar. |
| **VERIFICACION_FISICA** | Usuario | No existe evidencia instrumental equivalente; el asistente pide la comprobación mínima y específica (p. ej. ambos monitores muestran imagen). |
| **DEPENDENCIA_EXTERNA** | Upstream / proveedor | Hay evidencia concreta de falta de soporte o release, con enlace, versión mínima y criterio de reanudación. Una hipótesis no basta para este estado. |
| **VERIFICADO** | Nadie | Criterio de aceptación funcional cumplido con evidencia; issue puede cerrarse. |
| **DESCARTADO** | Nadie | No se modifica, con justificación técnica explícita. |

El estado **LIMITE_DEL_EJECUTOR** es distinto de todos los anteriores: el script automatizado llegó al final de su whitelist, pero el asistente todavía tiene trabajo técnico que hacer con otras herramientas o mediante una extensión revisada del ejecutor. **Jamás se lo presenta como una autorización pendiente del usuario.**

## Contrato de escalamiento

**No pedir "haz esta investigación" o "ejecuta estos comandos"** cuando el asistente dispone de conexión autorizada. Ante privilegios elevados, solicitar aprobación usando el diálogo local del sistema operativo, sin contraseñas en chat.

Toda solicitud al usuario debe ser una **única acción ejecutable**, con este formato:

> **Necesito que apruebes [acción concreta].** Haré [operación específica]; afecta [alcance]; el riesgo es [riesgo] y la reversión es [método]. Después verificaré [criterio]. Si no autorizas, continuaré con los frentes independientes.

Agrupar autorizaciones compatibles; no interrumpir una investigación cada vez que aparece una hipótesis nueva. Ninguna aprobación implícita permite desactivar Secure Boot/shim, alterar MOK/EFI/BitLocker, flashear BIOS, arrancar kernels experimentales o activar amplificadores sin protección.

## Criterio de repetición y parada

- Repetir solo con **una acción nueva y segura**, prueba diferenciable, hipótesis nueva o evidencia nueva.
- Máximo **6 rondas por invocación**, timeout de 20 s por comando de diagnóstico y checkpoint por ronda. Nunca un `for` infinito.
- Ante error/rechazo: investigar la causa, no repetir indefinidamente; si no hay avance tras dos rondas, detener el ejecutor y cambiar de estrategia técnica.
- Parada del **ejecutor**: sin nuevas acciones autorizadas o sin progreso. Declarar por separado **TRABAJO_TECNICO pendiente del asistente**, **AUTORIZACION**, **VERIFICACION_FISICA** y **DEPENDENCIA_EXTERNA**.
- Cierre de **issue**: funcionalidad probada y criterios de aceptación satisfechos, o resolución externa/descartada claramente marcada. Nunca cerrar por silencio del kernel.
- Cierre del **sprint**: cada issue está verificado, descartado con fundamento o bloqueado externamente con evidencia y responsable identificado; las acciones humanas necesarias se presentan en el mínimo número de solicitudes. Un pendiente técnico del asistente impide declarar terminación del sprint.

## Aplicación inmediata en XPS

**Prioridad 1, asistente:** verificar si Ubuntu 7.3.0-10.10 integra LP #2131181 y qué ocurre con la confianza MOK/los keyrings del kernel. Solo la lectura privilegiada pendiente necesitará autorización local; no alterar Secure Boot.

**Prioridad 2, asistente:** investigar IRIS con datos ya capturados, evitando reintentos de decodificación que provocan errores de sesión.

**Prioridad 3, asistente:** estudiar protección real de amplificadores, EC térmico y controles de estabilidad sin pruebas físicas riesgosas.

**Cuando haga falta, usuario:** autorizar elevación administrativa de solo lectura, confirmar imágenes en los dos DisplayPort, aprobar reinicios o BIOS tras explicación y verificar audio cuando sea seguro.

**Estado honesto del motor actual:** `scripts/sprint_cycle.py` es un **runner de diagnóstico de solo lectura**, NO un agente que aplique correcciones del sistema. Su resultado `external_actions_only` significó únicamente que había agotado sus herramientas permitidas. **No equivale a que el asistente haya agotado el trabajo técnico**. Antes de automatizar correcciones, el motor debe incorporar estas distinciones con pruebas RED→GREEN y revisión del PR.
