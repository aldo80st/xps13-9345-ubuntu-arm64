# H1 PCIe — applicability harness and rebase plan (shutdown v7 + freeze v2 → Ubuntu 7.3.0-10.10)

**Status: NO_GO. Not ported.** No patch was applied to any real tree, nothing was built or installed. Issue #24 (H1).
Harness: `scripts/hibernate-pcie-h1-applicability.py`; tests: `tests/test_hibernate_pcie_h1_applicability.py` (picked up by `python3 -m unittest discover -s tests -p 'test_*.py'`).

## Why the earlier evidence was invalid
`git apply --check` executed inside an extracted, non-git tree does not validate against that tree and silently skipped patches. It is **never** evidence. The harness therefore *rejects* (exit 2): missing `--source-root`, a source that is not the top of a git work tree, an incomplete tree, a patch without `diff --git` headers / without hunks / with renames or new files, a missing staged patch, or a sha256 differing from `docs/hibernate-pcie-h1-stack.json`.

## What the harness does (read-only)
1. Validates inputs as above; records `git rev-parse HEAD`; flags `SOURCE_DIRTY` if touched files differ from HEAD.
2. Copies **only the files the series touches** into a temp scratch git repo (outside the source) and runs `git apply --check` / `git apply` there: *isolated* against pristine copies and *sequential* (S7-1 → S7-2 → S7-3 → P2); a failure marks later patches `BLOCKED_BY_<id>` rather than skipping them. No fuzz, no whitespace tolerance.
3. Per hunk, searches the exact preimage in the real file and reports `PREIMAGE_FOUND` (+offset) or `PREIMAGE_MISSING` with first mismatching expected/found line. It never rewrites or skips a hunk.
4. Static lint, e.g. `S7-3_UNINITIALISED_PCIE`.
5. Mutation guard: hash of touched files + `git status` before/after (`UNCHANGED` required).
6. The verdict is **always `NO_GO`**; exit code is never 0. Applicability is necessary, not sufficient: defects, P2-on-v7 reconciliation and Dell XPS 9345 evidence remain gated by `hibernate-pcie-h1-stack.py`.

```
python3 -I scripts/hibernate-pcie-h1-stack.py stage --out .local/h1-pcie/stack
python3 -I scripts/hibernate-pcie-h1-applicability.py \
  --source-root <git work tree of linux-source-7.3.0-10.10> --series-dir .local/h1-pcie/stack --json
```
The tree must be imported into git first (`git init && git add -A && git commit` on an XPS-class host; the 1.8 GB source is **not** fetched on STOLAS02). **This step requires XPS validation**: no kernel source exists on STOLAS02, so the harness has only been run against synthetic fixtures here.

## Recorded XPS scratch evidence (raw, 2026-11-07)
Isolated copy of the 10 target files, `patch --batch --forward --fuzz=0 -p1`, sequential. (This was run with `patch`, outside the new harness, on a scratch copy; paths omitted.)

| Step | Exit | Rejects |
| --- | --- | --- |
| S7-1 | 0 | – |
| S7-2 | 1 | `pcie-designware-host.c`, `pcie-rcar-gen4.c` |
| S7-3 | 1 | `pcie-qcom.c` (ECAM drvdata hunk) |
| P2 v2 (on the partially patched copy) | 0 | – (**series still INVALID**: prerequisites missing) |

