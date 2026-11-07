# M3 — Contrato de compatibilidad: hibernación, Dell EC v8 y SCMI cpufreq

**Fecha:** 2026-11-07. **Estado:** alcance aprobado por directiva “hazlo”; solo lectura, sin autorización de instalación.
**Objetivo:** prevenir que un candidato de kernel con hibernación haga retroceder el control térmico experimental, la recuperación de dispositivos o la regulación dinámica de frecuencia en el Dell XPS 13 9345 (X1E80100).

## Estado contrastado directamente

- Arranque observado: `7.3.0-10-generic`, con `xps_ec_trial=20261107-stubble` y `stubble.dtb_override=false`. Es una entrada experimental **realmente activa**, no un ejemplo teórico.
- Módulo `dell_xps_ec` cargado; dispositivo `I2C 5-003b` enlazado; Device Tree de ejecución con compatible `dell,xps13-9345-ec`. El módulo es externo al kernel oficial.
- Código EC v8 en staging con callbacks de sueño vía `SYSTEM_SLEEP_PM_OPS`; Linux asigna estos a suspend/resume, freeze/thaw y poweroff/restore. **Presencia del callback no prueba restauración tras hibernación**, particularmente con EC/firmware que cortan la energía de periféricos.
- Frecuencia CPU en 3 políticas mediante `scmi_cpufreq`, gobernador `ondemand`; el perfil actual del demonio de energía se observó como `power-saver`. Son dimensiones distintas: gobierno de frecuencia del kernel, perfil del sistema y métricas/visualización de CPU en GNOME Resources.
- La fuente Ubuntu `linux-source-7.3.0=7.3.0-10.10` usada para M2 **carece** de `drivers/platform/arm64/dell-xps-ec.c`, `Documentation/devicetree/bindings/embedded-controller/dell,xps13-9345-ec.yaml` y nodo Dell EC en el DTS. Integrar únicamente hibernación quitaría esa capacidad experimental.
- M2 `CONFIG_HIBERNATION=y`, auditor `CLEAN` (8 símbolos directos y 2 dependencias LZ4), y **mismas** configuraciones `CONFIG_ARM_SCMI_CPUFREQ=m`, `CONFIG_CPU_FREQ=y`, `CONFIG_CPU_FREQ_GOV_ONDEMAND=y`, `CONFIG_CPU_FREQ_GOV_SCHEDUTIL=y`, `CONFIG_ARM_SCMI_PROTOCOL=y`.
- Staging EC v8 local contiene tres parches versionados y un módulo/DTB de prueba. Sus bytes se identifican por SHA256; no se reproducen ni almacenan binarios en Git.

## Opciones descartadas

1. Combinar un kernel de hibernación con el árbol Ubuntu sin EC: **rechazada** (regresión térmica).
2. Copiar sin revisión los binarios EC actuales a un nuevo kernel: **rechazada** (vermagic/ABI/DTB/firmware y cambios de interfaz).
3. **Seleccionada:** matriz compartida y gate read-only, más integración del *código fuente* EC v8 + DTS + Kconfig/Makefile y preservación de SCMI en el futuro árbol experimental. PRs/worktrees siguen separados; ninguna fusión implícita.

## Contrato mínimo comprobable por automatización

- `CONFIG_HIBERNATION=y` en configuración de laboratorio.
- `CONFIG_EC_DELL_XPS=m` o `y` en futura configuración, **no** basta el archivo del driver.
- Ausencia de cambios en las cinco opciones SCMI/cpufreq requeridas respecto de Ubuntu oficial.
- Fuentes Dell EC, binding, Kconfig, Makefile y nodo Device Tree están presentes de forma coherente y conservan las operaciones PM del EC.
- Los parches EC v8 de referencia coinciden con hashes fijos, evitando integrar una revisión inadvertidamente.
- Si falta información, resultado `NO_GO`. Si todo pasa, el resultado máximo es `REVIEW_REQUIRED`: todavía faltan ABI/DTB, integración de P1–P5, arranque y pruebas reales.

## Gate posterior, no automatizable todavía

Antes de admitir un kernel para instalar: revisión de parches Qualcomm P2 v2 / shutdown v7, SMP2P/remoteproc, pinctrl, UART y Bluetooth; ensayos del driver EC de freeze/thaw, poweroff/restore (no basta que compile); CPUFREQ/SCMI y `ondemand` restaurados, límites/min/max, temperatura, controles de ventilador, power-profiles, NVMe, USB-C y periféricos. Definir rollback GRUB y evidencia BitLocker/backup. Nunca cambiar BIOS, EFI, kernel activo, swap, fuentes de otros worktrees ni arrancar por esta tarea.

## Procedencia

Staging EC: `XPS-THERMAL/ec-v8-staging/patches/v8-{1,2,3}.diff`, usado como evidencia de referencia pero no alterado.
Rama de métricas CPU Qualcomm: `fix/resources-51-qualcomm-cpu-metrics` (interfaz/medición, no reemplazo de `scmi_cpufreq`).
Rama hibernación: `feat/hibernate-readiness-20261106`.
Fuentes propias existentes: [thermal-ec.md](../../thermal-ec.md), [hibernate-patch-review-20261107.md](../../hibernate-patch-review-20261107.md), [hibernate-m2-toolchain.md](../../hibernate-m2-toolchain.md).
