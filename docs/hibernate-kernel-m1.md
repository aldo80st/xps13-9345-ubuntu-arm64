# M1 — Auditoría de fuentes para hibernación ARM64 (Dell XPS 13 9345)

**Fecha de inspección:** 2026-11-07. **Estado:** preparación de laboratorio; **NO-GO para instalación o arranque**.
**Hardware:** Dell XPS 13 9345 con Qualcomm X1E80100. Ubuntu 26.10 ARM64, kernel activo `7.3.0-10-generic`.

## Decisión ejecutiva

La **base de trabajo seleccionada** es el código fuente oficial de Ubuntu `linux-source-7.3.0=7.3.0-10.10` (no un kernel funcional de hibernación). No existe evidencia suficiente de kernel empaquetado e íntegramente validado para hibernación del **Dell XPS 13 9345**. Por ahora se prepara un `.config` experimental no compilado. No aplicar parches arbitrarios ni instalarlo en el equipo principal.

## Inventario local verificado

| Elemento | Resultado |
| --- | --- |
| Kernel actual | 7.3.0-10-generic, ARM64 |
| Kernel Ubuntu candidato apt | 7.3.0-10.10; sin versión nueva publicada en los índices locales consultados |
| CONFIG_ARCH_HIBERNATION_POSSIBLE | y |
| CONFIG_HIBERNATION en kernel actual | no habilitado |
| /sys/power/state | freeze mem; disk no disponible |
| Fuente Ubuntu | linux-source-7.3.0_7.3.0-10.10_all.deb, descargada con apt download |
| Paquete fuente SHA256 calculado localmente | `becefccd4560e96bcf9e7f0aba9ef830e2734a8db601c0a3f5c921582e1c726a` |
| Metadatos | Package linux-source-7.3.0, Version 7.3.0-10.10; tar.bz2 de ~201.7 MB |
| Ubicación | `.local/kernel-source/` (ignorado por Git), árbol fuente descomprimido de ~1.8 GB |
| Kconfig de laboratorio | `.local/kernel-source/candidate-config/.config`: CONFIG_HIBERNATION=y, ARCH_HIBERNATION_POSSIBLE=y, SWAP=y |
| `make olddefconfig` | **PASS** con `flex 2.6.4`, `bison 3.8.2`, `m4 1.4.21` extraídos en `.local/kernel-source/isolated-toolchain/`, sin instalar paquetes |
| Diferencia con config de distribución | 68 líneas de opciones modificadas (incluye Rust, pahole y metadatos del compilador), además de habilitar hibernación: **no es todavía una configuración fiel** |
| Compilación kernel / instalación / GRUB | **NO iniciadas** |

El SHA256 queda registrado como huella reproducible de los bytes descargados. No se obtuvo un digest independiente de los índices apt-cache en esta inspección; no equiparar huella calculada con validación independiente de firma.

## Dependencias Qualcomm: evidencia y estado (2026-11-07)

| ID | Subsystema / parche | Estado de la fuente upstream examinada | Presencia en fuente Ubuntu 7.3.0-10.10 |
| --- | --- | --- | --- |
| P1 | pinctrl: qcom, guardar/restaurar TLMM GPIO; v4 | **Applied** 2026-10-28 en árbol del mantenedor, commit `30d9a180c86e`. No equivale a merged mainline ni Ubuntu | Ausentes callbacks `msm_pinctrl_freeze_noirq` / `msm_pinctrl_restore_noirq` |
| P2 | PCI: qcom, forzar apagado controlador al congelar imagen; v2 | **Patch bajo revisión** (12 oct); basado en `shutdown()` serie **v6** | Ausente callback específico `freeze_noirq` en pcie-qcom.c |
| P2a | Prerrequisito PCI: Qualcomm `shutdown()` | Serie **v7** publicada el 29 oct; debe cotejarse y rebasarse junto a P2 antes de usar | Ausente `qcom_pcie_shutdown` en fuente inspeccionada |
| P3 | soc: qcom: smp2p, reinicializar negociación tras restore | **Patch publicado** (9 oct); una falla independiente de estado de remoteproc se reconoce abierta | Sin callback de restauración en smp2p.c |
| P4 | serial: qcom-geni, reiniciar UART en restore; v2 | **Patch publicado** (27 oct); pruebas en Lenovo con correcciones adicionales | Sin callback de restauración en qcom_geni_serial.c |
| P5 | Bluetooth: hci_qca, reiniciar in-band sleep al cortar energía; v2 | **Patch publicado** (14 oct); pruebas Lenovo y OnePlus, no Dell | La función `qca_power_off` mantiene lógica previa y no restablece ambos estados IBS |

