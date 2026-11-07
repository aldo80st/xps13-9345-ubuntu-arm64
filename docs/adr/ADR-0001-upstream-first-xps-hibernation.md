# ADR-0001 — Integración upstream-first para XPS-HIB-01

- **Estado:** adoptado para trabajo de laboratorio, pendiente de validar kernel compilable
- **Fecha:** 2026-11-07
- **Decisión vigente:** no mantener un kernel Qualcomm paralelo ni duplicar arreglos upstream
- **Epic:** [XPS-HIB-01](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/21)

## Contexto y problema

Las PR #11, #20, #31–#38 y #41–#43 consolidaron herramientas y evidencias de hibernación en Ubuntu ARM64 del Dell XPS 13 9345. El kernel operativo `7.3.0-10-generic` no tiene `CONFIG_HIBERNATION`. La versión empaquetada `linux-qcom-x1e 7.3.0-31.31` publicada por Ubuntu Concept tampoco: `# CONFIG_HIBERNATION is not set`. PCIe, remoteproc/SMP2P, PDC, relojes y Dell EC requieren pruebas de recuperación que aún no tenemos.

Habíamos comenzado a construir una pila derivada de un árbol Ubuntu generic. Eso duplicaría mantenimiento del kernel especializado que ya realiza Ubuntu Concept y puede provocar divergencias de ABI, DTB o firmware.

## Decisión

1. **Canonical/Ubuntu Concept: autoridad de empaquetado y kernel base.** Fijar `resolute-x1e` en el repositorio oficial de Launchpad para estudiar y, solo tras identificar qué fuente produce el paquete exacto, utilizar el flujo `debian.qcom-x1e/config/annotations` y sus herramientas de paquete. **La identidad del commit fijado con el binario 7.3.0-31.31 todavía es desconocida**; no se debe afirmar equivalencia.
2. **Qualcomm/upstream Linux: autoridad para controladores SoC.** Conservar manifiesto por parche/revisión para pinctrl, PCIe, SMP2P/PAS, PDC, clock, UART, Bluetooth. `proposed`, `accepted`, `mainline` y `ubuntu_inclusion` nunca se equiparan; NO_GO si falta prueba de restauración.
3. **Dell Tributo: referencia de Device Tree y hardware específico.** Auditar sus parches frente al DTS del Ubuntu/Canonical exacto; portar solo diferencias vigentes y licenciadas. La versión consultada probó `linux-next 2025-05-21`, documenta *suspend* y EC como WIP, **no hibernación**. El controlador EC v8 que funciona en el equipo sigue siendo un frente separado y no se sustituye por el material histórico de Tributo.
4. **Omarchy y x1e-nixos-config: referencias comparativas solamente.** Extraer ideas y reportes reproducibles; no introducir sus gestores de paquetes, scripts ni configuración como dependencia de Ubuntu.
5. **Un registro de versiones fijadas, no actualizaciones automáticas.** `docs/hibernate-upstream-projects.lock.json` contiene URL exacta, rama/ref, SHA Git, rol y tratamiento de cada proyecto. `scripts/verify-hibernate-upstream-lock.py` valida origen/identidad y opcionalmente consulta las referencias remotas sin descargar código. Si cambia alguna rama, detener y revisar el diff antes de actualizar el pin.

## Contratos de integración

| Límite | Entrada permitida | Salida verificable |
| --- | --- | --- |
| Canonical → XPS-HIB | commit fijado, fuente oficial, annotations, buildinfo ARM64 | candidato **offline**, versión/reproducibilidad y Kconfig auditada |
| Dell Tributo → XPS-HIB | DTS y notas verificadas, licencia validada | matriz de diferencias Dell, parches mínimos, revisión EC/SCMI |
| Qualcomm → XPS-HIB | series primarias con versiones y commits verificados | manifiesto, gates de restauración y pruebas de aplicación/compilación |
| Omarchy/NixOS → XPS-HIB | evidencia externa atribuida | recomendaciones comparativas, **sin importar código** |
| XPS-HIB → host XPS | **nada durante H1–H3** | informes y artefactos en `.local`, sin instalación |

La resolución remota de un SHA prueba solo identidad de la referencia **en la fecha de consulta**. No valida seguridad, licencia, correspondencia con el paquete PPA, compilación, suspend/resume ni hibernación.

## Condiciones obligatorias

- No publicar/copiar código de terceros sin revisar SPDX/licencia y atribución.
- No crear una segunda implementación del EC, PCIe o remoteproc cuando existe una corrección mantenida que pueda integrarse.
- Mantener el kernel operativo, `efi=noruntime`, GRUB, BIOS, Secure Boot, swap, initramfs y control térmico **sin cambios** hasta H4 con aprobación específica.
- PDC y clock restore se evalúan por separado, aunque PCIe y SMP2P estén corregidos.
- El gate de H4 exige respaldo restaurable, BitLocker disponible localmente, ruta de recuperación y prueba de retorno; el de H5 exige recuperación de la misma sesión con EC, ventilación, SCMI y dispositivos completos.

## Opciones rechazadas

- **Seguir creando un fork de Ubuntu generic:** costo de mantenimiento elevado, duplicación de parches y fuente distinta al kernel especializado.
- **Instalar inmediatamente el PPA experimental:** su Kconfig no permite hibernación y no contamos con prueba de rescate y restauración.
- **Migrar a NixOS/Omarchy para obtener hibernación:** no existe evidencia de restauración correcta en este Dell; cambiar distribución añade riesgos.
- **Aplicar todas las series upstream automáticamente:** las revisiones PCIe v2/v7 y remoteproc tienen bloqueos documentados; la aplicación textual no prueba compatibilidad semántica.

## Consecuencias y reversibilidad

Los PR de diagnóstico y el trabajo previo se conservan como evidencia y pruebas. Las correcciones duplicadas quedan en pausa; la integración se realizará a través de PRs pequeñas, branches normalizadas, revisión y CI. El primer hito es obtener pins auditables y contrato formal; el siguiente comparar **la fuente Canonical exacta** con la versión binaria del PPA y el DTS Dell, antes de compilar.

Rollback de este ADR/contrato: revertir commits Git. **No hay rollback de dispositivo porque esta decisión no modifica el host.**

## Evidencias

- Build Canonical: https://discourse.ubuntu.com/t/how-to-build-your-own-ubuntu-concept-x-elite-kernel/49941/
- Fuente oficial: https://git.launchpad.net/~ubuntu-concept/ubuntu/+source/linux/+git/resolute
- PPA: https://launchpad.net/~ubuntu-concept/+archive/ubuntu/x1e
- Dell: https://github.com/alexVinarskis/linux-x1e80100-dell-tributo
- Comparativos: https://github.com/omacom/omarchy y https://github.com/kuruczgy/x1e-nixos-config
- Contratos previos: `docs/hibernate-upstream-reuse-manifest.json`, `docs/hibernate-canonical-base.md` y `docs/hibernate-thermal-m3.md`.
