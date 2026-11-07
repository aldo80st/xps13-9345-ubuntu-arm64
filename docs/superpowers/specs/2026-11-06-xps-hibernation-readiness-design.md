# XPS 13 9345 — diseño seguro de hibernación ARM64

Fecha: 2026-11-06. Alcance: Dell XPS 13 9345, Ubuntu 26.10 aarch64, Snapdragon X Elite, arranque dual Windows BitLocker. Estado: diseño; no autoriza cambios de arranque.

## Propósito

Preparar evidencia, procedimientos y decisiones para habilitar **hibernación real y restauración íntegra de sesión**, conservando el kernel funcional y sin experimentar a ciegas con firmware.

## Hechos medidos, sujetos a revalidación

- Kernels 7.3.0-10-generic y 7.3.0-9-generic: CONFIG_HIBERNATION no configurado, aunque CONFIG_ARCH_HIBERNATION_POSSIBLE=y.
- /sys/power/state: freeze mem. Ausente disk; no se puede hibernar con kernel actual.
- RAM ~30 GiB; swapfile /swap.img ~8 GiB; ~175 GiB disponibles; raíz ext4.
- GRUB y dracut 112 con módulo resume; BIOS Dell 2.14.0; 2.15.0 publicada con avisos de seguridad, pero no prueba de corrección de EFI/hibernación.
- ubuntu-x1e-settings v34 añade efi=noruntime en /etc/default/grub.d/ubuntu-x1e-settings.cfg; parámetro separado de CONFIG_HIBERNATION.
- EFI boot variables leídas con efibootmgr no equivalen a demostrar servicios EFI Runtime completos.

## Alternativas evaluadas

A. **Diagnóstico de sólo lectura y kernel alternativo aislado después de gates — seleccionada**: pruebas verificables y rollback, costo de más pasos.
B. Reemplazo directo del kernel instalado: riesgo inaceptable en un equipo de trabajo y arranque dual.
C. Esperar soporte oficial sin diagnóstico: bajo riesgo, pero no genera evidencia útil ni permite escalar bloqueos.

## Objetivos de esta iteración

1. Herramienta read-only que no precise sudo y distinga BLOCKED / UNKNOWN / READY_FOR_EVALUATION.
2. Separar: hibernación del kernel, capacidad runtime, intercambio swap, ruta dracut y firmware.
3. Reproducir en fixtures respuestas negativas, ambiguas y favorables sin inventar soporte.
4. Documentar decisiones Dell (firmware), Ubuntu (config del kernel), Linux/Qualcomm (drivers), y retorno a kernel estable.
5. No filtrar cmdline completo, seriales, UUID, GUID, MAC, IP, tokens ni información de recuperación personal.

## Condiciones no negociables

- No cambiar kernel, EFI/NVRAM, BIOS, GRUB, initramfs, swap, Secure Boot, BitLocker ni suspender/reiniciar equipo durante esta iteración.
- No asumir que parches propuestos están en el kernel instalado.
- Un resultado READY_FOR_EVALUATION significa elegible para siguiente inspección, nunca hibernación probada.
- Para hibernar: kernel CONFIG_HIBERNATION=y y disk, ruta resume disponible, swap apto y dispositivos capaces de restaurar estado.
- La imagen hibernada no debe compartir sistema de archivos modificado desde otro SO antes de reanudar.
- Hito posterior de instalación: respaldo verificable, clave de recuperación BitLocker verificada **por usuario**, acceso a GRUB/rescate, comparación de drivers, pruebas A/B y autorización específica.

## Fuentes

- Linux swsusp: https://www.kernel.org/doc/html/next/power/swsusp.html
- Dell BIOS 2.15.0: https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=PK3V5
- Dell BitLocker: https://www.dell.com/support/manuals/en-us/xps-13-9345-laptop/xps-13-9345-owners-manual/bitlocker?guid=guid-02ef31d0-ad81-4e06-935d-78dba82dc625&lang=en-us
- Ubuntu x1e settings: https://discourse.ubuntu.com/t/foundations-team-updates-2025-07-24/64104/2
- LP MOK/EFI (no es ticket de hibernación): https://bugs.launchpad.net/bugs/2172878
