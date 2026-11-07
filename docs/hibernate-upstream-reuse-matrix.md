# Hibernation upstream reuse review — 2026-11-07

**NO_GO.** Reuse upstream fixes and Canonical packaging; defer candidate admission.
This STOLAS02 review adds evidence and offline automation, not driver code or a
working Dell hibernation kernel. Machine-readable evidence:
[manifest](hibernate-upstream-reuse-manifest.json). Stable IDs below match it.

Read together with [H1](hibernate-qualcomm-h1.md),
[PCIe reconciliation](hibernate-pcie-h1-v7-reconciliation.md),
[remoteproc lifecycle](hibernate-remoteproc-h1.md) and
[epic tracking](hibernate-epic-tracking.md). Their gates remain in force.

“Proposed” means a published patch, including RFC; “accepted” requires an explicit
maintainer application; “mainline” requires verified integration/ancestry;
“Ubuntu inclusion” requires the exact package source or semantic equivalent.
These are separate evidence axes. **Unknown does not mean absent or rejected.**
A patch's base-commit is not its integration commit. This manifest deliberately
records no integration SHAs. H1's pinctrl SHA remains a maintainer-reported tree
commit, not independently verified mainline ancestry.

| Stable component ID | Publication / acceptance | Mainline / exact PPA inclusion | Reuse decision and evidence |
| --- | --- | --- | --- |
| `pdc_restore` | Proposed v1, Oct 26 / unknown | unknown / unknown | **Defer** integration; track upstream syscore IRQ restore. [Requested Patchew post](https://patchew.org/linux/20261026-b4-irqchip-qcom-pdc-restore-resume-v1-1-ed6cc37816b0@oss.qualcomm.com/), [matching author post](https://lists.openwall.net/linux-kernel/2026/10/26/2170). |
| `clock_restore` | Proposed RFC v1, Oct 28 / unknown | unknown / unknown | **Defer**; reuse reviewed upstream outcome, including provider wiring. [Cover](https://lists.openwall.net/linux-kernel/2026/10/28/880), [framework 1/3](https://lists.openwall.net/linux-kernel/2026/10/28/856), [qcom common 2/3](https://lists.openwall.net/linux-kernel/2026/10/28/861), [Glymur 3/3](https://lists.openwall.net/linux-kernel/2026/10/28/882). |
| `pcie_freeze` | Proposed v2 / unknown | unknown / unknown | **Defer**; reuse reviewed successor/rebase. [Oct 12 proposal](https://lists.openwall.net/linux-kernel/2026/10/12/1513) targets shutdown v6, not verified against v7. |
| `pcie_shutdown` | Proposed v7 / unknown | unknown / unknown | **Defer**; [Oct 29 series](https://lists.openwall.net/linux-kernel/2026/10/29/328) does not itself supply freeze behavior or close existing review defects. |
| `smp2p_restore` | Proposed / unknown | unknown / unknown | **Defer**; [Oct 9 proposal](https://lists.openwall.net/linux-kernel/2026/10/09/2521) resets shared-memory negotiation. Preserve lifecycle gate. |
| `remoteproc_lifecycle` | Solution unknown / unknown | unknown / unknown | **Defer**; the [SMP2P author's report](https://lists.openwall.net/linux-kernel/2026/10/09/2521) explicitly leaves running-at-image remotes unresolved. No verified upstream solution identified here. |
| `uart_restore` | Proposed v2 / unknown | unknown / unknown | **Defer** pending Dell console/UART mapping. [Oct 27 post](https://lists.openwall.net/linux-kernel/2026/10/27/2926), [author mirror](https://lkml.iu.edu/hypermail/linux/kernel/2610.3/07785.html): resets non-console engine setup; console case excluded. |
| `bluetooth_ibs` | Proposed v2 / unknown | unknown / unknown | **Defer**; reuse after locking and combined UART review. [Oct 14 post](https://lists.openwall.net/linux-kernel/2026/10/14/2305), [author mirror](https://lkml.iu.edu/hypermail/linux/kernel/2610.1/16019.html): Lenovo hibernation tested v1, OnePlus power cycling tested v2. |
| `pinctrl_restore` | Proposed v4 / **accepted** | unknown / unknown | **Reuse after review**; [v4](https://lists.openwall.net/linux-kernel/2026/10/21/2649), [maintainer application Oct 28](https://lists.openwall.net/linux-kernel/2026/10/28/768). Confirm exact-base inclusion and Dell ownership first. |
| `dell_ec` | Proposed v8 / unknown | unknown / unknown | **Reuse after review** the existing binding/driver/DTS artifacts. [Author's v8 cover](https://lkml.iu.edu/hypermail/linux/kernel/2610.3/01866.html); preserve [M3 integration](thermal-hibernation-integration.md), ADC dependency and SCMI/thermal checks. Local build success does not establish hibernation recovery. |
| `ubuntu_concept` | Packaging exists; patch publication N/A / acceptance unknown | upstream ancestry N/A to packaging; fixes unknown / exact fix inventory unknown | **Reuse packaging** from Canonical's [build guide](https://discourse.ubuntu.com/t/how-to-build-your-own-ubuntu-concept-x-elite-kernel/49941), [FAQ](https://discourse.ubuntu.com/t/faq-ubuntu-25-04-25-10-on-snapdragon-x-elite/61016) and [package pool](https://ppa.launchpad.net/ubuntu-concept/x1e/ubuntu/pool/main/l/linux-qcom-x1e/). Availability is not feature qualification. |

## PDC and clock gates

The PDC author reports that a restore kernel can leave IRQ trigger/enables from
its own configuration. Saving/restoring TLMM alone does not repair PDC state.
The proposal saves IRQ_CFG/enable banks through syscore and preserves latched
GPIO status in secondary mode; it includes an X1E enable-write quirk. Its reported
failure is a **Glymur CRD EC interrupt storm**, not an XPS reproduction.
[Primary proposal](https://lists.openwall.net/linux-kernel/2026/10/26/2170).

`pdc_restore` remains unresolved until a reviewer records current upstream
acceptance/integration evidence, exact Ubuntu source equivalence or reviewed
backport, Dell PDC mode/IRQ ownership and syscore ordering, and suspend/restore
IRQ regression evidence. Do not write a parallel PDC fix or assume pinctrl closes
this gate.

The clock RFC proposes replaying cached provider state and adding Qualcomm
restore handling. Its cover identifies uncertain architecture, disabled-source
clock programming, devres coverage and missing phase/duty restoration. The example
provider wiring is **dispcc-glymur**, so it establishes no X1E/Dell provider
coverage. Reuse the eventual reviewed framework/provider solution; copying only
the helper cannot qualify Dell clocks. [RFC cover](https://lists.openwall.net/linux-kernel/2026/10/28/880),
[common callback](https://lists.openwall.net/linux-kernel/2026/10/28/861).

`clock_restore` stays unresolved pending the reviewed series outcome, full
provider coverage for Dell, exact source/package identity and PM/domain ordering,
plus evidence for display and other consumer recovery. Neither a common API nor
Glymur/Lenovo success supplies these proofs.

## Canonical packaging and XPS evidence boundary

**User-supplied XPS-verified observation:** PPA `linux-qcom-x1e` **7.3.0-31** has
`# CONFIG_HIBERNATION is not set`. This was not remeasured on STOLAS02 and is
recorded with that provenance in the manifest. It is a hard blocker, separate
from unknown patch inclusion. The earlier Ubuntu source audit used
`linux-source-7.3.0=7.3.0-10.10`; its absence observations cannot be transferred
to this different PPA package. No full source/package inventory was downloaded.

Canonical's guide supplies the packaging workflow; its FAQ describes a WIP
Qualcomm kernel with experimental additions. Follow that source/configuration,
toolchain and packaging baseline for any future reviewed build; retain ABI,
modules, DT, initramfs and distribution features. An upstream commit or config
flip alone proves none of these. [Build workflow](https://discourse.ubuntu.com/t/how-to-build-your-own-ubuntu-concept-x-elite-kernel/49941),
[Concept scope](https://discourse.ubuntu.com/t/faq-ubuntu-25-04-25-10-on-snapdragon-x-elite/61016).

PCIe v2/v7 reconciliation, its recorded defects, PAS lifecycle, EC thermal/SCMI
compatibility and separately authorized Dell runtime qualification remain
independent blockers. Lenovo manual remote stop/start and ath12k workarounds are
reported experimental constraints, not a reusable Dell lifecycle solution.
No claim of Dell real power-off session restore follows from any row.

## Verification scope and offline contract

Online checks on 2026-11-07 fetched PCIe v2/v7, SMP2P, pinctrl application, clock
cover and UART/EC indexed author posts. PDC publication was verified through its
indexed primary-author mirror with the exact requested Message-ID; Patchew was
inaccessible. Clock 1/3 and 2/3 were available through indexed primary content;
3/3 was identified by cover/day index but direct fetch failed. Bluetooth's author
mirror was fetched after Openwall timed out. Targeted acceptance searches for
PDC/clock/EC supplied no integration proof. Search absence is not proof of absence.

The attempted [mainline PDC history](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/log/drivers/irqchip/qcom-pdc.c)
and [Launchpad package listing](https://launchpad.net/~ubuntu-concept/+archive/ubuntu/x1e/+packages)
were inaccessible. No mainline ancestry or exact PPA source comparison was
completed for any fix. Mainline and Ubuntu-inclusion fields therefore stay
**unknown**, including accepted pinctrl. These are bounded observations, not a
claim to have exhaustively searched newer revisions or maintainer trees.

```sh
python3 -I scripts/validate-hibernate-upstream-reuse.py --json
python3 -m unittest discover -s tests -p test_hibernate_upstream_reuse.py -q
python3 -m unittest discover -s tests -q
```

The stdlib validator reads only the selected manifest (`--manifest PATH`, default
relative to its script), never fetches or executes evidence. Valid blocked input
returns `NO_GO`, `admitted: false`, empty `errors`, seven stable blockers and exit
**1**. Invalid/missing JSON, duplicate keys, component loss/duplication, invalid
URLs, altered gate/config/status claims and unsupported fields also deny.
The version-1 snapshot is locked: future evidence requires a reviewed contract
update, not editing “unresolved” to “resolved”. The tool cannot certify source
correctness, cryptographically authenticate citations, or authorize builds/boots.

TDD RED was observed before implementation (8 failures, 2 errors across five
methods); GREEN validates default denial, hostile/malformed mutations, missing
input, read-only bytes and working-directory independence. Tests concern this
review contract only. No existing file, driver, host configuration, swap, BIOS,
GRUB or installed kernel was changed; no push or merge was performed.

Final verification on 2026-11-07: **178 tests ran, OK (2 skipped)**; the five
focused methods passed. Default `--json` returned exit 1, `NO_GO`, seven blockers
and zero validation errors. `git diff --check` passed.
