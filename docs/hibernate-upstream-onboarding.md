# XPS-HIB-01 — Reinicio operativo con proyectos upstream

**Fecha de baseline:** 2026-11-07. **Estado:** I0 registro y auditoría read-only; H1/H2 aún bloqueados. [ADR-0001](adr/ADR-0001-upstream-first-xps-hibernation.md) · [Plan ejecutable](superpowers/plans/2026-11-07-upstream-projects-integration.md).

## Proyectos integrados en el contrato

| Proyecto | Uso aprobado | Fuente fijada |
| --- | --- | --- |
| Ubuntu Concept / `linux-qcom-x1e` | **Base de kernel y empaquetado**, nunca instalación directa desde PPA | `resolute-x1e` @ `ba0042b4d0be94e27274fc336655f21fa0146027` |
| Dell Tributo XPS 9345 | Referencia de DTS y periféricos; comparar deltas con Canonical | `master` @ `2c5a57875dc4bc62e179a785e290a91bebfde2c6` |
| Omarchy | Referencia de experiencias de Snapdragon, no código de Ubuntu | `HEAD` @ `9044b7e8ea55ed6f443c14cbf93a2504aa248825` |
| NixOS `x1e-nixos-config` | Referencia de configuración declarativa, no sustituye el SO | `HEAD` @ `0b46072347252f83d40439f4a95d9d1fa37d6cf8` |

La identidad está en `docs/hibernate-upstream-projects.lock.json`, cuyos 4 refs remotos fueron comprobados con `git ls-remote` desde el XPS. La clasificación de *parches* (Qualcomm PDC/clocks, PCIe, SMP2P, pinctrl, UART, BT, Dell EC v8) permanece en `docs/hibernate-upstream-reuse-manifest.json`: **no es lo mismo fijar una referencia que verificar que su código se incluyó en el paquete Canonical**.

## Comandos de aceptación I0

```bash
python3 scripts/verify-hibernate-upstream-lock.py --json
python3 scripts/verify-hibernate-upstream-lock.py --check-remote --json
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

Salida verificada el 7 de noviembre: `LOCAL_LOCK_VALID` offline y `PIN_MATCH` contra los cuatro Git remotos. En ambos casos `install_authorized=false`, `release_equivalence_verified=false`. Si Git cambia una rama, el comando remoto retorna `DRIFT_DETECTED` y exige nueva investigación/PR; **no actualiza automáticamente los pins**. Ante red inaccesible: `REMOTE_UNVERIFIED`.

## Primer material externo inspeccionado en el XPS

Se creó, **fuera del índice Git**, una clonación superficial `.local/upstreams/dell-tributo`, comprobando que `git rev-parse HEAD` coincidiera con el SHA fijado. Se encontraron README, dos parches recientes de DTS/audio y un PDF de investigación EC. Su README describe la validación principal en `linux-next next-20250521`, suspensión funcional y EC WIP. No se encontró un archivo LICENSE/COPYING en ese snapshot superficial; **no se ha importado ni redistribuido su código**, ni se puede considerar su licencia autorizada por inferencia.

La fuente Ubuntu generic que usamos inicialmente ya contiene el DTS `arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts`. Ese hecho **no demuestra** que el árbol Canonical `resolute-x1e` precise los parches del repo Tributo, y tampoco que la fuente actual corresponda al paquete `7.3.0-31.31`. Primero se realizará un diff semántico sobre fuentes exactas.

Se intentó consultar solamente `debian.qcom-x1e/config/annotations` por HTTP usando el SHA de la rama Canonical; el endpoint devolvió 404. No se trató como un archivo ausente del repositorio ni se inventó su contenido. **Siguiente gate:** obtener el árbol fuente correcto mediante su Git remoto y su empaquetado oficial.

## Secuencia de arranque de la implementación

1. **I0 (ahora):** contrato, versiones Git, CI y revisión documental en `main`. Git remote sólo lectura.
2. **I1:** mapear `resolute-x1e` y la fuente exacta del paquete Canonical `linux-qcom-x1e 7.3.0-31.31`; revisar `debian.qcom-x1e/config/annotations` y Kconfig de HIBERNATION, SCMI, EC, PDC. Usar descarga de fuente controlada en `.local`, nunca `apt install` al host.
3. **I2:** comparar DTS Dell del mismo kernel y nuestros parches EC v8; registrar qué fue absorbido, qué sigue vigente y su licencia; preservar el módulo operativo.
4. **I3:** contrastar versiones upstream PDC, clocks, PCIe, remoteproc/SMP2P y pinctrl; si no hay upstream aplicable, se crea issue acotado, nunca parche ad hoc no probado.
5. **I4:** construir paquetes offline con la metodología de Canonical. Sin imagen con restauración y seguridad verificadas, no se avanza al arranque.
6. **I5:** solo con permiso específico, clave BitLocker y recuperación, probar arranque y tres restauraciones reales. Ninguna de las fases anteriores habilita hibernación.

## Qué sigue sin demostrarse

El kernel especializado publicado conserva `# CONFIG_HIBERNATION is not set`; ninguno de los pins demuestra una restauración de sesión. Los contratos PCIe, SMP2P, PDC y relojes siguen `NO_GO` o `UNKNOWN`. El kernel del XPS permanece `7.3.0-10-generic` sin `disk` en `/sys/power/state`. La operación I0 es revertible con Git, sin modificar firmware ni arranque.
