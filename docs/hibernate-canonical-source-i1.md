# I1 — Fuente oficial Canonical qcom-x1e 7.3.0-31.31, auditada

**Fecha:** 2026-11-07. **Estado:** prueba estática de integridad superada; **hibernación NO_GO**, sin instalación o boot. [ADR-0001](adr/ADR-0001-upstream-first-xps-hibernation.md) · [Plan de integración](superpowers/plans/2026-11-07-upstream-projects-integration.md).

## Fuente reproducible, no una rama mutable

Se inspeccionó el paquete fuente que Ubuntu Concept publicó para `linux-qcom-x1e 7.3.0-31.31`:

- [.dsc oficial](https://ppa.launchpadcontent.net/ubuntu-concept/x1e/ubuntu/pool/main/l/linux-qcom-x1e/linux-qcom-x1e_7.3.0-31.31.dsc), SHA256 `db38bee3a6cb6dbaed0e7ac13c68ab1261e380bb2f9ce4e54caa299fdda6cc21`. Declara `Source: linux-qcom-x1e`, `Version: 7.3.0-31.31` y lista artefactos para ARM64.
- [Archivo fuente exacto](https://ppa.launchpadcontent.net/ubuntu-concept/x1e/ubuntu/pool/main/l/linux-qcom-x1e/linux-qcom-x1e_7.3.0-31.31.tar.gz), **273 721 575 bytes**, SHA256 `41e6c1e13aa14a6c4bc66f8e8faa33d6364eb309fa8f8c726a1e0ebee84a4051`. Descargado en el XPS y comparado contra el hash de la declaración `.dsc`; **PASS**.
- [Buildinfo ARM64](https://ppa.launchpadcontent.net/ubuntu-concept/x1e/ubuntu/pool/main/l/linux-qcom-x1e/linux-buildinfo-7.3.0-31-qcom-x1e_7.3.0-31.31_arm64.deb), SHA256 `120e3bd802af4f4c7a307b46b203662958d9c093a797e1e5cbd58dd39603136c`. Ya comparado con `/boot/config-7.3.0-10-generic`.
- Changelog **dentro del tar**: `linux-qcom-x1e (7.3.0-31.31) stonking`, fecha 26 de octubre de 2026; describe un cambio Qualcomm ASoC. El changelog **no es una prueba de que se compiló byte a byte ese árbol**, pero vincula las versiones publicadas.
- PGP: la firma de `.dsc` fue validada criptográficamente con la clave pública `9B693D7440802E8A6FF803DE13498F032CCFE9DA`, publicada para Tobias Heider, mediante un keyring temporal en `.local`: `GOODSIG`, `VALIDSIG`. **Confianza de identidad GPG: `TRUST_UNDEFINED`** al no disponer de una cadena de confianza previamente establecida; no equivale a autenticación completa de firma de distribución. El validador automatizado comprueba hashes y NO realiza GPG.
- Git de Canonical: rama `resolute-x1e` estaba en `ba0042b4d0be94e27274fc336655f21fa0146027`; se consultaron los tags remotos y **no se identificó uno para `Ubuntu-qcom-x1e-7.3.0-31.31`**. No afirmar que el HEAD corresponda al paquete. Este SHA pertenece al registro upstream **de referencias**, no al identificador de fuente binaria.

Por tanto, el archivo `.tar.gz` comprobado desde el repositorio publicado es nuestro **material de referencia exacto para I1**, no la cabeza de una rama. El buildinfo comparte versión y política Kconfig; la reproducibilidad binaria está **por demostrar**.

## Anotaciones y drivers del archivo exacto

La carpeta `debian.qcom-x1e/config/annotations` está presente, con `# FLAVOUR: arm64-qcom-x1e`. El validador comprueba su política `arm64` contra la Kconfig extraída del buildinfo publicado.

| Símbolo | Annotations exactas | Buildinfo exacto |
| --- | --- | --- |
| `CONFIG_HIBERNATION` | **n** | **n** |
| `CONFIG_ARM_SCMI_CPUFREQ` | m | m |
| `CONFIG_PCIE_QCOM` | y | y |
| `CONFIG_QCOM_PDC` | y | y |
| `CONFIG_QCOM_SMP2P` | m | m |

El tar contiene el DTS `x1e80100-dell-xps13-9345.dts`, controladores `qcom-pdc.c`, `pcie-qcom.c`, `qcom_q6v5_pas.c`, `smp2p.c`, `gcc-x1e80100.c`. **No contiene `drivers/platform/arm64/dell-xps-ec.c`**. Su incorporación posterior será específica del equipo y exigirá revisión ABI/térmica.

Comparación hash SHA256: estos **seis** archivos (DTS + PDC + PCIe + PAS + SMP2P + GCC relojes) son idénticos byte por byte a la fuente Ubuntu generic 7.3.0 ya utilizada para el laboratorio; **no se verificó equivalencia de todo el kernel**. En particular, cambiar de empaquetado no aporta automáticamente parches de recuperación para esos seis archivos. Se mantienen los gates `NO_GO` existentes de PCIe, PAS/SMP2P y PDC/clocks.

## Dell Tributo: comparación sin importar código

Repositorio fijado `alexVinarskis/linux-x1e80100-dell-tributo` `2c5a57875dc4bc62e179a785e290a91bebfde2c6`, clonado superficialmente y solo bajo `.local`. README documenta revisión `linux-next next-20250521`, *suspend* probado, EC WIP y un PDF de investigación, **no hibernación**. El snapshot no presenta licencia raíz LICENSE/COPYING identificable.

Las series DTS `0009` (left/right speakers y USB) y `0010` (micrófonos) se probaron mediante `patch --dry-run --batch --fuzz=0` en una **copia** del DTS exacto de Canonical: ambas devolvieron errores tanto en aplicación como en reversión. Esto **no demuestra** que los cambios estén incluidos o ausentes; el contexto ha divergido desde su base histórica. Los SHA de DTS original y copia coincidieron al finalizar. **No se importó código externo.**

## Comando reproducible

Desde la raíz del repositorio (todos los archivos temporales bajo `.local` ignorado):

```bash
mkdir -p .local/source-audit
cd .local/source-audit
curl -fLsS https://ppa.launchpadcontent.net/ubuntu-concept/x1e/ubuntu/pool/main/l/linux-qcom-x1e/linux-qcom-x1e_7.3.0-31.31.dsc -o linux-qcom-x1e_7.3.0-31.31.dsc
curl -fLsS https://ppa.launchpadcontent.net/ubuntu-concept/x1e/ubuntu/pool/main/l/linux-qcom-x1e/linux-qcom-x1e_7.3.0-31.31.tar.gz -o linux-qcom-x1e_7.3.0-31.31.tar.gz
echo '41e6c1e13aa14a6c4bc66f8e8faa33d6364eb309fa8f8c726a1e0ebee84a4051  linux-qcom-x1e_7.3.0-31.31.tar.gz' | sha256sum -c -
cd ../..
python3 scripts/audit-canonical-source-i1.py \
  --dsc .local/source-audit/linux-qcom-x1e_7.3.0-31.31.dsc \
  --tarball .local/source-audit/linux-qcom-x1e_7.3.0-31.31.tar.gz \
  --buildinfo-config .local/source-audit/buildinfo/usr/lib/linux/7.3.0-31-qcom-x1e/config --json
```

`--buildinfo-config` apunta al `config` **previamente extraído**, mediante `dpkg-deb -x` desde el archivo `linux-buildinfo` ARM64 fijado y verificado por SHA; el validador nunca instala paquetes. Resultado observado con el buildinfo real: salida **1**, `NO_GO`, `source_sha256_verified=true`, `dell_ec_present=false`, `install_authorized=false`. Bloqueos: HIBERNATION_NOT_ENABLED, HARDWARE_RESTORE_UNVERIFIED, GIT_COMMIT_EQUIVALENCE_UNVERIFIED y DELL_EC_NOT_IN_SOURCE.

**Seguridad:** no se extrajeron entradas del archivo automáticamente al ejecutar el validador; se leen solo 8 miembros de interés, sin ejecutar código ni escribir archivos. La comprobación de firma es una acción separada; el script NO marca `dsc_signature_verified=true` por sí mismo. El proceso no modifica kernel, firmware, initramfs, GRUB, BIOS, EC ni swap.

## Próximo trabajo

1. Registrar la relación canónica entre el origen fuente PPA `7.3.0-31.31` y su commit Git real, si Canonical expone un tag/metadata verificable; no inferirlo del HEAD.
2. Comparar DTS exacto y EC v8 con dependencias de `linux-qcom-x1e`, comprobar licencias de parches Dell antes de portar.
3. Auditar series upstream PDC/clocks/PCIe/PAS contra **esta fuente publicada**, no solo generic.
4. Preparar con annotations el siguiente candidato **offline**; compilación/packaging y restauración sin aprobación todavía NO_GO.

Rastreo: [Epic #21](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/21), [I1 fuente exacta](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/44), [H2 candidato offline](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/45).
