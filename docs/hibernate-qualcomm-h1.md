# H1 — Qualcomm patch-stack decision matrix (2026-11-07)

**Verdict: REVIEW_REQUIRED, never GO.** No working hibernation kernel exists or is implied. No Dell resume has been demonstrated. Machine-readable twin: [hibernate-qualcomm-manifest.json](hibernate-qualcomm-manifest.json), checked by `scripts/hibernate-qualcomm-h1.py --json`.

**Evidence date:** 2026-11-07. **Source tree:** Ubuntu `linux-source-7.3.0=7.3.0-10.10` as audited in [M1](hibernate-kernel-m1.md); H1 did **not** download or re-inspect it (4 GB host), so every `ubuntu_7_3_10_present` value is carried from M1 (absence of callbacks), not re-verified.

## Live upstream check (this session)
Fetched `lists.openwall.net` posts for P1, P2, P2a, P3 (succeeded). P4 and P5 were **not** re-fetched; their status is carried from [the patch review](hibernate-patch-review-20261107.md). git.kernel.org, lore and GitHub mirrors were not queried, so mainline ancestry is **UNKNOWN** for all groups. Search absence is not proof of non-integration.

Status vocabulary: proposed < accepted < mainline < ubuntu. Only "accepted" (P1) is observed; "mainline" and "ubuntu" are observed for none.

## Decision matrix
| ID | Patch | Source | Observed status | In Ubuntu 7.3.0-10.10 | Admission | Key blocker |
| --- | --- | --- | --- | --- | --- | --- |
| P1 | pinctrl qcom TLMM restore | [applied msg](https://lists.openwall.net/linux-kernel/2026/10/28/768), [v4](https://lists.openwall.net/linux-kernel/2026/10/21/2649) | **accepted** (brgl tree; message says "Applied, thanks!") | not present (M1) | REVIEW_ONLY | mainline/backport on exact base UNKNOWN; Dell DT pin ownership |
| P2 | PCIe qcom freeze power-down v2 | [post](https://lists.openwall.net/linux-kernel/2026/10/12/1513) | **proposed** | not present (M1) | BLOCKED | written on shutdown **v6**; tested on a v7.2 kernel with that series |
| P2a | PCIe qcom shutdown() v7 | [post](https://lists.openwall.net/linux-kernel/2026/10/29/328) | **proposed**; 3 patches, base `17bb0e2f6c80` per post | not present (M1) | BLOCKED | adds `force` arg touching other DWC drivers; caller audit needed |
| P3 | smp2p restart after restore | [post](https://lists.openwall.net/linux-kernel/2026/10/09/2521) | **proposed** (unversioned, no maintainer reply seen) | not present (M1) | BLOCKED | remoteproc lifecycle unresolved |
| P4 | GENI UART restore v2 | [post](https://lists.openwall.net/linux-kernel/2026/10/27/2926) | **proposed** (not re-fetched) | not present (M1) | REVIEW_ONLY | Dell UART/console mapping |
| P5 | hci_qca IBS reset v2 | [post](https://lists.openwall.net/linux-kernel/2026/10/14/2305) | **proposed** (not re-fetched) | old logic present (M1) | REVIEW_ONLY | v1 (not v2) was hibernation-tested; no Dell test |

## Hard rules
- **P2 + P2a:** P2 v2 targets shutdown v6; P2a is v7. v7 is a rebase that adds patches to `d3cold_possible()` and DWC `force`, but whether P2 applies and behaves correctly on v7 is **UNKNOWN** and must not be asserted without a full dependency review (force semantics, error unwinding, PME/MSI, suspend/poweroff). Both stay BLOCKED.
- **remoteproc:** P3 stays BLOCKED. The author states a remote running at image time stays "running" after resume and fails to stop (-22), and that this is open. Manual stop/start was used in testing. No lifecycle solution is accounted for.
- **SHA:** only P1 has a full commit SHA, `30d9a180c86e3cbd53efb7152e05cb059112f6eb`, taken from the maintainer's message (tree named only as `git.kernel.org/brgl/...`; not independently resolved on git.kernel.org). Other groups carry no hash; none is invented.
- **ABI:** `abi_claim` is `UNKNOWN` everywhere; the validator rejects any other value.

## Acceptance criteria (per group, before leaving BLOCKED/REVIEW_ONLY)
1. Exact base revision and full commit SHA recorded; mainline/Ubuntu inclusion verified at that base.
2. Patch hash manifest and reviewed ordered stack; semantic (not callback-name) comparison with Ubuntu.
3. Dependencies in the manifest all `resolved: true` with evidence (P2→P2a v6/v7 review; P3→remoteproc lifecycle; P4 UART mapping; P5 locking review).
4. Does not regress Dell EC v8 thermal controller or SCMI CPUFreq ([M3 contract](superpowers/specs/2026-11-07-m3-thermal-hibernate-contract.md)).
5. Dell hardware validation (separately authorized): NVMe, Wi-Fi, Bluetooth, remoteprocs, display.

## UNKNOWN
Mainline ancestry of all groups; Ubuntu inclusion re-verification; P4/P5 live status; whether any successor of P2 targets v7; Dell UART/console mapping; remoteproc lifecycle fix.

## Validator semantics
`NO_GO` (exit 1): missing/duplicate/unexpected group, bad enum, non-HTTPS URL, bad SHA, ABI claim, secret-like content, `READY`, P2/P2a/P3 not BLOCKED, or the P2→P2a / P3→remoteproc dependencies dropped, unreadable manifest. `REVIEW_REQUIRED` (exit 0): structurally valid, with blockers listed. It cannot output GO.
