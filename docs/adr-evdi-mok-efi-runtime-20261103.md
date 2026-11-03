# ADR — EVDI, MOK y EFI Runtime en Snapdragon X Elite

Fecha de evaluación: 2026-11-03
Equipo: Dell XPS 13 9345, Ubuntu 26.10 ARM64, kernel oficial firmado 7.3.0-10.10.
Estado: **diagnóstico concluido; cambio de arranque NO autorizado ni ejecutado; DisplayPort doble NO resuelto**.

## Evidencias reproducibles

- Secure Boot habilitado, shim firmado instalado, bloqueo kernel activo.
- EVDI 1.15.0 DKMS firmado PKCS#7/SHA512 para este kernel. Se verificó criptográficamente contra el certificado público MOK inscrito (OpenSSL CMS exit 0); no firmar de nuevo.
- Tabla shim `/sys/firmware/efi/mok-variables/MokListRT` presente: dos certificados, incluido el MOK verificado.
- Con `keyutils` 1.6.3 instalado desde Ubuntu Stonking y autorización administrativa **solo de lectura**, `keyctl show` permitió consultar cuatro keyrings:
  - `.machine`: 0 certificados asimétricos.
  - `.platform`: 0 certificados asimétricos.
  - `.secondary_trusted_keys`: 5 certificados asimétricos; no coincide con el firmante de EVDI.
  - `.builtin_trusted_keys`: 5 certificados asimétricos; no coincide con el firmante de EVDI.
- `efi=noruntime` viene de `ubuntu-x1e-settings` v34. El kernel informa `integrity: secureboot mode unknown, no efi`.
- El código Linux `security/integrity/platform_certs/load_uefi.c` retorna cuando `EFI_RT_SUPPORTED_GET_VARIABLE` no está disponible, antes de cargar MOK por EFI configuration table.
- Tras `apt-get update` el 2026-11-03: última revisión firmada Ubuntu disponible `7.3.0-10.10` (ya instalada); no hay `linux-modules-evdi` prefirmado de Canonical en los repositorios configurados.
- Baseline verificada por `scripts/verify-evdi-after-oneboot.sh`: EVDI ausente, DisplayLink inactivo, ningún DP conectado en DRM, `pd-mapper` y agente remoto activos. Advertencias de `journalctl` no constituyen prueba de funcionalidad de dos pantallas.

## Causa inmediata demostrada y causa de raíz

**Demostrado:** el kernel no tiene la clave MOK correspondiente a la firma válida de EVDI en los keyrings admitidos. Por eso no debe cargar el módulo mientras Lockdown está activo.

**Hipótesis causal sólida pero pendiente de ensayo:** el parámetro `efi=noruntime` bloquea la ruta que importa `MokListRT` al keyring de máquina. El código upstream y el mensaje `no efi` respaldan esta ruta, pero un ensayo de arranque reversible o una corrección firmada validada demostraría causalidad.

## Opciones y decisión

| Alternativa | Aplicabilidad | Decisión |
| --- | --- | --- |
| Kernel Ubuntu firmado con carga de MOK mediante config table sin EFI Runtime | Soluciona raíz manteniendo `efi=noruntime` y Secure Boot; necesita revisión de seguridad (no importar certificados si Secure Boot no está probado). | **PREFERIDA / NO DISPONIBLE COMO PAQUETE ACTUAL**. Preparar reporte para Canonical; no inventar un kernel firmado. |
| Arranque puntual del mismo kernel oficial retirando solo `efi=noruntime` de la línea de GRUB para ese arranque | Permite ensayo causal sin modificar configuración persistente; **riesgo real de fallo EFI/freeze**, ya que ese parámetro mitiga un bug de firmware Snapdragon. | **SOLO CON AUTORIZACIÓN EXPLÍCITA Y OPERADOR FRENTE AL XPS**. No realizar automáticamente. |
| Refirmar EVDI / reenrolar MOK | Firma válida y certificado inscrito; el problema es la ausencia de confianza en el kernel. | **DESCARTADA**. |
| Deshabilitar Secure Boot o shim, relajar Lockdown, usar kernel no firmado | Contradice requisitos de seguridad. | **PROHIBIDA**. |
| Dock D6000 HDMI por DP Alt Mode (solo una pantalla) | Fallback parcial de hardware, requiere cable/monitor y prueba física. | **OPCIONAL**; no cierra requisito de dos DP. |

## Preparación de prueba de arranque único (SIN ejecutar)

**Precondiciones:**
1. Usuario presente físicamente y autorización específica para un ensayo que habilita EFI Runtime **una sola vez**. No operar desatendido. Equipo con corriente, trabajo guardado, acceso a firmware/Windows y recuperación BitLocker disponible localmente si aplica.
2. Verificar la posibilidad de mostrar GRUB: el XPS usa `GRUB_TIMEOUT_STYLE=hidden` y `GRUB_TIMEOUT=0`. La entrada al menú mediante `Esc` durante arranque puede no ser fiable; **NO reconfigurar GRUB persistentemente sin una segunda revisión**.
3. No cambiar `/etc/default/grub`, `ubuntu-x1e-settings.cfg`, NVRAM, shim, MOK ni el kernel firmado.
4. Con GRUB visible, pulsar `e` sobre la entrada normal Ubuntu, retirar **únicamente** `efi=noruntime` de la línea que empieza con `linux`, comprobar que los demás parámetros quedan intactos y arrancar una vez con `Ctrl+X` (o `F10` si GRUB lo indica).
5. Si se congela o falla: apagar y volver a arrancar normalmente. La línea editada **no persiste**; el `ubuntu-x1e-settings.cfg` original conserva `efi=noruntime`. No reintentar indefinidamente.
6. Si arranca: ejecutar `scripts/verify-evdi-after-oneboot.sh`, confirmar Secure Boot activo y GRUB/shim sin desactivar, inspeccionar keyrings mediante `keyctl` con autorización si se requiere, cargar/validar EVDI y servicio DisplayLink según evidencia, comprobar físicamente dos DP.
7. Si EVDI carga pero DisplayLink no da imagen, abrir segundo frente de fallo driver/user-space sin marcar la causa como resuelta.
8. Volver al arranque estándar a continuación del ensayo y documentar ambos estados.

**Criterio de STOP:** congelamiento de firmware, fallo de pantalla integrada, Secure Boot no confirmado o anomalía crítica. No permitir reinicio automático a ciegas.

## Fuentes primarias

- [Kernel Linux: carga MOK y chequeo prematuro EFI](https://raw.githubusercontent.com/torvalds/linux/master/security/integrity/platform_certs/load_uefi.c)
- [Ubuntu X1E obliga efi=noruntime](https://discourse.ubuntu.com/t/foundations-team-updates-2025-07-24/64104/2)
- [Johan Hovold, Snapdragon X Elite: workaround requerido por bug firmware](https://github.com/jhovold/linux/wiki/T14s)
- [Secure Boot Ubuntu](https://documentation.ubuntu.com/security/security-features/platform-protections/secure-boot/)
- [Canonical LP #2131181: MOK en ring incorrecto; tema diferente](https://lists.ubuntu.com/archives/kernel-team/2026-October/172721.html)

**No confundir esta ADR con aprobación del ensayo; el usuario debe aceptarlo de manera informada.**
