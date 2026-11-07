# M2 — reproducible Kconfig toolchain harness

Purpose: run `make olddefconfig` for Ubuntu `7.3.0-10.10` arm64 in a sandboxed container so the
candidate config differs from the distro config only by intended hibernation options. This
resolves Kconfig dependencies only. It is **not proof** of hibernation, boot, suspend or resume.
Claude Code, orquestado por Paseo en STOLAS02, desarrolló el ejecutor y sus pruebas sin compilar el kernel. La imagen Docker y `olddefconfig` **sí fueron ejecutados y verificados en el XPS** el 7 de noviembre de 2026; los resultados constan más abajo.

## Commands (run on the XPS, arm64, as a normal user)

```bash
# 1. Build the image (apt runs inside the image only; fails closed on any version mismatch)
docker build -f container/Dockerfile.hibernate-kconfig -t xps-hibernate-kconfig:ubuntu26.10 container/

# 2. Run (all inputs absolute; output must live under a .local directory)
scripts/hibernate-m2-config.sh \
  --source   "$PWD/.local/kernel-source/tree/linux-source-7.3.0" \
  --baseline /boot/config-7.3.0-10-generic \
  --output   "$PWD/.local/m2-out" \
  --image    xps-hibernate-kconfig:ubuntu26.10 \
  --audit    "$PWD/scripts/audit-hibernate-config.py"
```

`--audit` se invoca como `python3 -I SCRIPT --baseline FILE --candidate FILE --json`, **verificado en el XPS** (salida 0 = CLEAN, 1 = drift). El JSON queda en `audit.json`; cualquier resultado no-CLEAN devuelve salida 7. Para aceptación M2, `--audit` es obligatorio.

Before `olddefconfig` the container edits only its staging copy `/out/.config`, replacing exactly one
`# CONFIG_HIBERNATION is not set` with `CONFIG_HIBERNATION=y`; zero or multiple matches (or an
existing `CONFIG_HIBERNATION=` line) abort with exit 5. The baseline and source are never modified.
Without `--audit`, drift is explicitly reported as not evaluated.

## Required toolchain (checked in image build and again at run time)

| Tool | Required |
| --- | --- |
| `aarch64-linux-gnu-gcc` | 15.3 (passed as `CC=`, to preserve CONFIG_CC_VERSION_TEXT) |
| rustc | 1.97.1 |
| `RUST_LIB_SRC` | `/usr/src/rustc-1.97.1/library` (must contain `core/`) |
| bindgen | 0.72.1 (`BINDGEN=`) |
| clang / LLVM | 22.x; `LIBCLANG_PATH=/usr/lib/llvm-22/lib` |
| pahole (package `pahole`) | 1.31 |
| bison, flex, m4, libssl-dev, libelf-dev | present |

Any missing tool or mismatch → exit 5, no `.config` accepted. Rust/pahole absence is what
previously changed 50 unrelated + 8 hibernation symbols; do not bypass.

## Sandbox

`docker run --rm --pull never --network none --cap-drop ALL --security-opt no-new-privileges
--read-only` with tmpfs `/tmp`, caller uid:gid, pids/memory limits. Mounts: source `:ro`,
baseline `:ro`, output `:rw` (only `.local/...`). No `/boot`, `/etc`, docker socket or sudo.
The baseline is hashed before and after; the copy `make` edits lives in the output dir.
Source must not contain an in-tree `.config`.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | olddefconfig finished (and audit clean if given) |
| 2 | usage / missing or unknown flags (`--help` exits 0) |
| 3 | unsafe/nonexistent path, output not under `.local`, bad image name, audit script missing |
| 4 | docker missing or image not present locally |
| 5 | toolchain missing or wrong version in container |
| 6 | `olddefconfig` failed (tail of `make.log` printed) |
| 7 | audit nonzero (drift or parse error); success requires 0 unrelated symbols, 8 expected |
| 8 | other container failure or baseline modified |

## Manifest

