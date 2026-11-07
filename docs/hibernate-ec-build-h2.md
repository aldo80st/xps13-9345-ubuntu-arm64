# H2 isolated Dell EC object and Device Tree build

H2 runs only on the XPS with an H2 layer derived from the existing local ARM64
M2 image `xps-hibernate-kconfig:ubuntu26.10`. STOLAS02 was used for code, stdlib tests
and shell syntax checks only: no Ubuntu source download, image execution or
compilation. No object, DTB, kernel 7.3 target compatibility or runtime behavior
has been observed there.

Use the already patched Dell EC v8 source and already resolved M3 config from
[the integration procedure](thermal-hibernation-integration.md). This harness
does not apply patches or resolve Kconfig. It imports the M3 strict relevant-symbol
parser and SCMI requirements, and requires exactly `CONFIG_EC_DELL_XPS=m` and
`CONFIG_HIBERNATION=y`. Duplicate relevant symbols fail. Optional `--baseline`
checks the same SCMI settings and records its hash, without mounting it.

Run from this repository on the XPS as the normal user with its existing Docker
daemon. The live XPS daemon reports `name=apparmor`, `name=seccomp` and
`name=cgroupns`; it is rootful. H2 does not require a rootless daemon or any source
permission changes. The staged source may remain host-writable. Source and config
are mounted `:ro`; the harness never writes to them or runs host make. Keep input
files stable during execution. Selected file hashes are provenance, not a full
source-tree attestation. An in-tree `.config` is refused.

The user observed `modules_prepare` fail on the XPS with Ubuntu 7.3.0-10.10
and the M2 image: `scripts/gendwarfksyms/gendwarfksyms.h:6:10: fatal error:
dwarf.h: No such file or directory`. Ubuntu's `CONFIG_GENDWARFKSYMS` path needs
elfutils `libdw-dev`; libelf headers alone are insufficient. Build the separate
H2 layer on the XPS, with package network access during image creation only:

```bash
docker build --pull=false -f container/Dockerfile.hibernate-ec-build-h2 \
  -t xps-hibernate-ec-build-h2:ubuntu26.10 container/
```

This installs `libdw-dev` inside the new image, checks both DWARF headers and
linking against libdw/libelf, and records the updated package manifest. It does
not rebuild, retag or change the existing M2 image. No host package installation
is needed. This image layer has not been built on STOLAS02.

XPS acceptance command (the output must not already exist):

```bash
scripts/hibernate-ec-build-h2.sh \
  --source "$PWD/.local/m3-ec-source" \
  --config "$PWD/.local/m3-config/.config" \
  --output "$PWD/.local/h2-ec-build" \
  --image xps-hibernate-ec-build-h2:ubuntu26.10 \
  --baseline /boot/config-7.3.0-10-generic
```

Source and config mount read-only, only the new repository `.local` output mounts
read-write at `/out` from `OUTPUT/build`. The outer output and build subdirectory
are private (0700); the container uses umask 022. With the existing XPS daemon,
`--user` uses the host caller's UID:GID and can write the caller-owned output.
The fixed Docker invocation requires no network, a read-only root filesystem,
all capabilities dropped, no new privileges, 256 processes, 2 GiB memory with no
additional swap allowance, and a 256 MiB temporary filesystem. Builds use `-j1`
for the approximately 3.7 GiB host. Unsupported security/resource options cause
Docker to fail; the harness has no fallback that omits these flags. The image must
already exist locally; the harness resolves and executes its image ID, never pulls.

The fixed commands use `make -C /src O=/out ARCH=arm64`,
`CROSS_COMPILE=aarch64-linux-gnu-`, `CC=aarch64-linux-gnu-gcc`, `HOSTCC=gcc`,
and the image's Rust/bindgen environment. The sequential targets are:

1. `modules_prepare`
2. `drivers/platform/arm64/dell-xps-ec.o`
3. `qcom/x1e80100-dell-xps13-9345.dtb`

The third target is the expected top-level arm64 Kbuild target; its resulting file
is `build/arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dtb` under the output.
The user reports a successful separate XPS spike on Ubuntu 7.3.0-10.10,
building the EC `.o` and Dell DTB with a `libdw-dev` image and `-j2`. This supports
the chosen targets; it does not certify execution of this final harness. H2
retains the more conservative `-j1`. There is no
fallback to a full kernel build. `KCONFIG_NOSILENTUPDATE=1` prevents silent
configuration updates, and the staged config is compared byte for byte after
preparation and after the build. If synchronization is required, stop and use the
existing M2/M3 config workflow separately.

