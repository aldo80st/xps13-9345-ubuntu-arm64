# H1 — Canonical qcom-x1e como línea base mantenida (2026-11-07)

**Decisión:** adoptar el flujo de compilación y empaquetado Ubuntu Concept/Canonical para futuras pruebas ARM64 del XPS 13 9345, en lugar de mantener un kernel completo propio sobre generic. **No instalar ni arrancar ninguna imagen aún.** El hardware actual sigue en `7.3.0-10-generic`.

## Evidencia externa y de paquete exacto

- Paquetes Ubuntu Concept: https://launchpad.net/~ubuntu-concept/+archive/ubuntu/x1e (advertencia del equipo: experimentales, no soportados como producción).
- Instrucciones originales del mantenedor: https://discourse.ubuntu.com/t/how-to-build-your-own-ubuntu-concept-x-elite-kernel/49941/3 (usar `debian.qcom-x1e/config/annotations`, exportar/importar con `debian/scripts/misc/annotations` y construir los paquetes con reglas Debian/Ubuntu).
- Artefacto inspeccionado en el XPS el 7 de noviembre de 2026:
  `https://ppa.launchpadcontent.net/ubuntu-concept/x1e/ubuntu/pool/main/l/linux-qcom-x1e/linux-buildinfo-7.3.0-31-qcom-x1e_7.3.0-31.31_arm64.deb`
- Control Debian del artefacto: `Package=linux-buildinfo-7.3.0-31-qcom-x1e`, `Version=7.3.0-31.31`, `Architecture=arm64`; SHA256 **`120e3bd802af4f4c7a307b46b203662958d9c093a797e1e5cbd58dd39603136c`**.
- Configuración verificada dentro del paquete (no valores presumidos): `# CONFIG_HIBERNATION is not set`; `CONFIG_ARCH_HIBERNATION_POSSIBLE=y`, `CONFIG_SUSPEND=y`, `CONFIG_ARM_SCMI_CPUFREQ=m`, `CONFIG_PCIE_QCOM=y`, `CONFIG_QCOM_SMP2P=m`, `CONFIG_QCOM_PDC=y`, `CONFIG_SWAP=y`. El kernel generic del equipo también tiene hibernación deshabilitada.
- Para el Dell: https://github.com/alexVinarskis/linux-x1e80100-dell-tributo mantiene referencia de device-tree y EC. Documenta **suspend** funcional, no prueba hibernación. Revisión general Snapdragon: https://github.com/omacom/omarchy/discussions/11823 reporta restauración fallida en Lenovo; NO extrapolar al Dell.

## Reproducción sin instalación

Este ejemplo emplea una carpeta desechable local con el paquete verificado; no escribe en el sistema ni ejecuta `apt`.

```bash
mkdir -p .local/qcom-x1e-buildinfo
cd .local/qcom-x1e-buildinfo
curl -fL --retry 1 \
  'https://ppa.launchpadcontent.net/ubuntu-concept/x1e/ubuntu/pool/main/l/linux-qcom-x1e/linux-buildinfo-7.3.0-31-qcom-x1e_7.3.0-31.31_arm64.deb' \
  -o linux-buildinfo.deb
echo '120e3bd802af4f4c7a307b46b203662958d9c093a797e1e5cbd58dd39603136c  linux-buildinfo.deb' | sha256sum -c -
dpkg-deb -f linux-buildinfo.deb Package Version Architecture
dpkg-deb -x linux-buildinfo.deb unpacked
grep -E '^# CONFIG_HIBERNATION is not set|^CONFIG_ARM_SCMI_CPUFREQ=' \
  unpacked/usr/lib/linux/7.3.0-31-qcom-x1e/config
```

Desde la raíz del repositorio, comparar de manera **read-only** la configuración del kernel activo y la fuente empaquetada:

```bash
python3 scripts/audit-qcom-x1e-baseline.py \
  --current-config /boot/config-"$(uname -r)" \
  --candidate-config .local/qcom-x1e-buildinfo/unpacked/usr/lib/linux/7.3.0-31-qcom-x1e/config \
  --candidate-release 7.3.0-31-qcom-x1e --json
```

**Resultado efectivamente observado en el XPS:** código de salida `1`, `status=NO_GO`, `blockers=["HIBERNATION_NOT_ENABLED"]`, `boot_authorized=false`. Sin regresiones configuracionales de los diez símbolos auxiliares que comparó el programa. El controlador EC Dell no se identifica por ese símbolo en el paquete (`EC_DELL_XPS=UNKNOWN`): NO implica que el equipo esté soportado ni que ese controlador funcione en el candidato. No se actualizó la instalación.

## Estrategia que reemplaza al kernel artesanal

1. **Mantener Canonical como baseline de paquetes y compilación:** usar su variante `linux-qcom-x1e` y su formato de configuración por annotations. No instalar directamente las imágenes del PPA experimental en el XPS sin una puerta H4 de recuperación.
2. **Integrar por procedencia, no copiar a ciegas:** cada componente PCIe, SMP2P/remoteproc, PDC, clocks, pinctrl, UART, Bluetooth, Dell DTS/EC se traza a una versión y un estado upstream. NO comparar solo nombres de parches.
3. **Conservar exclusivamente integraciones Dell probadas** y el sistema existente de tests, logs, manifests y gates.
4. **H2/H3:** reconstruir en laboratorio un kernel Canonical con anotaciones actualizadas y luego verificar `.ko`, `Module.symvers`, DTB, SCMI y Dell EC. Publicar únicamente artefactos offline con SHA, sin hacer `make install` ni escribir en `/boot`.
5. **H4/H5:** requieren llave BitLocker local y respaldos restaurables, método de rescate y aprobación separada antes de probar arranque y restauración real.

**Lo que todavía NO existe aquí:** una imagen de kernel comprobada que restaure sesiones hibernadas en este Dell. Activar solo `CONFIG_HIBERNATION=y`, ampliar swap o reemplazar `efi=noruntime` no garantiza recuperación. Los validadores de H1 no autorizan instalación ni suspend-to-disk.

Trazabilidad: [Epic #21](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/21), [issue de baseline #39](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/39), [matriz upstream #40](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/40).
