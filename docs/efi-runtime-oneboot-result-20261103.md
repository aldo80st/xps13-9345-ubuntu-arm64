# Resultado de arranque GRUB único sin efi=noruntime — 2026-11-03

**Equipo:** Dell XPS 13 9345 ARM64, Ubuntu 26.10, kernel oficial firmado 7.3.0-10-generic.
**Estado de prueba:** arrancó, Desktop Commander volvió, Secure Boot habilitado; EVDI no carga; MOK no importada.

## Preparación y ejecución

- GRUB permanente: `GRUB_DEFAULT=0`, `GRUB_TIMEOUT_STYLE=hidden`, `GRUB_TIMEOUT=0`; configuración Ubuntu `ubuntu-x1e-settings` conserva `efi=noruntime`.
- Para mostrar menú al usuario una sola vez, se fijó `recordfail=1` mediante `grub-editenv`; tras el arranque `grubenv` no tenía variables listadas, por lo que quedó despejado.
- Usuario físicamente en laptop autorizó el ensayo. En editor GRUB se retiró únicamente `efi=noruntime` de la línea `linux`, dejando el resto (incluidos `clk_ignore_unused`, `pd_ignore_unused` y `cma=128M`) sin modificar.
- GRUB mostró `error: devicetree: the command is not allowed when lockdown is enforced`; la línea `devicetree` existía previamente y fue bloqueada por la política de GRUB; **NO** evidencia de que se haya eliminado o editado. Pese al error el kernel oficial y Ubuntu arrancaron y se recuperó la conectividad remota.
- Ninguna modificación persistente a GRUB, shim, certificados MOK, Secure Boot o kernel fue parte de la prueba.

## Evidencia de arranque excepcional

- `/proc/cmdline` **NO contiene `efi=noruntime`**.
- `mokutil --sb-state` = `SecureBoot enabled`.
- `/sys/firmware/efi/efivars/SecureBoot-*`: valor 1; `SetupMode` = 0, `DeployedMode` = 1, `AuditMode` = 0.
- `journalctl -k -b`: `secureboot: Secure boot enabled`; `Kernel is locked down from EFI Secure Boot mode`; **`Remapping and enabling EFI services.`**
- `journalctl -k -b`: **`integrity: secureboot mode unknown`**, que reemplaza al mensaje de la línea original **`integrity: secureboot mode unknown, no efi`**.
- El kernel informa **`integrity: MODSIGN: Couldn't get UEFI db list`** y **`integrity: Couldn't get UEFI dbx list`**.
- `/sys/firmware/efi/mok-variables/` sigue conteniendo `MokListRT`, `MokListTrustedRT`, `MokListXRT`.
- Auditoría privilegiada mediante `keyctl show`: `.machine` = **0** certificados asimétricos, `.platform` = **0**; `.secondary_trusted_keys` = 5, `.builtin_trusted_keys` = 5; **no** está firmante EVDI.
- `mokutil --test-key MOK.der`: MOK inscrita, pero sigue advirtiendo `Failed to access kernel trusted keyring: Required key not available`.
- EVDI permanece no cargado, DisplayLink permanece iniciándose/repitiendo intentos y el kernel registra Lockdown de carga de módulo sin confianza.

## Conclusiones

1. **Ensayo de arranque completado con éxito en el sentido de arranque; reparación de EVDI NO conseguida.**
2. Quitar `efi=noruntime` **no basta** para que EFI Runtime retorne una respuesta válida a la consulta que hace `arch_get_secureboot()` (indica `unknown`), por lo que la ejecución existente de `load_uefi_certs()` sigue sin importar MOK.
3. No existe evidencia de que EVDI necesite otra firma: la firma PKCS#7 ya verificó criptográficamente contra certificado MOK inscrito.
4. La vía del parche RFC para cargar MOKvar bajo un estado Secure Boot previamente autenticado sigue siendo candidata, **pero no es aún un parche seguro aprobado**; el ensayo también demuestra que el problema NO se soluciona solamente habilitando EFI Runtime.
5. No repetir ensayos eliminando `efi=noruntime`: se arranca así una vez, y la siguiente entrada normal usa la configuración original. Mantener Secure Boot y shim.

## Acción inmediata

**Volver a arrancar normalmente, sin editar GRUB**, para recuperar la mitigación firmware `efi=noruntime` después de recopilar evidencia. Verificar posteriormente la línea de arranque y la conectividad. No reiniciar automáticamente si el usuario no está disponible para eventual intervención física.

**Aceptación para cerrar el issue:** arranque normal con `efi=noruntime` y Secure Boot habilitados, clave MOK en keyring permitido, EVDI/DisplayLink activos, ambos DP con imagen real.
