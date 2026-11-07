# Contexto — piloto NPU XPS 9345

**Corte:** 2026-11-05. **Repositorio:** `aldo80st/xps13-9345-ubuntu-arm64`. **Base analizada:** `5d8addf71aed44b7a5cbe212cb80af5ce7a30257`. **ADR:** ADR-001 aceptado.

## Objetivo y realidad observada
Inferencia Hexagon local y reproducible en Snapdragon X Elite X1E80100 sin crear controlador ni runtime. Ubuntu 26.10 ARM64, kernel 7.3.0-10-generic; FastRPC cargado; `/dev/fastrpc-{adsp,cdsp,cdsp-secure}` presentes; firmware Dell `CDSP.HT.2.9.c1-00046-HAMOA-1`; remoteproc adsp/cdsp en `running`. No se detectaron ejecutables QNN/Genie ni se probó inferencia. Journal mostró alertas de FastRPC/DMA y QRTR cuyo impacto no se ha establecido.

## Reglas existentes
README y CONTRIBUTING del repositorio exigen soluciones reversibles, verificación de origen/hash y no publicar datos sensibles ni firmware propietario. No desactivar Secure Boot como solución predeterminada. El repositorio no se halló clonado bajo `/home/amarquez/projects`; se examinó en GitHub. Antes de este cambio, no había `.ai-architect/` en main.

## Referencias candidatas, todavía no verificadas en este XPS
- https://github.com/UnsignedChad/t14s-x1e-npu — referencia X1E Linux; advierte riesgo dspqueue.
- https://github.com/qualcomm/GenieX — X Elite documentado en Windows, Linux ARM64 validado para otros Qualcomm.
- https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/linux.md
- https://docs.qualcomm.com/nav/home/QNN_general_overview.html

**Estado:** aprobado el diseño, pendientes compatibilidad, validación funcional y benchmarks. Este paquete no concede autorización de instalación, ejecución de aplicaciones ni cambios al sistema.
