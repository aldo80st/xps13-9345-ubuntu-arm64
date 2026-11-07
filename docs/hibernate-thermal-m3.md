# M3 — Matriz de compatibilidad: hibernación × Dell EC v8 × SCMI

**Fecha:** 2026-11-07 · **Resultado en fuentes oficiales sin adaptar:** **NO_GO**. **Resultado en copia de fuentes con EC v8:** **REVIEW_REQUIRED**, aún **NO apto para arrancar**. Véase [integración reproducible](thermal-hibernation-integration.md). **Alcance:** preparación aislada sin modificar el sistema.
**Contrato:** [M3 Thermal × Hibernate](superpowers/specs/2026-11-07-m3-thermal-hibernate-contract.md) · **Plan:** [Superpowers M3](superpowers/plans/2026-11-07-m3-thermal-hibernate-gate.md).

## Por qué los frentes no son intercambiables

El M2 reprodujo de forma equivalente el **Kconfig** de Ubuntu 7.3, activando hibernación y sus dependencias LZ4. Eso preserva las opciones de `scmi_cpufreq`, pero **no reproduce las incorporaciones experimentales del kernel/Device Tree Dell EC v8**. El equipo actualmente ejecuta una entrada experimental de GRUB con DTB alternativo y un módulo externo `dell_xps_ec`. Un futuro kernel nuevo necesita estos componentes **reconstruidos para su versión y revisados**, no simplemente copiados.

Además, la rama `fix/resources-51-qualcomm-cpu-metrics` mejora la **observabilidad** de temperaturas/clústeres Oryon en GNOME Resources. Es un trabajo distinto de la administración real de frecuencias, que realiza `scmi_cpufreq`; no se debe presentar como un cambio de control de clocks.

## Matriz de requisitos, evidencia y gate

| Frente | Evidencia observada directamente | Situación en fuente Ubuntu 7.3 + config M2 | Requisito de aceptación en M3 |
| --- | --- | --- | --- |
| Hibernación del kernel | `CONFIG_HIBERNATION=y` en `.local/m2-out/.config`; auditor M2 `CLEAN` | **Preparado solo en laboratorio**; kernel ejecutado aún no tiene `disk` | Mantener CONFIG_HIBERNATION=y y cadena de reanudación integral, después validarla con kernel alternativo |
| Dell EC: controlador de ventilador/térmica | `dell_xps_ec` cargado, dispositivo I²C 5-003b enlazado | **No integrado**: falta `drivers/platform/arm64/dell-xps-ec.c` | Integrar fuente EC v8 para nuevo kernel, compilar módulo, revisar ABI/firmware y operación real |
| Dell EC: configuración del kernel | Staging `v8-2.diff` define `CONFIG_EC_DELL_XPS` | **No integrado**: Kconfig/Makefile ausentes; `CONFIG_EC_DELL_XPS` no habilitado | Añadir wiring Kconfig/Makefile y establecer símbolo `m` o `y` en nueva configuración |
| Dell EC: binding y Device Tree | DTB experimental en uso, compatible `dell,xps13-9345-ec` visible; I²C 5-003b | **No integrado**: faltan binding y nodo `embedded-controller@3b` | Integrar `v8-1.diff` + `v8-3.diff`, revisar IRQ, ADC/térmicos, propiedad I²C y DTB Dell correcto |
| Dell EC: freeze / restore | `SYSTEM_SLEEP_PM_OPS` define suspend/resume, freeze/thaw y poweroff/restore | El mecanismo existe en el módulo externo, **no ensayado en hibernación** | Verificar que EC/I²C/IRQ, ventilador, temperaturas y periféricos vuelven tras restaurar RAM; cobertura de error de PM |
| CPU: gestión de frecuencias | `scmi_cpufreq`, políticas 0/4/8 con gobernador `ondemand` | **Conservado**: cinco opciones kernel iguales en Ubuntu y M2 | Exigir igualdad de símbolos y prueba posterior de clústeres, límites min/max, variación de frecuencia y governor |
| Perfil energético | `powerprofilesctl get` reportó `power-saver` | Capa de usuario distinta del Kconfig | Verificar perfiles y transiciones de energía al restaurar |
| Métricas GNOME Resources | Rama `fix/resources-51-qualcomm-cpu-metrics` separada; parche de visualización CPU ARM | No es necesario fusionarla al kernel para operar SCMI | Comparar observabilidad antes/después; preservar implementación de UI de manera independiente |
| Qualcomm hibernación | Revisión P1–P5 documentada en `hibernate-patch-review-20261107.md` | PCIe shutdown v7 / freeze v2 y remoteproc sin integración probada | Validar pila ordenada y firmas/commits, sin cherry-picks indiscriminados |
| Recuperación segura | Grub stock presente, entrada EC experimental separada; arranque experimental activo | Instalación de nuevo kernel no autorizada por M2 | Respaldos restaurables, BitLocker recuperable por usuario, ruta GRUB / USB de rescate y rollback probado |

