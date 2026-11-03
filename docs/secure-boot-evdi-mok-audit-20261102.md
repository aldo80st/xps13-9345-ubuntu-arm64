# EVDI, Secure Boot y MOK — auditoría de causa (2026-11-02)

**Equipo:** Dell XPS 13 9345, Snapdragon X Elite, Ubuntu 26.10 ARM64, kernel `7.3.0-10-generic`, DisplayLink D6000 `17e9:6006`.

**Estado:** causa muy acotada; **no corregido**, pruebas privilegiadas **únicamente de lectura**, sin cambio en Secure Boot, shim, EFI, MOK, firmware ni bootloader.

## Evidencia observada

1. `mokutil --sb-state`: **SecureBoot enabled**; el kernel aplica Lockdown y rechaza `modprobe evdi`.
2. `evdi.ko.zst` corresponde a `7.3.0-10-generic ... aarch64` y tiene firma PKCS#7 SHA-512.
3. Descomprimimos temporalmente el módulo, extrajimos su estructura de firma Linux y verificamos el contenido firmado con `openssl cms -verify -binary -inform DER -content <modulo-sin-firma> -certfile <MOK-publico-PEM> -noverify`. **Exit code 0**: la firma PKCS#7 es válida criptográficamente respecto a `/var/lib/shim-signed/mok/MOK.der`. No se leyó la clave privada y no se modificó el módulo.
4. `mokutil --test-key /var/lib/shim-signed/mok/MOK.der`: certificado inscrito, pero `Failed to access kernel trusted keyring: Required key not available`.
5. La tabla EFI `/sys/firmware/efi/mok-variables/MokListRT` existe (2,117 bytes), incluye **dos certificados** y contiene byte a byte el certificado MOK local utilizado para verificar el módulo.
6. Línea de arranque: `efi=noruntime`. El kernel registra **`integrity: secureboot mode unknown, no efi`**.
7. El parámetro **proviene del paquete Ubuntu `ubuntu-x1e-settings`, versión 34**: `/etc/default/grub.d/ubuntu-x1e-settings.cfg`. No es una personalización local. Un informe del equipo Ubuntu indica que el paquete lo impone por compatibilidad Snapdragon.
8. Los keyrings `.machine`, `.platform` y `.secondary_trusted_keys` **no pudieron consultarse directamente**, ya que `keyutils` no está instalado. Incluso leyendo `/proc/keys` como administrador la visibilidad de esas claves no es concluyente. **No afirmar que están vacíos.**
9. Los identificadores `modinfo sig_key` y X.509 `subjectKeyIdentifier` no coinciden, **pero esto no prueba una clave incorrecta**, porque la firma PKCS#7 **sí pasó verificación criptográfica** contra el MOK local. No volver a firmar EVDI como primer paso.

## Mecanismo plausible y reproducible

El código upstream `security/integrity/platform_certs/load_uefi.c` abandona la importación de certificados cuando `efi_rt_services_supported(EFI_RT_SUPPORTED_GET_VARIABLE)` es falso **antes de intentar cargar la tabla MOK de shim**. El mensaje del kernel confirma que no puede realizar una comprobación EFI Runtime. Por tanto, es plausible que el certificado MOK esté inscrito y presente en `MokListRT`, pero no sea importado al keyring confiable necesario para admitir EVDI.

**Estado de certeza:** firma válida y certificado inscrito **verificados**. El flujo que omite la carga por ausencia de runtime está respaldado por la fuente del kernel; falta observar directamente el keyring bajo este kernel o realizar una prueba de arranque controlada que confirme la relación causal.

## Decisión de ingeniería

**No** quitar `efi=noruntime` persistentemente, porque Ubuntu lo impone como workaround de la plataforma y eliminarlo puede reintroducir fallos de firmware. Tampoco desactivar Secure Boot, shim, Lockdown ni verificación de firmas.

Orden preferido:
1. Consultar **paquetes upstream** que eviten ese retorno temprano al disponer de `MokListRT` en la tabla de configuración EFI, incluso sin EFI Runtime Services. Esta vía preservaría `efi=noruntime`.
2. Si el usuario autoriza explícitamente y tiene acceso físico y recuperación, preparar **una sola prueba de arranque no persistente sin `efi=noruntime`**. Verificar logs, confianza MOK y carga EVDI, sin tocar la política Secure Boot. Si falla el arranque, apagar y reiniciar con entrada normal. No programar prueba automática.
3. Si la confianza se recupera, probar EVDI y ambos DisplayPort físicamente. No cerrar issue hasta ver las dos pantallas.
4. Como provisional, probar el **HDMI Alt Mode** nativo del D6000 en una sola pantalla, sin afirmar que restaura los dos DP.

## Fuentes

- [Ubuntu: Secure Boot y MOK](https://documentation.ubuntu.com/security/security-features/platform-protections/secure-boot/)
- [Kernel upstream: `load_uefi.c`](https://github.com/torvalds/linux/blob/master/security/integrity/platform_certs/load_uefi.c)
- [Kernel: `integrity: secureboot mode unknown, no efi`](https://lists.openwall.net/linux-kernel/2026/01/15/27)
- [Equipo Ubuntu: `ubuntu-x1e-settings` impone `efi=noruntime`](https://discourse.ubuntu.com/t/foundations-team-updates-2025-07-24/64104/2)
- [Dell D6000: HDMI Alt Mode](https://www.dell.com/support/kbdoc/en-ca/000126592/dell-dual-video-d1000-usb-3-0-d3100-and-universal-d6000-docking-stations-do-not-support-daisy-chain-functionality)

## Instrumentación

`scripts/audit-mok-keyrings-readonly.sh` obtiene exclusivamente métricas agregadas del keyring y de MOK, sin imprimir nombres de firmas ni contenidos de certificados. Requiere root para consultar la tabla EFI; ejecutar solo después de revisar el script. La verificación PKCS#7 se realizó por separado y no está automatizada en ese script.

No publicar archivos `MOK.priv`, `MOK.der`, `MokListRT`, módulos ni variables EFI.
