# XPS-HIB-01 — Contrato de integración entre proyectos upstream

**Versión:** 1 · **Fecha:** 2026-11-07 · **Estado:** contrato de laboratorio implementable.
**Decisión vinculante:** [ADR-0001](../../adr/ADR-0001-upstream-first-xps-hibernation.md).

## Resultado que busca el contrato

Identificar y fijar versiones de cuatro proyectos públicos sin recrear sus implementaciones ni importar dependencias inapropiadas. El kernel Canonical es **fuente base propuesta**, Qualcomm es proveedor de parches, Dell Tributo es referencia de hardware; Omarchy y NixOS son información, no plataformas de despliegue.

## Autoridad y reglas

- `docs/hibernate-upstream-projects.lock.json` controla las cuatro fuentes Git: identificador, rol, URL explícita, ref, SHA de 40 dígitos y política de uso.
- `docs/hibernate-upstream-reuse-manifest.json` sigue siendo el registro de **parches**, evidencia de inclusión, aceptaciones y bloqueos de restore. No duplicar sus datos en la lock.
- `docs/hibernate-canonical-base.md` registra la comparación con el buildinfo real 7.3.0-31.31. La equivalencia del branch actual `resolute-x1e` con el paquete exacto sigue `unverified`.
- `scripts/verify-hibernate-upstream-lock.py` valida offline y opcionalmente compara con los refs remotos. `PIN_MATCH` solo significa coincidir SHA; nunca autoriza boot o instalación. Ante `DRIFT_DETECTED`, `REMOTE_UNVERIFIED` o `INVALID`, rechazar actualización automática.
- El código Dell Tributo se estudia solo en staging `.local`; verificar licencia/SPDX y comprobar si el DTS de Canonical ya absorbió los cambios antes de importar cualquiera.
- Las observaciones de Omarchy/NixOS no deben transformarse en afirmaciones de compatibilidad Dell XPS ni en una segunda distribución del proyecto.

## Gates obligatorios y evidencias mínimas

1. **I0 — Identity**: manifest versionado, remoto fijado y comparado; no source swap ni dual authority; CI unit tests 0 fallos.
2. **I1 — Canonical**: mapear SHA del commit exacto a paquete fuente, changelog, annotations y buildinfo binario del mismo release; comparación de Kconfig; no instalar.
3. **I2 — Dell**: revisar upstream DTS/EC vs fuente exacta, atribución, compatibilidad térmica, ventiladores y SCMI sin reemplazar el EC activo.
4. **I3 — Qualcomm**: resolver PDC/clocks, PCIe v2/v7, PAS/SMP2P, TLMM, UART y Bluetooth por estado upstream y pruebas sobre la misma fuente. No suponer GO por `patch --dry-run`.
5. **I4 — Offline build**: compilar kernel, DTB, `.ko`, Module.symvers y paquetes Canonical reproducibles, sin instalación/boot.
6. **I5 — Controlled hardware**: aprobar aparte BitLocker, copia restaurable y recuperación; solo entonces pruebas de tres restauraciones de sesión.

## Contrato de fallas

Ausencia de un upstream requerido, cambio de URL/ref/rol, SHA inválido, manifest alterado o gate retirado → `INVALID`. Cambio remoto respecto del pin → `DRIFT_DETECTED`. Falla de red → `REMOTE_UNVERIFIED`. Estos estados no actualizan archivos. `PIN_MATCH` y `LOCAL_LOCK_VALID` siguen dejando `install_authorized=false` y `release_equivalence_verified=false`.

**Invariante operativo:** ninguna fase I0–I4 modifica `/boot`, EFI, GRUB, firmware, BIOS, swap, `/lib/modules`, kernel activo, EC operativo ni política SCMI.
