# H2 — Procedencia y prueba de ABI del módulo Dell EC

Fecha de verificación: 2026-11-07. **Alcance: kernel activo 7.3.0-10-generic**, no el futuro kernel de hibernación.

## Evidencia comprobada directamente en el XPS

| Elemento | Resultado |
| --- | --- |
| Fuente EC v8 en staging térmico y copia experimental `m3-ec-source` | **Idénticas, SHA256** `7c915a168c812fe9463ac1d766914bc1b7d6498fdfa91dd3c1960dce8d258cf2` |
| Módulo `dell-xps-ec.ko` original y copia instalada bajo `/lib/modules/7.3.0-10-generic/updates/` | **Idénticos, SHA256** `65ff6e2c9075c202fef8726bf4df1a3345f337abfb441e4787aae9f19ff7b308` |
| ABI declarada por `modinfo -F vermagic` del módulo instalado | `7.3.0-10-generic SMP preempt mod_unload modversions aarch64` |
| Dependencia de módulo | `industrialio` |
| Estado observado | `dell_xps_ec` cargado en kernel actual, sin operaciones de carga/descarga durante este análisis |
| Linux headers / `Module.symvers` del kernel actual | Disponibles; 34 060 símbolos registrados |
| Fuente y Kconfig experimentales de hibernación | `CONFIG_HIBERNATION=y`, `CONFIG_EC_DELL_XPS=m`, `CONFIG_ARM_SCMI_CPUFREQ=m` |

## Compilación externa de control (sin instalación)

Se creó una copia de la fuente EC v8 en un scratch Git-ignored `.local/abi-proof/`, con Makefile mínimo `obj-m += dell-xps-ec.o`, y se ejecutó sin privilegios:

```bash
make -C /lib/modules/$(uname -r)/build M="$PWD/.local/abi-proof" -j2 modules
file .local/abi-proof/dell-xps-ec.ko
/usr/sbin/modinfo -F vermagic .local/abi-proof/dell-xps-ec.ko
```

Resultado: **exit 0**, módulo ELF aarch64 relocatable, `vermagic` igual al kernel operativo, SHA256 del archivo generado `b834f796094bd670b32907bd449048aed7ba92a2fca8da2a1c887c9b439b092f`.

**Limitaciones observadas:** Kbuild advirtió que el compilador se denomina `gcc` en lugar de `aarch64-linux-gnu-gcc`, aunque ambos reportan Ubuntu 15.3.0-4ubuntu1. `pahole` no estaba disponible en el anfitrión y se omitió la generación de BTF porque falta `vmlinux` de depuración. Este módulo generado no es idéntico byte a byte al instalado y **no se cargó** ni se instaló. La prueba válida es compatibilidad de compilación externa en el kernel **actual**, no equivalencia binaria completa ni ABI de un kernel futuro.

No se modificó `/boot`, `/lib/modules`, GRUB, EFI, BIOS, swap, política SCMI, firmware ni el EC en ejecución.

## Regla de aceptación del epic

- **Aprobado parcialmente**: identidad de fuente EC v8, origen del módulo actual, recompilación del módulo externo contra encabezados del kernel activo y compilación aislada EC `.o`/DTB en Docker reproducible.
- **Aún no demostrado**: un `.ko` con `vermagic` del **futuro kernel alternativo de hibernación**, generación de `Module.symvers` de ese nuevo kernel, BTF y depmod apropiados, y recuperación de sensores/ventiladores tras apagar y restaurar memoria.
- **H2 y H3 no pueden declararse terminados** basándose en el módulo del kernel actual; no se debe copiar ese binario a otra versión del kernel.
- El requisito de restauración segura de SCMI y EC se conserva en [epic XPS-HIB-01](superpowers/specs/2026-11-07-xps-hibernation-epic.md), [H2 Docker](hibernate-ec-build-h2.md) y [matriz térmica](hibernate-thermal-m3.md).
