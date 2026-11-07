# Hibernation Kconfig audit

`scripts/audit-hibernate-config.py --baseline <config> --candidate <config> [--json]`

Read-only, stdlib-only. Compares two Kconfig files and reports only symbol **names**
(never values or paths). Baseline: `/boot/config-7.3.0-10-generic`; candidate:
`.local/kernel-source/candidate-config/.config`.

## Status categories and exit codes

| Status | Meaning | Exit |
| --- | --- | --- |
| `CLEAN` | Every changed symbol is in the expected set. If nothing changed, still `CLEAN` but `hibernation_evidence=false` and a note says there is no evidence of hibernation. | 0 |
| `UNRELATED_DRIFT` | At least one changed, added or removed symbol is outside the expected set. | 1 |
| `UNKNOWN` | Unreadable file, empty file, malformed line, duplicate symbol, or file over 16 MiB. | 2 |

Expected set: `CONFIG_HIBERNATION`, `CONFIG_HIBERNATE_CALLBACKS`, `CONFIG_HIBERNATION_SNAPSHOT_DEV`,
`CONFIG_HIBERNATION_COMP_LZO`, `CONFIG_HIBERNATION_COMP_LZ4`, `CONFIG_HIBERNATION_DEF_COMP`,
`CONFIG_PM_STD_PARTITION`, `CONFIG_ARCH_HIBERNATION_HEADER`.

## Parsing

Recognised: `CONFIG_X=value` and `# CONFIG_X is not set`. Free-form `#` comments and blank
lines are ignored. Any other line, including a `# CONFIG_...` comment in a different form, is
malformed and gives `UNKNOWN`. A symbol absent from one file differs from "is not set".

## JSON fields

`status`, `expected_changed`, `unrelated_changed`, `hibernation_evidence`, `errors`, `notes`, and
`flags` with the `rust`, `bpf`, `pahole`, `gcc` lists. The flag lists are subsets of
`unrelated_changed` chosen by name substring:
- rust: `RUST`, `BINDGEN`
- bpf: `BPF`, `BTF`
- pahole: `PAHOLE`
- gcc: `GCC`, `CC_VERSION`, `CC_IS_`, `CLANG`, `AS_VERSION`/`AS_IS_`, `LD_VERSION`/`LD_IS_`, `LLD_VERSION`, `TOOLS_SUPPORT`, `CC_HAS_`, `CC_CAN_`

## Limitations

- A `CLEAN` result means only that the configs differ in hibernation symbols. It does not show the kernel builds, boots, or resumes. The Qualcomm restore patches (P1–P5) are not covered.
- Name heuristics can miss or over-flag toolchain-derived symbols. Flagged names still count as `UNRELATED_DRIFT`.
- Symbol-level only: a changed value is reported by name, not by how large the change is.
- Dependencies are not evaluated, so a symbol can differ for a reason that has nothing to do with the toolchain.
- Error messages carry line numbers only, never paths or contents.

## Result record

**2026-11-07, ejecutado en XPS:** audit real sobre /boot/config-7.3.0-10-generic y .local/kernel-source/candidate-config/.config → **UNRELATED_DRIFT** (exit 1), **8** símbolos de hibernación modificados y **50** símbolos no relacionados; sin errores de análisis. Categorías identificadas: Rust/BINDGEN **26**, BPF/BTF **6**, pahole **2** y compiler/GCC **1** (categorías no necesariamente exhaustivas ni mutuamente excluyentes). La suite original y nuevas pruebas, incluyendo el caso real de símbolos CONFIG con minúsculas, produjo **27/27 PASS**. El resultado JSON sin rutas ni valores quedó en .local/hibernate-config-audit.json (ignorado por Git).

La primera ejecución arrojó UNKNOWN porque el analizador no admitía minúsculas válidas (p. ej. CONFIG_MT76x02_LIB); se añadió una prueba que falló antes de corregirlo y luego pasó. El código se verificó con unittest, py_compile y diff check. **Este resultado bloquea una compilación destinada a arrancar**; la configuración de fuente de Ubuntu sigue sin equivalencia a su paquete oficial.

La revisión de dependencias Qualcomm por un agente independiente en Paseo está documentada en [hibernate-patch-review-20261107.md](hibernate-patch-review-20261107.md).