**Advertencia esencial:** “Publicada”, “Applied en árbol de mantenedor”, “Mainline” y “Empaquetada en Ubuntu” son etapas distintas. Aquí **no se verificó que P2–P5 hayan sido fusionados en mainline**. La auditoría de fuente sí demuestra que no están presentes en el paquete Ubuntu inspeccionado en las formas analizadas.

### Referencias upstream primarias

- P1 v4: https://lists.openwall.net/linux-kernel/2026/10/21/2649
- P1 aplicada: https://lists.openwall.net/linux-kernel/2026/10/28/768
- P2 v2: https://lists.openwall.net/linux-kernel/2026/10/12/1513
- P2a v7: https://lists.openwall.net/linux-kernel/2026/10/29/328
- P3: https://lists.openwall.net/linux-kernel/2026/10/09/2521
- P4 v2: https://lists.openwall.net/linux-kernel/2026/10/27/2926
- P5 v2: https://lists.openwall.net/linux-kernel/2026/10/14/2305
- Kernel oficial: repositorio Ubuntu 26.10 `linux-source-7.3.0`.

## Auditoría de diferencias verificada en XPS (2026-11-07)

El nuevo script [audit-hibernate-config.py](../scripts/audit-hibernate-config.py) comparó las configuraciones reales y reportó **UNRELATED_DRIFT**: 8 símbolos de hibernación frente a 50 símbolos ajenos (27 pruebas automatizadas OK). Las 68 líneas de diferencias textuales de M1 no eran 68 símbolos únicos. La revisión externa de P1–P5 mediante Paseo quedó en [hibernate-patch-review-20261107.md](hibernate-patch-review-20261107.md); mantiene el **NO-GO** para un kernel arrancable.

## Secuencia correcta de próxima iteración

1. Comprobar estado actual de integración upstream P1–P5 y encontrar versión de P2 adaptada explícitamente a P2a v7. **No asumir** compatibilidad de v2+v7.
2. Elegir kernel experimental ARM64 con mismo soporte Dell; preservar árbol original y definir manifest de commits SHA completos y hashes de parches.
3. Resolver equivalencia de toolchain Ubuntu para no perder las opciones Rust/BPF y de depuración. `make olddefconfig` ya acepta `CONFIG_HIBERNATION=y` y `CONFIG_HIBERNATE_CALLBACKS=y` con herramientas sólo en `.local`, pero genera diferencias no atribuibles a hibernación. No compilar ni instalar hasta preservar las opciones relevantes del kernel original.
4. Compilar **sin instalar** y verificar ABI, módulos, firmas y DT Dell, comparando Bluetooth/NVMe/USB4/Adreno/DisplayLink/Wi-Fi frente a kernel actual.
5. Gate humano de recuperación de BitLocker, backup fiable y opción de regreso a GRUB antes de instalar un kernel alternativo para ensayos. Requiere autorización específica; se evita depender de la NAS degradada como único respaldo.

## No se hizo

- `sudo apt install`, cambios en `/boot`, GRUB, BIOS, UEFI, Secure Boot, BitLocker, swap, dracut, rootfs operativo, encendido/apagado o hibernación.
- No se compiló kernel ni se creó paquete .deb alternativo. La configuración **sí pasó Kconfig**, pero carece de equivalencia funcional de toolchain y de los parches necesarios. No es candidato booteable.
- No se abrió ticket a Dell o Canonical, porque todavía falta una reproducción específica y/o verificar disposición upstream de los parches.

## Avance M2 — 2026-11-07

La cadena reproducible (Ubuntu 26.10 arm64 + GCC 15.3 + Rust 1.97.1 + LLVM 22 + Bindgen 0.72.1 + pahole 1.31) se verificó en Docker sobre el XPS, sin instalar herramientas en el host. La nueva prueba `olddefconfig` conserva todas las opciones externas a hibernación; dos selecciones LZ4 son explícitamente requeridas por el Kconfig. Resultado final `CLEAN`, 8 opciones directas + 2 dependencias + 0 inesperadas. Véase [M2](hibernate-m2-toolchain.md).

**Aún no existe un kernel alternativo compilado ni probado**. La revisión de P2/P2a PCIe, SMP2P/remoteproc y los demás parches Qualcomm sigue impidiendo la instalación. Además, el [gate de compatibilidad M3 EC v8/SCMI](hibernate-thermal-m3.md) exige incorporar controlador, binding y DTS Dell actualmente ausentes de las fuentes Ubuntu.
