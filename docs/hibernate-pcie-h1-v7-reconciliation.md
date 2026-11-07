# H1 PCIe reconciliation — P2 freeze v2 vs shutdown v7 (2026-11-07)

**Status: BLOCKED. Verdict: NO_GO.** No kernel was built, no patch applied to any tree, nothing installed. `docs/hibernate-qualcomm-h1.md` and its manifest are unchanged. Checker: `scripts/hibernate-pcie-h1-stack.py`; manifest: [hibernate-pcie-h1-stack.json](hibernate-pcie-h1-stack.json); tests: `tests/test_hibernate_pcie_h1_stack.py`.

## Sources (fetched as text only into ignored `.local/h1-pcie/`)
| Node | What | Source | Base |
| --- | --- | --- | --- |
| P2 | `PCI: qcom: Power the controller down when hibernating` **v2**, Birk Skyum, 2026-10-12 | [openwall](https://lists.openwall.net/linux-kernel/2026/10/12/1513), [lore](https://lore.kernel.org/all/179181074907.22199.10556821368232442334@pm.me/) | `591d89f23a7c` + 3 prerequisite patch-ids (= shutdown **v6**) |
| S7-1/2/3 | `PCI: qcom: Implement shutdown()…` **v7** 3 patches, Krishna Chundru, 2026-10-29 | [openwall](https://lists.openwall.net/linux-kernel/2026/10/29/328), [lore thread](https://lore.kernel.org/all/20261029-shutdown-v7-0-3fd7a76a6991@oss.qualcomm.com/) | `17bb0e2f6c80` |
| (ref) | shutdown **v6**, 2026-09-09 | [lore](https://lore.kernel.org/r/20260909-shutdown-v6-0-62b7bd123236@oss.qualcomm.com/) | `12f8e3e3eef4` |

Three different bases (v6 `12f8e3e3`, v7 `17bb0e2f`, P2 `591d89f2`); their mutual ancestry was not resolved (no git tree available). Follow-ups checked on lore (as of fetch): P2 has only a Sashiko "no issues" review, **no maintainer reply and no v3**; v7 has Sashiko (3 findings on patch 3), a kernel-test-robot warning, and Mani's 2026-11-05 "Please fix the build issue reported by kbot". **No v8 was found, but lore search (403) could not be queried — absence is not proof.**

Hashes (sha256 of the staged text files written by `stage`, reproduced twice identically): S7-1 `1f00fbe0…15b9`, S7-2 `4e9338fd…b48d`, S7-3 `a3fc237b…c830`, P2 `0009a576…e447d` (full values in the JSON). They fingerprint lore's rendering, not an upstream commit; no commit SHA exists for any of these.

## Dependency graph
`S7-1 ← S7-2 ← S7-3`; `P2 → {S7-2, S7-3}` (P2 uses the `force` argument from S7-2 and its hunk header is inside `qcom_pcie_shutdown()` from S7-3). P2 declares `built_against_version: v6`, the stack provides v7 ⇒ `VERSION_MISMATCH` until `reconciliation.status=verified` with evidence.

## What actually changed v6 → v7 (diff of the extracted patches)
Correction to earlier notes: patch 1 (`d3cold_possible()` bus walk) is **not new in v7**; it is patch 1 of v6 too and is byte-identical modulo hunk offsets. The v7 changelog says only "rebased on pci". Real deltas:
- **S7-2 (semantic):** v7 keeps `|| pci->pp.suspend_poweroff` in the L2 condition (`!d3cold_possible && !force && !suspend_poweroff`); v6 had `!d3cold_possible && !force` because the v6 base lacked `suspend_poweroff`. Also v7 adds the **rcar-gen4** caller (v6 touched 9 files, v7 10).
- **S7-3:** context-only (`use_imsi_rx` line moved), otherwise identical.
So P2's freeze path (force = true) is unaffected by `suspend_poweroff`, but *poweroff_noirq* (force = false) now may also enter L2 via `suspend_poweroff`, a behavior P2's text does not account for (P2 says poweroff "keeps the D3cold check").

## DWC `force` call sites (S7-2, checker-enforced)
`dw_pcie_suspend_noirq(pci, bool force)`; every caller gets `false`: pci-imx6, pci-layerscape, pcie-eswin, pcie-nxp-s32g, **pcie-qcom** (suspend path), pcie-rcar-gen4, pcie-stm32, pcie-ultrarisc. S7-3 adds the only `true` (shutdown); P2 adds the second (`qcom_pcie_freeze_noirq`). The checker flags `MISSING_CALLSITE`/`UNEXPECTED_CALLSITE`/`CALLSITE_ARG` in the patch and `UNCOVERED_TREE_CALLER` for any `.c` under `drivers/` calling the function in a supplied `--source-root` but not converted (would break the build). **Ubuntu 7.3 tree was not scanned (not available, STOLAS02 4 GB) → `SOURCE_ROOT` unmet.** P2's pre-image line `dw_pcie_suspend_noirq(pcie->pci, false)` is textually produced by S7-2 (checked, `P2_PREIMAGE`); that is only textual.

## PME / MSI
S7-1 stops the bus walk at the first non-D3hot device so `pme_capable` (→ `skip_pwrctrl_off`, Vaux/wakeup) is computed for all devices; S7-2 still calls it unconditionally under `force`. P2 forces L2 + power-down regardless, so wake-capable devices at freeze are powered down (poweroff is deliberately kept non-forced). MSI: S7-3 frees the chained MSI IRQs (`dw_pcie_free_msi()`) at shutdown only; P2 does not touch MSI, relying on `dw_pcie_resume_noirq()` at thaw/restore. Open review finding: freeing the MSI domain while child mappings are live (Sashiko).

## NVMe / Wi-Fi
Proposer (Lenovo Yoga Slim 7x, X1E80100, kernel 7.2 + **v6** + P2): hibernate with real power-off resumed (one run), `pm_test=core`/`test_resume` ×2, both controllers go down at freeze and links return at thaw/restore, NVMe and Wi-Fi work. pcie4 (Wi-Fi) is not up in the image-loading kernel; reading its DBI regs in resume reset the machine — the bug P2 fixes. Caveats: ath12k unloaded and remoteprocs stopped for the test; with Wi-Fi in D0 the L2 wait **times out** (`LTSSM 0x11`) on pcie4; the kernel also had smp2p, newer pinctrl, an unposted GENI change, and a shutdown backport omitting the two global-IRQ lines. **None of this is Dell XPS 13 9345 evidence** (the failure depends on which controllers the image-loading kernel brings up, which is unestablished for Dell). v7 itself carries no hibernation testing at all.

## Error unwinding
Open items recorded as `known_defects` (all unresolved): (1) S7-3 reads uninitialised `pcie` on `firmware_managed` controllers (robot + Sashiko, maintainer asked for a fix 2026-11-05) — P2 depends on S7-3 context; (2) MSI domain freed early; (3) shutdown while already suspended touches unclocked DBI; (4) P2: on `dw_pcie_suspend_noirq()` failure `qcom_pcie_suspend()` returns early so freeze aborts with the link up — acceptable for freeze (hibernation aborts) but untested; the forced-L2 timeout path is only logged on Lenovo.

## GO / NO_GO conditions (checker implements; GO needs all)
1. manifest graph valid, https URLs, no cycle/dangling dependency;
2. all four patch files staged, subjects have declared versions (`WRONG_VERSION`), `sha256` present and matching (`NO_SHA256`/`SHA_MISMATCH`/`MISSING_PATCH`);
3. force signature, call-site map and P2 pre-image verified in the patches;
4. a Linux source root scanned: no uncovered caller;
5. `reconciliation.status == verified` with evidence (P2 re-posted or reviewed against v7, no `VERSION_MISMATCH`);
6. every `known_defects` entry resolved;
7. Dell XPS 9345 evidence (`machine` containing XPS and 9345, NVMe + Wi-Fi resume) — Lenovo results never satisfy it.

Current result with staged series: failures **none**; unmet: version mismatch (×2), source root, five defects, reconciliation, Dell evidence ⇒ **NO_GO**. Reproduce:
```
python3 -I scripts/hibernate-pcie-h1-stack.py stage --out .local/h1-pcie/stack
python3 -I scripts/hibernate-pcie-h1-stack.py check --series-dir .local/h1-pcie/stack
```
## Blockers / unknowns
No Ubuntu 7.3 source scanned; ancestry of the three bases unknown; whether P2 applies with `git am` on v7 is **untested** (no tree); mainline/stable inclusion unknown; no Dell testing. Authorized next step: scan `linux-source-7.3.0-10.10` on a capable host with `--source-root`, then a reviewed P2 rebase onto v7 (with the S7-3 uninitialised-pointer fix) and Dell hardware validation.

## Verificación adicional en el XPS real — 2026-11-07

El integrador repitió `stage` en un scratch `.local/pcie-v7-series/` sobre el XPS y confirmó byte por byte los mismos hashes de los cuatro archivos P2/S7-1/S7-2/S7-3 registrados arriba. Luego ejecutó:

```bash
python3 scripts/hibernate-pcie-h1-stack.py check \
  --series-dir "$PWD/.local/pcie-v7-series" \
  --source-root "<árbol Ubuntu 7.3.0-10.10 extraído del XPS>" \
  --json
```

Resultado **exit 1, `NO_GO` esperado**. `failures=[]`: se reconocieron hashes, revisiones y puntos de llamada de la serie; el árbol real de Ubuntu fue inspeccionado sin identificar un llamador DesignWare omitido. `unmet` conservó exactamente 9 motivos: dos incompatibilidades de versión P2(v6)/shutdown(v7), cinco defectos/observaciones de revisión sin resolver, falta de conciliación semántica verificable y ausencia de evidencia de Dell XPS 9345. La suite del worktree corrió con **141 tests, OK (1 skipped)**.

**Interpretación:** compatibilidad *estructural* del manifiesto con las fuentes examinadas, **no** aplicación exitosa de los parches ni garantía de comportamiento de NVMe/Wi-Fi al restaurar. No se ejecutaron `git am`, `patch` sobre las fuentes, `make`, `update-grub`, `dracut`, suspensión o hibernación desde esta tarea.
