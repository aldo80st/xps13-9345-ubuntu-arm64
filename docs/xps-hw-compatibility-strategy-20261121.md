# XPS-HW-01 — Estrategia integral de compatibilidad (ARM64 / Snapdragon X Elite)

**Fecha:** 2026-11-21 · **Equipo:** Dell XPS 13 9345 · **Base:** Ubuntu 26.10 ARM64, Linux 7.3.0-11 · **Estado:** plan de integración + implementación segura de evidencia, NO despliegue.

## Propósito y relación con lo existente

La meta es convertir problemas heterogéneos de soporte Linux (reinicios, EC/PMIC/SCMI, video Iris/Adreno, pantallas DisplayLink, audio SoundWire, firmware, NPU, conectividad, hibernación) en una **matriz verificable de compatibilidad**, ensayos aislados y candidatos de corrección reproducibles. No escribir otro controlador EC ni mantener una bifurcación permanente de Linux.

**Autoridad y anti-duplicación:**
- [#50](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/50) XPS-VAL-01 mantiene **exclusividad** sobre EC/PMIC/reinicio/térmico (V0–V6, #51–57). Esta estrategia lo consume, no lo renombra ni aumenta su alcance.
- [#3](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/3) conserva el defecto EC/ventiladores, [#5](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/5) BIOS, [#21](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/21) la hibernación; reutilizar #26/#27/#40/#46/#49.
- [#1](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/1) controla EVDI / Secure Boot; [#2](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/2) firmware Iris; [#4](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/4) audio; [#12](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/12) SCMI; [#13](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/13) NPU; [#15](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/15) métricas GPU.
- Los documentos y scripts existentes `docs/thermal-hibernation-integration.md`, `docs/qcom-iris.md`, `scripts/diagnose-readonly.sh`, `scripts/hibernate-*.py`, `scripts/stage-dell-ec-v8.py` son recursos de referencia, no se sustituyen.

## Política de seguridad

1. Baseline OBSERVADO/INFERIDO/NO_VERIFICADO/RESUELTO, **no equiparar** coincidencia temporal con causalidad o ausencia de errores con solución.
2. No instalar drivers/MOK, BIOS, EC, DTB, kernel, GRUB, EFI, Secure Boot, BitLocker, cambios de red, suspensión, estrés térmico ni reinicios en la XPS sin autorización **específica separada** y rollback.
3. No modificar otros nodos del homelab. Solo scripts opt-in sin privilegios y pruebas con fixtures dentro de worktree independiente.
4. Nunca registrar o publicar seriales, SSID, MAC/IP, EDID, rutas personales, tokens, IDs de Tailscale, claves o journals crudos; datos mínimos por lista blanca.
5. Para compatibilidad cruzada, comparar **exactamente** firmware/BIOS, kernel, Mesa, GNOME, Chrome, EVDI, Iris y herramientas antes/después; aislar variables y registrar incertidumbre.

## Paquetes de integración

| Orden | Frente / dueño | Problema verificable | Instrumentación / criterio de aceptación | Límite |
| --- | --- | --- | --- | --- |
| G0 | Inventario y gobierno / #50 V0 | Cambios concurrentes sin procedencia | Snapshot redactor, mapa issues/ramas, logs sintéticos y controles de privacidad; revisión CI | No habilitar servicios |
| G1 | Energía, EC, ADC/PMIC / #3, #50 | Calor y reinicios intermitentes | Timeline boot IDs, SCMI, sensores/ADC; comparación 7.3.0-10 vs -11 con evidencia | No EC live / writes IIO / reboot |
| G2 | Video Adreno e Iris / #2, #15; issue dedicado | Chrome sin VA-API y streams entrecortados | V4L2 vs FFmpeg controlado; CDP `droppedVideoFrames`, Chrome media-internals, petición/red/segmentos, 1 vs 4 videos, 360p/720p/1080p | No asumir que V4L2 directo implica VA-API en Chrome |
| G3 | DisplayLink D6000 / #1 | EVDI/Secure Boot y ruta de presentación | Dock desconectado/conectado, 60 Hz, GNOME/Mutter frametimes, CPU DisplayLink, alimentación y Ethernet como variables separadas | No cambiar MOK/Secure Boot |
| G4 | SoundWire/PipeWire / #4 | Altavoces internos/canales | Topología ALSA, nodos PipeWire, prueba estéreo/cuatro canales y guardia de regresión | No modificar UCM/firmware en vivo |
| G5 | Hibernación y arranque / #21 | Retorno suspendido inseguro, TPM/PCR/BitLocker | Reutilizar H0–H5 / harness offline; rollback completo para propuesta futura | Ni un ciclo físico sin gate |
| G6 | NPU/CDSP, Wi-Fi, USB-C, batería / #13 y futuras observaciones | Integraciones incompletas | Inventario de drivers/capacidades, ACL y documentación de uso aislado, problemas reproducibles | No instalar servicios NPU ni cambiar ACL |
| G7 | Upstream y adopción / #50 V3–V6 | Parches sin cotejar o pruebas no reproducibles | Matriz propuesta/revisada/aceptada/mergeada/empaquetada; candidata ADOPTAR/ESPERAR/NO_GO | Sin comunicación externa automática |

## Evidencia sintética verificada en la sesión previa (2026-11-21)

- **OBSERVADO:** `/dev/video16` Qualcomm Iris expone H.264/HEVC/VP9/AV1 y decodificó flujo H.264 local de 1080p por V4L2; Chrome registró `vaInitialize failed` y usó `FFmpegVideoDecoder`. No son pruebas de uso de VA-API efectivo.
- **OBSERVADO:** Chrome headless reprodujo H.264 sintético a 1080p/30 fps, con cero cuadros descartados en 7 s (un video); cuatro videos descartaron seis cuadros iniciales entre todos y no acumularon nuevos descartes. **NO_VERIFICADO:** rendimiento de composición en pantallas físicas DisplayLink.
- **OBSERVADO:** registros de streams reales mostraron `DEMUXER_UNDERFLOW`, cambios `kSeeking`, a veces `DECODER_UNDERFLOW`; incluso 360p. No demuestra fallo del ISP, DNS, NIC, compositor ni origen.
- **OBSERVADO:** pruebas ICMP LAN/WAN sin pérdida y HTTP por Ethernet/Wi-Fi con variaciones puntuales en tiempo de descarga; no hay un culpable de red confirmado.
- **NO_VERIFICADO:** faltó capturar la reproducción real en Chrome con trazas de red correlacionadas; una sesión aislada recibió algunos HTTP 403 y no comenzó reproducción. Requiere entorno con stream activo y consentimiento para observar solo metadatos.

## Gates de adopción y rollback

- `GO-LAB`: fuentes exactas, fixtures sintéticos, licencia/procedencia verificables, reproducción y unidad/CI PASS, sin privilegios.
- `GO-DEVICE`: diagnóstico probado; riesgo cuantificado; copia recuperable; ventanas de interrupción; autoridad explícita por cada componente; procedimiento de rollback verificado **antes** de instalar.
- `NO_GO`: kernel/DT/firmware mezclados sin prueba ABI, MOK/BitLocker no resueltos, fallo de integridad, evidencia privada no redactada, cambios térmicos de efecto desconocido, regresión en audio/pantallas/SCMI.
- `ESPERAR_UPSTREAM`: parche con mantenimiento activo pero sin pruebas de estabilidad o integración distro verificadas.
- `ADOPTAR`: solo después de comparación real repetible (versiones, reboot, batería/dock, matriz funcional) y aceptación separada del riesgo residual.

## Implementación de esta entrega

- Reutilización de `scripts/diagnose-readonly.sh` y herramientas de hibernación/EC previas.
- Nuevos `scripts/xps_val01_collect.py` (instantánea con lista blanca, salida stdout, sin daemon/escritura) y `scripts/xps_val01_compare.py` (diferencias observacionales; **jamás concede adopción automática**).
- Suite hermética `tests/test_xps_val01.py`, prueba opcional de decodificación `scripts/xps_val01_video_smoke.sh` con datos sintéticos temporales; CI aislado.
- Documentación en `docs/xps-val01-execution-20261121.md`, `docs/xps-val01-upstream-matrix.md`, `docs/xps-val01-maintainer-draft.md`.
- Sin merge, publicación upstream o pruebas físicas destructivas en este paquete.

## Próximas decisiones de ingeniería

1. Verificar si los reinicios se repiten con 7.3.0-11 y EC experimental ausente, con evidencia cronometrada y sin activar EC.
2. Evaluar `qcom-va-driver` en laboratorio **solo si** una prueba de flujo real justifica la necesidad; confirmar ABI y estado de parches Iris HFI gen2 antes de proponer adopción.
3. Separar alteraciones por dock: DisplayLink USB render, PD, Ethernet, compositor, frecuencia efectiva por pantalla y aceleración Chromium.
4. Alinear vía #21 la cadena de hibernación y BitLocker; no mezclar una corrección de video con cambios de arranque.
