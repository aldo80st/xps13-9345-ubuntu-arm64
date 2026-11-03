# Implementación experimental — importación MOK sin EFI Runtime

**Fecha:** 2026-11-03
**Dispositivo:** Dell XPS 13 9345 ARM64, Ubuntu 26.10, kernel firmado `7.3.0-10-generic`.
**Estado:** RFC implementado y compilado **como objeto de prueba fuera del sistema**, NO desplegado ni aprobado desde el punto de vista de seguridad. EVDI/DisplayLink siguen inactivos.

## Trabajo ejecutado

1. Consultado APT en el **XPS**: `linux-main-modules-evdi-7.3.0-10-generic` y `linux-main-modules-evdi-unsigned-7.3.0-10-generic` no tienen candidato para **arm64**, aunque exista metadato de un paquete de igual nombre para amd64. No instalar algo de otra arquitectura.
2. Descargado mediante `apt download linux-source-7.3.0=7.3.0-10.10` el paquete **Ubuntu oficial** del kernel instalado. Extracción a `.local/kernel-mok-patch/` (excluido de Git).
3. Verificado SHA256 de `security/integrity/platform_certs/load_uefi.c`: `2abff60cd5d5fcbdd5dfde3da3ca38bd9a16dbb6b1b3b822c38596ac7128424d`.
4. Examinado el código exacto de `load_uefi.c`, `efi_secureboot.c`, `keyring_handler.c` y `machine_keyring.c`; confirmar dos controles independientes: disponibilidad de EFI Runtime y confianza de MOK.
5. Verificado en el XPS que existen `MokListRT`, `MokListXRT` y **`MokListTrustedRT`** en `/sys/firmware/efi/mok-variables/`. La bandera de confianza MOK tiene 1 byte y es utilizada por `imputed_trust_enabled()`.
6. Creado `patches/0001-RFC-efi-mokvar-without-runtime.patch`. Aplica al árbol **exacto 7.3.0-10.10** con `patch --dry-run -p1`: PASS.
7. Aplicado solo a una **copia del árbol en `.local/`**, y compilado **`load_uefi.o`** mediante Kbuild y los headers del kernel activo: **PASS**. La compilación no crea un kernel instalable ni comprueba la seguridad del cambio.
8. RFC **v3**: se corrigió la ruta de seguridad que permitía importar certificados después de fallar el parseo de `MokListXRT`. En la ruta sin Runtime exige tanto la presencia de `MokListTrustedRT` (autorización de confianza MOK de shim) como `MokListXRT`; aborta la importación de MOK si las revocaciones no se pueden analizar. Las pruebas de integración de v3 pasaron en espacio de usuario, con y sin sanitizadores. El objeto v3 **compiló** con Kbuild ARM64 y los encabezados del kernel oficial; aún falta revisión de mantenedores.
9. Se añadieron pruebas estáticas y **ejecución del propio archivo C del kernel** con servicios EFI simulados (8 escenarios) en `tests/test_kernel_mok_patch.py`, `tests/test_kernel_mok_integration.py` y `tests/mok_runtime_harness.c`. El fixture GPL-2.0 del fuente exacto incluye hash y licencia para ejecutarlas también en CI, sin descargas externas.
10. **No se cambiaron** `/boot`, EFI, shim, MOK, firmware, parámetros GRUB ni módulos instalados en esta iteración. Secure Boot permaneció activado.


## Qué propone el RFC

- Cargar claves `MokListRT` a través del *handler* específico de MOK (`get_handler_for_mok`), que aplica el control `imputed_trust_enabled()`; no tratarlas como claves genéricas `db`.
- En ausencia de `EFI_RT_SUPPORTED_GET_VARIABLE`, solo intentar la tabla estática MOK cuando `efi_enabled(EFI_SECURE_BOOT)` ya sea **verdadero**. En caso contrario, detener la importación de confianza.
- No llamar a `efi.get_variable` desde `load_moklist_certs()` cuando EFI Runtime esté deshabilitado.
- Procesar **primero `MokListXRT`** y luego `MokListRT`; **detenerse sin importar MOK** si el parseo de revocaciones falla. Sin EFI Runtime, exigir también las entradas `MokListTrustedRT` y `MokListXRT` en la tabla. La ruta normal con EFI Runtime conserva sus controles previos, salvo el endurecimiento explícito del caso de revocaciones inválidas.
- El parser EFI **real** de Ubuntu se ejecuta adicionalmente en un entorno de usuarios con listas sintéticas válidas, truncadas y malformadas y 1,500 mutaciones deterministas; tests con ASan/UBSan también pasan. Estos resultados evalúan robustez sintáctica, **no** autentican revocaciones reales.
- La matriz C simulada comprueba ocho rutas, incluida la ausencia de la autorización `MokListTrustedRT`: Secure Boot temprano inactivo; arranque sin Runtime con revocaciones válidas; revocaciones inválidas; lista de revocaciones ausente; autorización MOK de shim ausente; MOK positiva ausente; Runtime habilitado con estado de integridad desconocido; Runtime habilitado con estado de integridad confirmado. Las pruebas usan exactamente el archivo C resultante de aplicar el parche, no una reimplementación Python.

