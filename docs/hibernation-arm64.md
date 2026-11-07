# Hibernación en Dell XPS 13 9345 — diagnóstico, gates y escalamiento

**Estado (2026-11-06):** investigación de sólo lectura completada; hibernación **NO habilitada**.
**No reemplazar ni actualizar BIOS, GRUB, kernel, initramfs o swap siguiendo esta guía sin autorización específica.**
Consulta el diseño y plan en docs/superpowers/ para trazabilidad.

## Diagnóstico reproducible, sin privilegios

~~~bash
python3 scripts/hibernate-preflight.py --json
~~~

Este comando lee el sistema y devuelve sólo campos normalizados sin datos privados. No registra logs, no necesita sudo y no cambia configuración. Los valores de referencia de este equipo (revalidar después de cada cambio) son:

| Campo | Medición | Significado |
| --- | --- | --- |
| Kernel | 7.3.0-10-generic | Ubuntu 26.10 aarch64 |
| CONFIG_HIBERNATION | false | **Bloqueo definitivo de este kernel** |
| CONFIG_ARCH_HIBERNATION_POSSIBLE | true | La arquitectura no lo prohíbe; no implica soporte funcional |
| disk en /sys/power/state | false | **No existe hibernación kernel activa** |
| RAM | 31557620 KiB | ~30 GiB |
| Swap | 8388604 KiB | ~8 GiB, inferior al objetivo conservador |
| efi=noruntime activo | true | No confundir con CONFIG_HIBERNATION |
| efi=noruntime configurado | true | Pertenece a ubuntu-x1e-settings v34 |
| BIOS | 2.14.0 | 2.15.0 publicada con actualizaciones de seguridad |
| Dracut | presente | La disponibilidad del módulo resume se midió por separado |

**BLOCKED**: el kernel no anuncia hibernación o no hay swap. **UNKNOWN**: faltan observaciones críticas. **READY_FOR_EVALUATION**: los prerrequisitos visibles permiten estudiar un ensayo; no demuestra que la sesión pueda restaurarse. El swap por debajo de RAM es advertencia conservadora, no prueba absoluta de imposibilidad: la imagen hibernada puede ser menor.

## Actualización M1 — 2026-11-07

La auditoría del candidato y las dependencias X1E80100 está en [M1: fuente Ubuntu y parches](hibernate-kernel-m1.md). Se descargó y extrajo el paquete fuente 7.3.0-10.10 en laboratorio ignorado por Git. La configuración con CONFIG_HIBERNATION=y **pasó `make olddefconfig`** con herramientas aisladas, pero muestra diferencias de Rust/pahole y faltan correcciones de restauración de hardware. **NO-GO para compilar con intención de arranque o instalar.**

## Dependencia transversal obligatoria: control térmico y relojes del procesador

Antes de construir un kernel de hibernación para arrancar en el Dell XPS 13 9345, ejecutar [M3: matriz EC v8 + SCMI](hibernate-thermal-m3.md) y su validador `scripts/hibernate-thermal-m3-gate.py`. La configuración M2 preserva los símbolos SCMI. Las fuentes Ubuntu originales carecen del EC v8 y del Device Tree experimental; dan **NO_GO**. Una [copia de fuentes integrada con EC v8](thermal-hibernation-integration.md) ya pasa la puerta estática como **REVIEW_REQUIRED**, lo cual todavía no autoriza compilar para instalar ni demuestra hibernación. Incluso `REVIEW_REQUIRED` exige revisión del hardware y no autoriza instalar nada. No fusionar las ramas térmicas ni reutilizar un módulo .ko compilado para el kernel anterior.

## Orden correcto, con dependencias explícitas

### Gate 0 — protección y reversión (previo a cualquier prueba de arranque)

- [ ] Verificar respaldo **restaurable** de los datos esenciales del XPS. No depender exclusivamente de NAS degradada.
- [ ] Usuario conserva y puede localizar por su cuenta la clave de recuperación Windows BitLocker; **no compartirla ni añadirla al repositorio**.
- [ ] Verificar acceso a GRUB, entrada Windows Boot Manager y kernel Ubuntu funcional.
- [ ] Preparar USB de recuperación ARM64 compatible, alimentación estable y procedimiento manual para volver al kernel anterior.
- [ ] Fotografiar o anotar fuera del repositorio los pasos de recuperación, sin secretos.
- [ ] Autorizar específicamente cada operación de firmware/kernel/EFI/swap; el plan no constituye autorización.

**NO-GO** si falta alguno. No se suspende BitLocker ni se modifica NVRAM automáticamente.

### Gate 1 — comparar soporte upstream y kernel Ubuntu

- [ ] Buscar un kernel ARM64 que exponga CONFIG_HIBERNATION=y con soporte X1E80100 / DT Dell 9345.
- [ ] Confirmar *commits efectivamente integrados* para PCIe/NVMe, GPIO/pinctrl, SMP2P, administración de energía, Bluetooth y periféricos; un parche enviado por correo o ensayo en Lenovo no equivale a soporte Dell.
- [ ] Revisar dependencias y regresiones respecto de 7.3.0-10: NVMe/USB4, pantallas D6000, Wi-Fi, cámara, audio, NPU y suspensión.
- [ ] Preparar **paquete alternativo y entrada separada de GRUB** sin sobrescribir el kernel funcional.
- [ ] Realizar pruebas primero del arranque y dispositivos; verificar que /sys/power/state anuncie disk. Esto es necesario pero NO suficiente.
- [ ] Conservar kernel anterior como retorno; si existe fallo, no avanzar al siguiente gate.