Inputs: source tree (ro), baseline config (ro), image tag, optional audit script.
Outputs in `--output`: `.config` (candidate), `versions.txt`, `make.log`, `manifest.txt`
(paths, sha256 of baseline/candidate, image id), `audit.json` (if audited), plus Kbuild files.
Image contains `/etc/hibernate-kconfig-packages.txt` (installed package list).

## Cleanup

`rm -rf .local/m2-out`; `docker rmi xps-hibernate-kconfig:ubuntu26.10`. No host state changed.

## Caveats

- Los paquetes `pahole`, `rustc-1.97`, `rust-1.97-src`, `bindgen`, `clang-22` y el directorio `RUST_LIB_SRC` se verificaron al construir la imagen oficial sobre el XPS. La prueba real de Kconfig también confirmó disponibilidad de Rust, BPF/BTF y demás funciones de su configuración original.
- Equivalence of config ≠ working hibernation; M3 stays NO-GO per the patch review.
- Tests: `python3 -I -m unittest discover -s tests` (static, no docker).

## M2 — evidencia final verificada en el XPS (2026-11-07)

- **Imagen Docker reproducible**: `xps-hibernate-kconfig:ubuntu26.10`; arquitectura `arm64`; ID local `sha256:40a9f32bb94e0b5f88303de9290b0aa80bee9a6446a01c9d18b83c18cf9cf62f`. Dockerfile parte de `ubuntu:26.10` y fija/verifica versiones durante build. El digest local identifica la imagen construida, **no** es una firma de confianza de Ubuntu ni un pin de la imagen base.
- Herramientas realmente verificadas: `aarch64-linux-gnu-gcc 15.3.0`, `rustc 1.97.1`, `bindgen 0.72.1`, `clang 22.1.8`, `pahole 1.31`, `bison 3.8.2`, `flex 2.6.4`, `m4 1.4.21`.
- `olddefconfig` generó `.local/m2-out/.config` sin sustituir ningún kernel ni afectar /boot; `hibernate-m2-config.sh` devolvió **exit 0**. La copia temporal activa `CONFIG_HIBERNATION=y`, no el archivo de entrada.
- Auditor final: `CLEAN`; **8 cambios directos** en opciones de hibernación, **2 dependencias LZ4** determinadas por Kconfig y **0 cambios no relacionados**; 0 errores de análisis. La clasificación dependiente está sujeta a transición `m → y` y cadena `CONFIG_HIBERNATION → CONFIG_CRYPTO_LZ4 → CONFIG_LZ4_COMPRESS`.
- Procedencia de la excepción: `kernel/power/Kconfig` contiene `select CRYPTO_LZ4` bajo `HIBERNATION`; `crypto/Kconfig` contiene `select LZ4_COMPRESS` bajo `CRYPTO_LZ4`. Los dos eran módulos (`m`) en Ubuntu oficial y Kconfig los habilitó integrados (`y`). **No es desviación accidental ni funcionalidad perdida**.
- El auditor pasó una prueba nueva RED→GREEN para estas dependencias y 3 pruebas negativas que conservan `UNRELATED_DRIFT` cuando no existe selección legítima.
- Suite conjunta en XPS: `python3 -m unittest discover -s tests -p 'test_*hibernate*.py' -q` → **66/66 OK**.
- SHA256 de config de base oficial: `d90aa49e6a3079eeedf97920c1b567443b5b4473e031b78fb9cf4aff8ed40f0c`. SHA256 de la config generada: `96cc0f77aa601b974346bbeeac15d5719946c086009780be78d9bb499d3b78ca`.
- Logs y archivos resultantes bajo `.local/m2-out/` (no versionados). No se ejecutó `make Image`, `dpkg` de kernel, cambio de EFI/GRUB/BIOS, suspensión ni hibernación.
- **M2 logrado a nivel Kconfig, no a nivel de sistema booteable.** M3 permanece bloqueado hasta resolver integridad de pila Qualcomm y precondiciones de recuperación Dell/BitLocker.
