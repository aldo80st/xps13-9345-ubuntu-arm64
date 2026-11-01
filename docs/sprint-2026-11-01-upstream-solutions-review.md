# Gate de investigación upstream — sprint de estabilidad Dell XPS 13 9345 ARM64

**Fecha de análisis:** 2026-11-01. **Estado:** investigación de solo lectura; no autoriza iniciar el sprint ni aplicar parches.
**Equipo evaluado:** Dell XPS 13 9345, Snapdragon X Elite X1E80100, Ubuntu 26.10 ARM64, kernel `7.3.0-10-generic` (paquete `7.3.0-10.10`), Secure Boot habilitado, shim validando, Dell D6000 con **dos pantallas DisplayPort**, doble arranque con Windows BitLocker.

## Resultado ejecutivo

Evitar desarrollar correcciones que ya existen. Clasificar cada alternativa conforme a su **madurez**, **correspondencia exacta con este equipo**, **riesgo**, **evidencia local** y **reversión**. Una corrección upstream *propuesta*, *Fix Committed* o *reportada por otro usuario* no demuestra que esté integrada en el kernel que usamos.

| Frente | Qué existe | Dictamen antes del sprint | Condición de ejecución |
| --- | --- | --- | --- |
| **#1 EVDI + MOK / Secure Boot** | [DisplayLink: firma DKMS](https://support.displaylink.com/knowledgebase/articles/1181617-how-to-use-displaylink-ubuntu-driver-with-uefi-sec); [Ubuntu LP #2131181](https://bugs.launchpad.net/bugs/2131181) y [SRU de Canonical](https://lists.ubuntu.com/archives/kernel-team/2026-October/172721.html) | **ADAPTAR / INVESTIGAR primero**. El controlador DisplayLink 6.4 instalado coincide con el [último oficial (24-09-2026)](https://www.synaptics.com/products/displaylink-graphics/downloads/ubuntu). No reinstalarlo a ciegas. | Comprobar si la corrección MOK está realmente en `7.3.0-10.10`, inspeccionar keyrings `.machine`/`.platform`, cadena shim, logs EFI, firma real de `evdi.ko`, y solo entonces considerar actualización de kernel firmada. **Prohibido deshabilitar Secure Boot, desactivar validación shim o modificar EFI sin autorización**. |
| **#1 Alternativa HDMI D6000** | [Dell confirma HDMI mediante DP Alt Mode sin DisplayLink](https://www.dell.com/support/kbdoc/en-ca/000126592/dell-dual-video-d1000-usb-3-0-d3100-and-universal-d6000-docking-stations-do-not-support-daisy-chain-functionality) | **APROVECHAR para prueba parcial**; permite una salida HDMI nativa (máx. 4K/30 según Dell), **no arregla las dos salidas DisplayPort**. | Usar un monitor/cable compatible ya disponible; comparar video nativo contra DisplayLink. No comprar hardware para esta prueba sin decisión del usuario. |
| **#2 IRIS video acelerado** | Firmware [Dell oficial KPF2C](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=kpf2c) **ya extraído, SHA-256 verificado e instalado**. [Guía de Qualcomm](https://docs.qualcomm.com/doc/80-80021-20/topic/bring-up.html?product=895724676033554725&facet=Video&version=2.0-rc2) y [ejemplos GStreamer del fabricante](https://www.qualcomm.com/developer/blog/2025/10/same-day-snapdragon-8-elite-gen-5-upstream-linux-support). | **ADAPTAR pruebas existentes**, no volver a descargar firmware de otro modelo. | Reproducir con bitstream H.264 libre/sintético y pipeline acorde a caps V4L2; distinguir fallo `not-negotiated` de fallo VPU; comprobar activación real del hardware. **La guía Qualcomm citada corresponde a otro BSP/SoC: no copiar sus nombres de módulo o nodos literalmente**. |
| **#3 Control térmico y EC** | [PATCH v8 de Aleksandrs Vinarskis, 25/10/2026](https://lists.openwall.net/linux-hardening/2026/10/26/3) para XPS 9345; [Ubuntu LP #2172131](https://bugs.launchpad.net/bugs/2172131). | **ESPERAR INTEGRACIÓN upstream / kernel firmado**. Reutilizar métodos de medición, no insertar driver EC fuera de árbol al portátil diario. | Primero evidenciar ventiladores, carga sostenida, temperatura, throttling y suspensión; después verificar si upstream fue integrado y firmado para la versión instalada. |
| **#4 Altavoces/SoundWire** | [Repositorio específico Dell tributо](https://github.com/alexVinarskis/linux-x1e80100-dell-tributo), [AudioReach Topology](https://github.com/linux-msm/audioreach-topology), [ALSA UCM Dell](https://github.com/alexVinarskis/alsa-ucm-conf/tree/dell-xps-9345), [Ubuntu LP #2172596](https://bugs.launchpad.net/bugs/2172596). | **APROVECHAR configuración/topología después de diff**; **DESCARTAR bypasses peligrosos del amplificador**. En [Ubuntu Discourse](https://discourse.ubuntu.com/t/dell-xps-13-9345-x1e80100-audio-stack-investigation-on-ubuntu-25-10/73248) advierten sobre ausencia de protección de altavoces y riesgo de daño. | Comparar topología Dell y UCM ya instalados con ramas upstream, determinar presencia de protección de amplificador antes de ensayos acústicos; probar altavoces L/R y micros de forma conservadora. No habilitar `i_accept_the_danger=1` ni forzar volumen. |
| **#5 BIOS 2.14→2.15** | [Dell BIOS 2.15.0](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=PK3V5) con aviso BitLocker. | **PREPARAR**, no instalar durante el sprint autónomo. | Confirmar necesidad/versión, integridad, alimentación, medio Dell soportado y clave de recuperación BitLocker; requerir autorización explícita. |
| **#6 Desktop Commander systemd** | [Nuestra guía verificada](desktop-commander-systemd.md), versión local 0.3.1, servicio habilitado y conectado, sin agentes duplicados. | **CONSERVAR Y PROBAR**, no reemplazar con otro framework. | Validar funcionamiento posterior a reinicio/inicio de sesión, logs sin secretos y recuperación sin agentes duplicados. `Linger=no` es deliberado; no habilitar exposición anterior al login sin evaluación. |
| **#7 pd-mapper** | [Nuestra solución verificada](pd-mapper-overlay-regression.md): corregimos sombra de `updates/` y recuperamos mapas `.jsn`. | **CERRADO / NO TOCAR** salvo regresión. | Validar `pd-mapper` activo y firmware en el directorio base. No recrear el overlay. |
| **#8 Adreno initramfs** | [Ubuntu LP #2169496](https://bugs.launchpad.net/bugs/2169496) declara el fallo temprano y su carga posterior, **Won't Fix** (reintento intencional desde Linux 6.16). | **DESCARTAR** el `dracut -f` sugerido por otros reportes solo para ocultar advertencias. | Nuestra GPU termina cargando `gen70500_sqe.fw` y GMU; intervenir únicamente si surge fallo gráfico reproducible adicional. |
| Wi-Fi suspensión (otro modelo) | [LP #2169326](https://bugs.launchpad.net/bugs/2169326) reportado para **Lenovo Yoga Slim 7x**, no para nuestro Dell. | **DESCARTAR COMO CAMBIO AUTOMÁTICO**; conservar como referencia si aparece problema real. | Probar suspensión/Wi-Fi; no aplicar resets de adaptador por anticipación. |

## Hallazgos locales verificados durante el gate

- `linux-image-7.3.0-10-generic 7.3.0-10.10`, `displaylink-driver 6.4.0-0ubuntu1~ppa1~stonking1`, `evdi-dkms 1.15.0+dfsg-2`, `alsa-ucm-conf 1.2.16.1-1ubuntu1`, `linux-firmware 20260915.git1522c78a.1ubuntu`.
- Secure Boot activado; `mokutil --test-key` confirma MOK inscrito, pero informa que no puede acceder al keyring confiable del kernel. `evdi.ko` tiene firma PKCS#7 SHA-512 y es rechazado por lockdown. **Coincidencia con LP #2131181 plausible, no probada**.
- El Dell D6000 está conectado: USB `17e9:6006`. El error de EVDI ocurre repetidamente (más de 100 entradas de lockdown en una ventana de cinco minutos durante la inspección). **No se hicieron cambios en servicios**.
- El firmware de IRIS ya fue verificado y está en `/lib/firmware/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn` (SHA-256 `8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629`). Las topologías Dell `*.tplg.bin.zst` también están instaladas; no copiarlas de nuevo por defecto.
- El kernel `7.3.0-10.10` es la versión candidata actual en los repositorios de `stonking-updates` del equipo según `apt-cache policy`. Aunque LP #2131181 figura **Fix Committed para Stonking**, **no se encontró prueba de que esta revisión concreta ya contenga la reparación**.

## Política de selección para Codex

Para cada issue, producir un ADR breve con:

1. **Alternativas reales**: paquete oficial, parche upstream integrado, repo comunitario, workaround y opción de no intervenir.
2. **Aplicabilidad**: modelo exacto, SoC, kernel, versión y prerequisitos; diferenciar una propuesta de una solución empaquetada.
3. **Estado**: EXISTE / PARCIAL / WIP / FIX COMMITTED / FIX RELEASED / NO REPRODUCIDO / RECHAZADO.
4. **Decisión**: DIRECTO, ADAPTAR, ESPERAR o DESCARTAR (motivos técnicos, no preferencias).
5. **Prueba y reversión**: evidencia antes/después, rollback y riesgo residual.
6. **Autorización**: si afecta MOK, EFI, shim, kernel firmado, BIOS, arranque o parlantes sin protección, **bloquear la ejecución automática**.

No confundir `Fix Committed` con `Fix Released`, ni el estado de otro equipo con el del XPS 9345. No introducir nuevas tecnologías, kernels experimentales o servicios sin motivo verificable.

## Orden del sprint recomendado

1. **Sólo lectura:** MOK/kernel/trust keyrings y paquetes Ubuntu; decidir la solución de EVDI con Secure Boot.
2. **En paralelo, baja intrusión:** bitstream H.264 libre y pipeline de prueba V4L2/IRIS; comparar audio UCM/topología y protección de altavoces; continuidad de Desktop Commander.
3. **Sólo ante necesidad demostrada:** pruebas de carga térmica conservadoras y revisión de EC; evaluación BIOS y BitLocker.
4. **No ejecutar:** cambio de initramfs para Adreno, bypass Secure Boot/shim, `i_accept_the_danger` de audio, reset Wi-Fi preventivo, reinstalación aleatoria DisplayLink, kernel EC no firmado.
5. Cierre: evidencia funcional de los **dos DisplayPort**, prueba de VPU real, audio seguro, estado de servicios sin esconder causas; publicar sólo resultados verificados.

## Enlaces clave (fuentes primarias)

- Canonical SRU LP 2131181: https://lists.ubuntu.com/archives/kernel-team/2026-October/172721.html
- Launchpad LP 2131181: https://bugs.launchpad.net/bugs/2131181
- DisplayLink Secure Boot: https://support.displaylink.com/knowledgebase/articles/1181617-how-to-use-displaylink-ubuntu-driver-with-uefi-sec
- Synaptics driver 6.4: https://www.synaptics.com/products/displaylink-graphics/downloads/ubuntu
- Dell D6000 HDMI Alt Mode: https://www.dell.com/support/kbdoc/en-ca/000126592/dell-dual-video-d1000-usb-3-0-d3100-and-universal-d6000-docking-stations-do-not-support-daisy-chain-functionality
- Qualcomm Video: https://docs.qualcomm.com/doc/80-80021-20/topic/bring-up.html?product=895724676033554725&facet=Video&version=2.0-rc2
- XPS 9345 upstream: https://github.com/alexVinarskis/linux-x1e80100-dell-tributo
- Dell EC PATCH v8: https://lists.openwall.net/linux-hardening/2026/10/26/3
- Ubuntu SoundWire issue: https://bugs.launchpad.net/bugs/2172596
- Speaker protection warning: https://discourse.ubuntu.com/t/dell-xps-13-9345-x1e80100-audio-stack-investigation-on-ubuntu-25-10/73248
- Adreno Won't Fix: https://bugs.launchpad.net/bugs/2169496

La investigación tomó evidencia de **Firecrawl** (búsquedas de actualidad, fuentes oficiales, proyectos OSS y lectura de páginas), corroboración web y diagnósticos **sólo de lectura** en el equipo. No se aplicó ninguna corrección ni se alteró el arranque durante este gate.