### Gate 2 — investigar EFI Runtime como frente independiente

- La línea efi=noruntime proviene de /etc/default/grub.d/ubuntu-x1e-settings.cfg administrada por Canonical. No es una configuración casual del usuario.
- La presencia de efivars o la salida de efibootmgr no demuestra que el runtime esté completamente habilitado.
- Investigar fundamento y persistencia de workaround upstream; no quitarlo permanentemente por intuición.
- **Solamente tras Gate 0 y autorización:** comparar una entrada de arranque temporal sin el argumento, sin tocar otros parámetros de Qualcomm. Examinar servicios runtime, MOK, actualización firmware, NVRAM y estabilidad; conservar reversión inmediata.
- Si se observa bloqueo de firmware o reinicio, restaurar el parámetro y documentar logs no sensibles antes de generar ticket Dell.
- La reanudación de swap con resume= y resume_offset= no depende necesariamente de variables EFI Runtime: la hibernación y EFI son problemas relacionados, pero separados.

### Gate 3 — almacenamiento de imagen y recuperación

- [ ] Elegir swapfile persistente o swap partición. En ext4, un swapfile exige calcular offset físico en unidades de página para resume_offset; su valor puede cambiar al reemplazarlo.
- [ ] Dimensionar swap para el caso real (objetivo inicial ~32 GiB ante ~30 GiB de RAM), considerando compresión, espacio y carga; no modificar /swap.img actual sin transacción reversible.
- [ ] Validar el dispositivo de swap y el cálculo de offset, configurar dracut resume y resume=..., probar initramfs **del kernel alternativo** antes de tocar GRUB principal.
- [ ] Comprobar acceso temprano al NVMe y no restaurar una imagen sobre un sistema de archivos alterado por Windows, LiveUSB u otro arranque.
- [ ] No combinar este cambio con actualización de BIOS ni desactivación del workaround EFI, para aislar causas.

### Gate 4 — validación real de hibernación

- [ ] Primer ensayo bajo supervisión, con copia de trabajo cerrada, recuperación y alimentación disponibles.
- [ ] Confirmar que el equipo apagó, arrancó y recuperó la **misma sesión**; no confundir un arranque nuevo con reanudación.
- [ ] Verificar integridad de datos, logs kernel, NVMe, D6000/gráficos, Wi-Fi, Bluetooth, audio, USB-C, energía y suspensión deep.
- [ ] Repetir al menos tres ciclos, con eventos de éxito/fracaso reproducibles, y verificar el retorno desde GRUB.
- [ ] No habilitar botón de GNOME ni cambiar política de cierre de tapa hasta superar estas pruebas.

## ¿Generar ticket? Árbol de decisión

| Evidencia encontrada | Responsable | Qué pedir |
| --- | --- | --- |
| Ubuntu ARM64 publica kernel con CONFIG_HIBERNATION deshabilitado en X1E | Canonical / Ubuntu kernel | Soporte y validación de compilación + restauración ARM64, con manifest de parches incluidos |
| Fallo de un driver durante restauración, con kernel compilado para hibernación | Maintainer del driver / Qualcomm / kernel Linux; Canonical si paquete Ubuntu | Corregir falla reproducible de hardware con logs sanitizados |
| EFI Runtime falla al quitar efi=noruntime en condiciones controladas, incluso con BIOS evaluado | Dell firmware, con posible coordinación Canonical | Solución UEFI o justificación de workaround, datos de BIOS/modelo/repro |
| No se logra reproducir fallo EFI o la hibernación sigue deshabilitada por kernel | No abrir ticket Dell por hibernación | Resolver primero el bloqueo del kernel |

El ticket Launchpad #2172878 se refiere a MOK/EFI y debe citarse como antecedente, **no como reporte ya comprobado de hibernación**. Crear un ticket nuevo de hibernación únicamente con evidencia distinta; no duplicar.

## Paquete de evidencia publicable

Incluir únicamente: fecha, modelo genérico XPS 13 9345, Ubuntu/kernel, paquete ubuntu-x1e-settings, versión BIOS, datos normalizados del preflight, pasos de reproducción y resultados redactados, lista de controladores/commits comprobados y condiciones de reversión. No incluir serial, Service Tag, UUID/GUID, identidades, IP, cmdline completa, claves BitLocker, identificadores de arranque, credenciales ni dumps indiscriminados.

## Rollback previsto

- Si falla kernel alternativo: reiniciar por el menú GRUB al kernel estable (no tocar su initramfs).
- Si falla ensayo temporal EFI: retornar al arranque original con efi=noruntime y comprobar estado del firmware.
- Si falla restauración: no reintentar sobre una imagen posiblemente corrupta ni montar el mismo filesystem desde otro SO con imagen pendiente; decidir rescate según evidencia de almacenamiento.
- Si falla cambio de swap/Dracut: restaurar fichero de intercambio anterior y configuración verificada a partir de respaldo antes de otro ciclo.

## Referencias oficiales

- Linux swsusp https://www.kernel.org/doc/html/next/power/swsusp.html
- Dell BIOS 2.15.0 https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=PK3V5
- Dell BitLocker https://www.dell.com/support/manuals/en-us/xps-13-9345-laptop/xps-13-9345-owners-manual/bitlocker?guid=guid-02ef31d0-ad81-4e06-935d-78dba82dc625&lang=en-us
- Canonical origen del ajuste efi=noruntime https://discourse.ubuntu.com/t/foundations-team-updates-2025-07-24/64104/2
- MOK/EFI LP https://bugs.launchpad.net/bugs/2172878
