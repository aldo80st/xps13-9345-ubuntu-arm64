# XPS-VAL-01 — Matriz de procedencia upstream (verificación inicial)

**Corte:** 2026-11-21. **Estados:** `PROPUESTO` = publicación de serie, `REVISADO` = hay etiquetas de revisión reportadas, `ACEPTADO/MERGEADO` = prueba de incorporación en árbol exacto, `EMPAQUETADO` = paquete de distribución comprobado. **La mera presencia en un hilo no confirma merge ni empaquetado Ubuntu.**

| Candidato | Fuente / autor / fecha verificables | Estado verificado | Relevancia y dependencia | Gate |
| --- | --- | --- | --- | --- |
| Dell XPS EC v8 (3 patches) | [Cover 2026-10-26, Aleksandrs Vinarskis](https://lists.openwall.net/linux-kernel/2026/10/26/28), [diff driver](https://lists.openwall.net/linux-hardening/2026/10/26/4) | **PROPUESTO v8**, no hay evidencia de merge/packaging Ubuntu 7.3.0-11 en esta auditoría; [archivos de staging existentes](./thermal-hibernation-integration.md) | EC Power/Thermal, termistores y fans. Depende de Qualcomm SPMI ADC Gen3 en árbol objetivo. módulo EC experimental **ausente** en kernel 7.3.0-11 del host | **NO_GO** host, revisar ABI/fuente y comparación sin EC |
| DTS thermal zones v2 | [Liviu Nicoara, 2026-10-22](https://lkml.rescloud.iu.edu/2610.2/17102.html) | **PROPUESTO v2**, trae etiquetas Reviewed-by/Tested-by en mensaje; **NO** significa merge | Zonas SYS_THERM1–7, nombres basados en configuración PMIC. Intersección con nodos EC: revisar solapamiento | **PREPARAR** diff contra versión exacta, no mezclar automáticamente |
| PMK8550 ADC5 Gen3 / TM5 | [Dependencia referenciada por Dell EC v8](https://lists.openwall.net/linux-kernel/2026/10/26/28) | El autor afirma dependencias en linux-next para 7.1, no se verificó aquí el SHA de integración Ubuntu | Controladores para sensores PMIC. El host tiene módulo `qcom-spmi-adc-tm5-gen3` en disco, **no equivale a tener pila EC válida** | **REVISAR** verificación de configuración/ABI |
| Iris HFI gen2 VA-API fixes v1 (5 parches) | [Xilin Wu, 2026-10-29](https://lists.openwall.net/linux-kernel/2026/10/29/306) | **PROPUESTO v1**, estado merge/Ubuntu no comprobado. `base-commit` del cover no es SHA de merge | Decode-order, buffers, timestamps, AV1/VP9; podría afectar puente VA-API y V4L2 directo | **GO-LAB** solo fuente/fixtures |
| `qcom-va-driver` | [radxa-pkg/qcom-va-driver](https://github.com/radxa-pkg/qcom-va-driver), [fuente Debian 1.1.0-1](https://sources.debian.org/src/qcom-va-driver/1.1.0-1/README.md) | Backend experimental disponible públicamente; **Ubuntu 26.10 local no tiene `qcom_drv_video.so`**; Chrome real reporta VA-API error | Traduce API VA a V4L2 Iris. Pruebas públicas no garantizan integración Chrome+GNOME+DisplayLink ni la misma versión de firmware Iris | **GO-LAB / NO_GO HOST** |
| BIOS Dell 2.15.0 | [Dell release referida en thermal-ec](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=PK3V5) | Publicación referenciada; **host 2.14.0** | Seguridad / firmware. BitLocker TPM y Secure Boot requieren procedimiento explícito | **ESPERAR #5** |
| EVDI DisplayLink | [Documentación local de cadena Secure Boot](./secure-boot-evdi.md) | **Instalado/cargado actualmente** con kernel 7.3.0-11; sin garantía en arranque Secure Boot habilitado | Dos monitores externos 1080p60; módulo evdi y DisplayLink manager | **NO_GO** cambiar Secure Boot |
| Hibernación y árbol Ubuntu `qcom-x1e` | [Epic #21](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/21), [integración de fuentes EC](./thermal-hibernation-integration.md), [auditoría de fuentes](./hibernate-canonical-source-i1.md) | Compilación y fuentes en laboratorio previas; **hibernación operativa no demostrada** | Afecta PCIe, remoteproc/SMP2P, DT/EC/SCMI, pstore y TPM | **NO_GO** boot y hibernación físicos |

## Comprobaciones que faltan antes de cambiar estados

1. Para cada parche, consultar rama/commit de árbol maintainer y `git log` de la fuente exacta; guardar URL del commit (no solo `base-commit`), revisión, versión y digest.
2. Verificar fuente y configuración real `/boot/config-7.3.0-11-generic` y `/lib/modules/7.3.0-11-generic`. La presencia de un módulo no prueba que haya sido cargado ni utilizado.
3. Para `qcom-va-driver`, comprobar tags, dependencias, licencias y tests en contenedor ARM64; no instalar ningún driver VA-API del sistema por defecto. Si `vainfo` da perfiles positivos, verificar **Chrome media-internals** por cada codec y carga de compositor.
4. Antes de cualquier prueba con EC, respetar gates de [#3](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/3), [#21](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/21) y [#49](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/49).
5. Aprobación humana independiente para BIOS/EFI/GRUB/MOK/kernel/DTB/BitLocker/reboot/suspend y envío upstream.

## Notas de atribución

Autores y fechas proceden de mensajes citados; no implica endoso de estos resultados de la XPS. La afirmación de que el ADC Gen3 está en linux-next para v7.1 es una **declaración en cover letter**, no verificación de empaque en Ubuntu 7.3.0-11. No hay colaboración upstream ni `Tested-by` enviado en esta entrega.