The existing Dockerfile calls itself a Kconfig image. It includes GCC, cross GCC,
binutils, make, bc, bison, flex, Perl, Python, libelf/libssl development headers,
Rust/bindgen, LLVM and pahole. It does **not explicitly install** cross-binutils
or all tools that arbitrary kernel build paths might need (for example cpio or
rsync). Cross-binutils may arrive through package dependencies; the harness
checks `aarch64-linux-gnu-ld` and `aarch64-linux-gnu-as`. It records tool versions
and the image package manifest, without duplicating the M2 version gate. This
is not evidence that the image can compile these targets. Missing tools or build
failures stop the run; leave image integration and actual compilation to the XPS
integrator. The H2 layer adds the observed missing elfutils dependency; the M2
Dockerfile remains unchanged.

Inspect `make.log` and `manifest.txt` in the output, plus `build/versions.txt`,
`build/.config`, `build/artifacts.sha256` and the object/DTB under `build/`. Exit 0 requires nonempty object and DTB plus
unchanged config; it proves only these limited build steps completed. Preserve
failed output for diagnosis and select a new output directory for another run.
Exit codes: 2 usage; 3 unsafe input/path/config; 4 Docker/image unavailable;
6 container failure, changed input/config or missing artifacts. A started manifest
and container exit code remain available after container failure.

An `.o` is not a `.ko`. `modules_prepare` does not generate the complete
`Module.symvers` needed for module versioning. H2 does not link a loadable module,
build a bootable kernel, check DT binding schemas, or establish EC firmware/PM
compatibility. Run the existing M3 static gate separately for patch provenance
and EC wiring. Successful compilation does not clear Qualcomm hibernation gates.

Nothing copies into host `/boot` or `/lib/modules`; no installation, depmod,
service changes, dracut, EFI changes or reboot occurs. Existing experimental EC,
SCMI cpufreq and governor settings remain as they were. Hibernation, fan/sensor
recovery and cpufreq behavior still require separately authorized runtime work.

Local verification (no real Docker):

```bash
bash -n scripts/hibernate-ec-build-h2.sh
python3 -I -m unittest discover -s tests -p 'test_*.py' -q
```

## Evidencia en el XPS — 2026-11-07

El integrador ejecutó **el propio harness versionado** (no una simulación) sobre la fuente Dell EC v8 en la copia experimental Ubuntu 7.3 y `CONFIG_EC_DELL_XPS=m` + `CONFIG_HIBERNATION=y` + SCMI conservado. Se construyó la imagen Docker H2 derivada del M2, añadiendo `libdw-dev` dentro de la imagen (el kernel requiere `dwarf.h` para `gendwarfksyms`).

El primer ensayo con imagen M2 había fallado por ausencia de `dwarf.h`; tras añadir esa dependencia, la compilación aislada generó el objeto del controlador y el Device Tree. Luego el **harness H2 oficial** generó los mismos SHA256 con salida 0:

- `drivers/platform/arm64/dell-xps-ec.o` — ELF ARM64 relocatable, SHA256 `de7be0b7041ff36a022a6c164da4252f78684d9847e7bbc2fb4a85f97cac11f0`.
- `arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dtb` — DTB v17 para Dell, SHA256 `ee3898e9f620863f9b3e3778782ca1c5880fd49373784d9dd8ffd4bff2b0a59d`.
- El manifiesto contiene `status=object-and-dtb-built; no runtime acceptance`; los artefactos permanecen bajo `.local` y **no** se agregan al repositorio ni se instalan.
- La imagen Docker H2 es local; se verifica por hash al ejecutar. La compilación tiene memoria limitada, contenedor sin red, sólo fuente y configuración read-only y directorio de salida en `.local`.
- Suite Python conjunta ejecutada en el XPS con los cambios H2: **118/118 PASS**; `bash -n` OK.
- El kernel del equipo continúa siendo `7.3.0-10-generic`. No se ejecutaron `make modules_install`, `make install`, `depmod`, `dracut`, edición de GRUB/EFI/BIOS/swap, suspensión ni hibernación.

**Importante:** el artefacto generado es un **.o**, NO un módulo `.ko` apto para instalar ni una imagen kernel. Faltan Module.symvers/vmlinux adecuados, verificación de ABI completa, integración de P1–P5 Qualcomm y pruebas de restauración de EC/SCMI en hardware. El milestone H2 continúa **parcial**, y los gates H3–H5 permanecen cerrados.