## Exact preimage differences (from XPS inspection vs. upstream hunks)
- **S7-2 / designware-host.c**: Ubuntu 7.3 `dw_pcie_suspend_noirq()` has `bool pme_capable = false;` and an early `if (!pci_host_common_d3cold_possible(pci->pp.bridge, &pme_capable)) return 0;`. S7-2's preimage expects a `bool d3cold` variable, a separate assignment and `pci->pp.suspend_poweroff` — those do not exist in Ubuntu. A correct port must add `force` to the *existing* condition (`if (!force && !pci_host_common_d3cold_possible(...)) return 0;`) **and** decide, on review, that `suspend_poweroff` semantics (a v7 behaviour, see the reconciliation doc) are not available/needed here; the pme_capable computation must still run when `force` is set.
- **S7-2 / pcie-rcar-gen4.c**: Ubuntu's file has no `dw_pcie_suspend_noirq()` caller; the hunk must be **dropped as inapplicable (not skipped blindly)**, justified by the caller scan (`UNCOVERED_TREE_CALLER` check against the real tree).
- **S7-3 / pcie-qcom.c**: Ubuntu's ECAM host init ends with `return devm_add_action_or_reset(dev, qcom_pci_free_msi, pp);`; v7-3 expects `return 0` after its `platform_set_drvdata()` addition. The drvdata line has to be added before that return and the `qcom_pci_free_msi` devm action must be retained; interaction with `dw_pcie_free_msi()` at shutdown (double free?) needs review.
- **S7-3 defect, not a port issue**: `struct qcom_pcie *pcie;` is uninitialised on the `firmware_managed` branch yet `if (pcie)` is evaluated afterwards (robot + Sashiko, upstream-requested fix). **Must not be carried over or called secure**; the port needs an explicit fix.
- **P2 v2**: hunks sit inside `qcom_pcie_shutdown()` (S7-3) and use `force` (S7-2); it only applies after those. Recorded direct failures: two `pcie-qcom.c` hunks.

## Plan (all steps need XPS/Docker validation; none done)
1. Import the exact source in git on the XPS; run the harness; keep the JSON (no host paths in the public repo).
2. Hand-author the minimal semantic adaptations above as separate commits on a throwaway branch of that tree, one per patch, each re-verified with the harness (sequential `APPLIES`, mutation guard `UNCHANGED`), plus a full-tree grep for every `dw_pcie_suspend_noirq(` caller.
3. Fix the S7-3 uninitialised-pointer defect and review MSI double-free; re-evaluate P2 against the adapted v7 (reconciliation entry in the manifest only with evidence).
4. Build only in the isolated H2/H3 Docker image; Dell XPS 9345 NVMe+Wi-Fi resume evidence is required before any admission. Until then: **NO_GO**, manifest unchanged, no port candidate published.

## Verificación de integración en el XPS — 2026-11-07

El integrador extrajo **solo 11 archivos** afectados por S7-1/S7-2/S7-3/P2 de las fuentes Ubuntu `linux-source-7.3.0-10.10`, conservó bytes originales y los guardó en un repositorio Git efímero e ignorado bajo `.local`. Este repositorio mínimo representa únicamente los contextos de los parches, **no** un árbol de kernel completo ni una prueba de compilación.

Se ejecutó el validador versionado contra los cuatro parches de texto verificados previamente por SHA256:

```bash
python3 scripts/hibernate-pcie-h1-applicability.py \
  --source-root "$PWD/.local/ubuntu-pcie-minitree" \
  --series-dir "<carpeta local que contiene s7-1.patch, s7-2.patch, s7-3.patch y p2-v2.patch>" \
  --json
```

**Resultado real:** código de salida `1`; `verdict=NO_GO`, `applicability=NOT_APPLICABLE`, `mutation_guard=UNCHANGED`, cuatro razones de fallo. S7-1 es aplicable; S7-2 no aplica por los contextos de `pcie-designware-host.c` y `pcie-rcar-gen4.c`. Por política atómica, S7-3 y P2 quedan bloqueados al fallar S7-2: no se permite aplicar trozos parciales. Un `patch` secuencial anterior había dejado cambios parciales y luego permitido aplicar P2; **ese resultado NO es una pila admisible**.

La comprobación Git sobre el snapshot de 11 archivos terminó limpia; la SHA256 de `pcie-qcom.c` coincidió entre snapshot y fuente oficial. El script por tanto comprobó sin mutaciones, pero **no integra ni compila código**. H1 permanece `NO_GO` por el fallo de aplicación y por los riesgos v6/v7 y dispositivos que siguen sin resolver.
