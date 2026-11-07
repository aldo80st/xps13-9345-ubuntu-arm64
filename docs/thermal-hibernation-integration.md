# Integración reproducible de Dell EC v8, SCMI y hibernación (M3)

**2026-11-07 · Estado:** integración de **fuentes en laboratorio**, `REVIEW_REQUIRED`. No es un kernel compilado, instalado ni probado tras hibernar.

## Origen y frontera de seguridad

Se conservaron los parches públicos de la serie upstream Dell Embedded Controller **v8** (binding, módulo, DTS) exactamente como estaban en el staging térmico. Se incorporan como archivos de texto en `patches/dell-ec-v8/` y quedan sujetos a SHA256. **No** se incluyen el módulo `.ko`, DTB experimental, scripts de GRUB con UUID de particiones ni copias de firmware.

| Parche | SHA256 | Alcance |
| --- | --- | --- |
| `v8-1.diff` | `c73f41f2e3c91afd388aa442b616f82c0be0f39b9a3185391da387cd099ea6e0` | Binding del Dell EC |
| `v8-2.diff` | `5eaba144c037a94d700e73b248883246494683b4aa8a36d71c17a3625a5c5938` | Controlador, Makefile, Kconfig |
| `v8-3.diff` | `8a25b419d57694ceceaa024f3152c4363268d2faf9fffe0ec1531a4f64f05620` | Device Tree del XPS 13 9345 |

**Adaptación explícita:** `v8-2.diff` fue propuesto sobre una versión de `drivers/platform/arm64/Kconfig` ligeramente distinta. El hunk de Kconfig no aplica literalmente al código Ubuntu 7.3. El ejecutor `scripts/stage-dell-ec-v8.py` conserva la copia original byte por byte, aplica los otros tres diffs de `v8-2.diff` y agrega únicamente `CONFIG_EC_DELL_XPS` delante de `EC_HUAWEI_GAOKUN`, validando el ancla. Si cambia la estructura, falla y limpia el staging. No modifica el archivo oficial de entrada ni la configuración de arranque.

La aplicación de parches en una copia de fuentes **no certifica** revisión de seguridad ni compatibilidad con firmware. Hacer `patch` con coincidencia contextual no prueba que se hayan restituido físicamente ventiladores o sensores.

## Reproducción sobre el XPS, sin sudo

Prerequisito: haber preparado la fuente oficial Ubuntu 7.3.0-10.10 en `.local/kernel-source/tree/linux-source-7.3.0` y terminado M2; disponer de espacio para una segunda copia (~1.8 GiB). El comando falla si el destino ya existe.

```bash
python3 scripts/stage-dell-ec-v8.py \
  --source-tree "$PWD/.local/kernel-source/tree/linux-source-7.3.0" \
  --output "$PWD/.local/m3-ec-source"
```

**Evidencia 2026-11-07:** `STAGED_REVIEW_REQUIRED` (exit 0), parche 1+2 (adaptación Kconfig)+3 integrados en copia independiente; entrada Ubuntu sin modificar. El árbol generado contiene el controlador EC, binding, Makefile/Kconfig y nodo Device Tree del XPS.

Para validar con las dependencias existentes, en el contenedor ARM64 reproducible de M2 se pasó `olddefconfig` usando una copia de `.local/m2-out/.config` con `CONFIG_EC_DELL_XPS=m`. Se obtuvo:

```text
CONFIG_HIBERNATION=y
CONFIG_EC_DELL_XPS=m
CONFIG_ARM_SCMI_CPUFREQ=m
```

El archivo de configuración de M3 se conserva en `.local/m3-config/.config`, fuera del repositorio. **No** se generó kernel, módulo ni DTB arrancable.

## Validación y resultado

```bash
python3 scripts/hibernate-thermal-m3-gate.py \
  --source-tree "$PWD/.local/m3-ec-source" \
  --baseline /boot/config-7.3.0-10-generic \
  --candidate "$PWD/.local/m3-config/.config" \
  --ec-patches "$PWD/patches/dell-ec-v8" --json

python3 -m unittest discover -s tests -p 'test_*.py' -q
```

- Estado en **fuentes Ubuntu originales sin adaptación**: `NO_GO` por ausencia de EC en Kconfig, driver, binding y DTS.
- Estado en **copia integrada y configuración M3**: `REVIEW_REQUIRED`, diez comprobaciones estáticas verdaderas, sin bloqueos; siempre `approval=not_authorized`.
- 88 pruebas Python en el repositorio pasaron, incluyendo ocho nuevas sobre procedencia, adaptación determinista y aislamiento.
- Datos observados en el arranque experimental (fuera de las fuentes): controlador `dell_xps_ec` cargado y dispositivo I²C `5-003b`, `scmi_cpufreq` con gobernador `ondemand` en 3 políticas. **No** se realizó prueba de hibernación real.

## Relación con las ramas de métricas

El trabajo de medición en GNOME Resources (`fix/resources-51-qualcomm-cpu-metrics`) se conserva como componente de observabilidad; no modifica el gobernador real `scmi_cpufreq`, que pertenece a kernel/SCMI. La integración Git puede hacer merge de esa rama sin trasladar modificaciones al sistema operativo.

## Límites obligatorios antes de compilar e instalar

1. **Kernel de laboratorio**: revisar ABI y controladores, verificar compilación del `dell-xps-ec` v8, Kconfig y DTB Dell con los parches Qualcomm P1–P5 consistentes.
2. **PCIe**: resolver la incompatibilidad semántica del parche freeze v2 frente a shutdown v7; no encadenar versiones a ciegas.
3. **Remoteproc/SMP2P**: determinar forma segura de detener/reiniciar coprocesadores durante imagen/restauración.
4. **EC/SCMI**: verificar callbacks de freeze/thaw, poweroff/restore, termistores, ventiladores y escalamiento de frecuencias después de restaurar.
5. **Puerta humana**: respaldo restaurable, clave BitLocker bajo control del usuario, GRUB de recuperación y autorización específica antes de instalar kernel, modificar BIOS/EFI/swap o ejecutar hibernación.

**Un merge Git no ejecuta ni instala un kernel.** La integración es una mejora de trazabilidad y código experimental reproducible, no una declaración de que el portátil ya puede hibernar.