## Lo que no está demostrado

**No es una corrección desplegada.** El código oficial ARM64 de Ubuntu confirma un mecanismo preliminar importante: `efi_init()` invoca `efi_set_secure_boot(efi_get__secure_boot())`, que fija `EFI_SECURE_BOOT` antes de `efi_mokvar_table_init()`; el estado proviene del EFI stub que evalúa firmware Secure Boot y `MokSBStateRT` (shim validation disabled). Esto respalda que `efi_enabled(EFI_SECURE_BOOT)` puede ser una guardia de confianza aun con `efi=noruntime`. Se verificó en código fuente exacto (`drivers/firmware/efi/{efi-init.c,secureboot.c,libstub/secureboot.c,mokvar-table.c}`) y coincide con el arranque observado (`secureboot: Secure boot enabled` y kernel Lockdown).

**Sigue pendiente la revisión externa de seguridad** para certificar el origen autenticado de la tabla MOKvar en todas las rutas ARM64, la aplicación de revocaciones MOKX/dbx y las combinaciones de firmware/bootloader. `efi_mokvar_table_init()` valida ubicación y estructura de la tabla, **no por sí misma una firma criptográfica** del contenido. **Un PASS de compilador no sustituye esa revisión.**

**Bloqueo de seguridad principal:** el parche v3 puede procesar `MokListXRT`, pero **no puede consultar `dbx` del firmware** cuando `efi=noruntime` está activo. Exigir `MokListXRT` no sustituye todas las revocaciones de `dbx`. Hace falta revisión por mantenedores antes de conceder nuevas claves de confianza; no basta con estas pruebas aisladas o una compilación correcta.

La prueba presencial de un arranque sin `efi=noruntime` ya se realizó: Ubuntu inició con Secure Boot habilitado, pero el estado de integridad siguió `unknown` y los keyrings MOK permanecieron vacíos. Se restauró y verificó el arranque habitual con `efi=noruntime`; no repetir ese ensayo. Los dos DisplayPort continúan sin validación funcional.

## Próximas etapas bajo condiciones claras

**Trabajo del asistente, sin tocar arranque:** revisión upstream del RFC; pruebas de matriz fail-closed/sin tabla/MOK rechazada/DBX; preparación de reporte para Canonical y comparación con parches existentes; seguimiento de paquete firmado ARM64.

**Requiere decisión externa antes de ejecutar:** validación de la política de revocaciones por mantenedores de integridad/EFI y publicación de un kernel firmado por Canonical para producción. La prueba presencial de GRUB **ya se completó y no resolvió MOK**; no repetirla. No instalar un kernel no firmado ni desactivar Secure Boot/validación shim.

**Definición de terminado:** Secure Boot/shim habilitados, EVDI carga sin error de confianza, DisplayLink activo y **ambos DisplayPort funcionan después de un arranque normal**, con evidencia en un monitor físico.

## Reproducción local del build RFC (no modifica el kernel activo)

1. Obtener exactamente `linux-source-7.3.0_7.3.0-10.10_all.deb` de los repositorios oficiales y extraer `security/integrity/platform_certs/` y `security/integrity/integrity.h` del tarball interno.
2. `patch --dry-run -p1 < patches/0001-RFC-efi-mokvar-without-runtime.patch`
3. Aplicar el parche **solo al árbol de trabajo temporal**.
4. En el directorio temporal `security/integrity/platform_certs` crear un `Makefile` temporal con `obj-m += load_uefi.o` y ejecutar `make -C /usr/src/linux-headers-7.3.0-10-generic M=/ruta/al/directorio/temporal load_uefi.o`.
5. **No** instalar el `.o` ni intentar convertirlo directamente en módulo cargable: `load_uefi.c` pertenece al núcleo del kernel, no es un módulo externo desplegable.

**Importante:** el RFC es material para revisión técnica; todavía NO cumple los criterios para modificar el sistema instalado.