**Precisión:** disponer de callbacks de suspensión del EC no equivale a comprobar reanudación después de hibernación (apagado total). `SYSTEM_SLEEP_PM_OPS` mapea varios eventos de energía a las mismas funciones; hay que probar los efectos específicos de firmware y carga de módulos en un kernel diferente.

## Proveniencia exacta del EC v8 en staging

Archivos fuente de referencia: `XPS-THERMAL/ec-v8-staging/patches` (no se copian al repositorio).

| Serie | SHA256 observado | Contenido / rol |
| --- | --- | --- |
| `v8-1.diff` | `c73f41f2e3c91afd388aa442b616f82c0be0f39b9a3185391da387cd099ea6e0` | Binding Device Tree |
| `v8-2.diff` | `5eaba144c037a94d700e73b248883246494683b4aa8a36d71c17a3625a5c5938` | Controlador EC, Kconfig, Makefile |
| `v8-3.diff` | `8a25b419d57694ceceaa024f3152c4363268d2faf9fffe0ec1531a4f64f05620` | DTS Qualcomm XPS 9345 |

Hashes de artefactos binarios *solo como evidencia local*, no autorizan copiarlos al kernel futuro: módulo `dell-xps-ec.ko` `65ff6e2c9075c202fef8726bf4df1a3345f337abfb441e4787aae9f19ff7b308`, DTB `xps13-9345-ec-v8-test.dtb` `42aa439d646ee83bf20bbcf062dd8c9b441962167eed2d9b0d9bcd3b97c60e06`. Un módulo construido para `7.3.0-10-generic` no debe copiarse a un kernel de otra versión.

## Ejecución del gate read-only

Desde el worktree del laboratorio del XPS, con Ubuntu 7.3 instalado y los artefactos de M2 disponibles:

```bash
python3 scripts/hibernate-thermal-m3-gate.py \
  --source-tree "$PWD/.local/kernel-source/tree/linux-source-7.3.0" \
  --baseline /boot/config-7.3.0-10-generic \
  --candidate "$PWD/.local/m2-out/.config" \
  --ec-patches "$HOME/projects/XPS-THERMAL/ec-v8-staging/patches" \
  --json
```

La salida contiene solo nombres de pruebas y bloqueos, sin rutas o valores privados. `NO_GO` devuelve **exit 1**; `REVIEW_REQUIRED` devuelve **exit 0** pero **nunca** autoriza instalar o arrancar un kernel. El gate es sintáctico/estructural: no comprueba automáticamente que la placa se enfríe correctamente ni que los drivers se recuperen tras hibernar.

**Resultado comprobado sobre fuente Ubuntu actual:**

- `status=NO_GO`, `approval=not_authorized`.
- Pasan `hibernation_config_enabled`, `scmi_cpufreq_preserved` y `ec_patch_provenance_valid`.
- Bloquean: `ec_config_disabled`, `ec_driver_missing`, `ec_power_management_unreviewed`, `ec_binding_missing`, `ec_kconfig_missing`, `ec_build_wiring_missing`, `ec_dts_node_missing`.
- 14 pruebas nuevas pasaron, incluyendo validación de SHA, regresión de SCMI, ausencia de DT, callbacks y resultados sin secretos.

## Orden de integración del futuro árbol experimental (trabajo aún no realizado)

1. **Preparar staging separado** del árbol Ubuntu 7.3 y conservar M2 como referencia inmutable.
2. Revisar/aplicar semánticamente EC v8 sobre nueva fuente, en orden binding → driver/Kconfig/Makefile → DTS, y comprobar que la versión/ABI y callbacks son válidos. No usar directamente `.ko` ni DTB previamente compilados.
3. Resolver por separado P1–P5 Qualcomm, en especial PCIe shutdown v7 versus freeze v2 y SMP2P/remoteproc, comprobando commits y compatibilidad en la misma base.
4. Generar nuevo Kconfig con `CONFIG_EC_DELL_XPS=m/y`, `CONFIG_HIBERNATION=y`, y todos los símbolos SCMI/cpufreq conservados; correr este gate y auditoría de diferencias bajo allowlist revisado para EC, no silenciar advertencias.
5. Solo tras pasar criterios estáticos y revisión de la pila, construir un **paquete alternativo no instalado**, verificar módulos/DTB/recovery y regresar a los gates BitLocker, backup y boot autorizados.
6. **Prueba experimental supervisada**: suspend/deep, freeze/thaw, poweroff/restore, temperaturas y ventilador, escalamiento de clocks y perfiles, redes y almacenamiento; nunca confundir `disk` anunciado con hibernación validada.

**Estado de avance:** matriz incorporada y gate ejecutado; integración real EC+Qualcomm en un kernel futuro **pendiente**, no declarada completada.
