# H1 / issue #25 — SMP2P and remoteproc lifecycle audit

2026-11-07. **Issue #25: OPEN / NO_GO. P3 and H1 remain blocked. Remoteproc is not fixed.**
This is a read-only source analysis and an offline admission contract, not a kernel
patch or a Dell runtime reproduction. It supplements the
[H1 matrix](hibernate-qualcomm-h1.md), [manifest](hibernate-qualcomm-manifest.json),
[patch review](hibernate-patch-review-20261107.md) and
[epic](superpowers/specs/2026-11-07-xps-hibernation-epic.md).

## Observations and their limits

The [original proposal](https://lists.openwall.net/linux-kernel/2026/10/09/2521)
reports Lenovo Yoga Slim 7x / X1E80100 tests on Arch Linux ARM v7.2:

- After real power-off, stale ADSP restart acknowledgement prevents handshake;
  CDSP retains a completed negotiation while its fresh item has the wrong version.
- The proposed `restore_noirq` clears cached inbound pointers, entry values,
  negotiation and SSR state; reallocates outbound SMEM, reclaims entries in reverse
  list order, then discovers inbound SMEM and kicks negotiation.
- ADSP/CDSP starts succeeded with the patch when manually stopped before imaging
  and started afterwards. Running remotes survived `test_resume`.
- A remote running at image creation remains reported running after real restore;
  stopping reports “failed to shutdown: -22”. The author explicitly leaves this open.
- PCI changes were required; Bluetooth UART was closed and ath12k unloaded.

These are author-reported Lenovo observations, not Dell measurements. No Dell
9345 restore, firmware equivalence or lifecycle solution is established. Shared
SoC identity does not establish board/firmware equivalence. Proposal status remains
proposed; acceptance, current mainline ancestry and exact Ubuntu inclusion are
UNKNOWN. No new integration search was performed for this deliverable.

## Source provenance

The proposal names base `705529dab1fa872d8b53b09c95e1b03a95573376`.
Three individual files at that revision were fetched and read independently;
no full kernel was downloaded. Browser fetches at that revision initially failed
(cache miss); targeted HTTPS downloads subsequently succeeded. SHA-256 below
fingerprints received bytes, not independent authentication or Ubuntu provenance.

| File at proposal base (primary source) | SHA-256 |
| --- | --- |
| [drivers/remoteproc/remoteproc_core.c](https://raw.githubusercontent.com/torvalds/linux/705529dab1fa872d8b53b09c95e1b03a95573376/drivers/remoteproc/remoteproc_core.c) | `be0ed0eb9b789c5c24b90a3d1a497a2815cda7bc8d5b94e5d4e7229aef79beb9` |
| [drivers/remoteproc/qcom_q6v5_pas.c](https://raw.githubusercontent.com/torvalds/linux/705529dab1fa872d8b53b09c95e1b03a95573376/drivers/remoteproc/qcom_q6v5_pas.c) | `354ebbca60e5f8706baec77ba5741a1635684a6ab3056e08b128723a0864494b` |
| [drivers/soc/qcom/smp2p.c](https://raw.githubusercontent.com/torvalds/linux/705529dab1fa872d8b53b09c95e1b03a95573376/drivers/soc/qcom/smp2p.c) | `6ec59f1cb21b218530f8807dbb9829afeed1b780225fbf643691caff15c7bf01` |

Historical comparison: [v6.12 PAS](https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/remoteproc/qcom_q6v5_pas.c)
uses `adsp_probe`/`adsp_stop`, whereas the proposal base uses
`qcom_pas_probe`/`qcom_pas_stop`. Both platform driver registrations lack `.pm`;
both contain X1E80100 ADSP/CDSP matches. Do not transplant historical function
names into an exact-base audit. Ubuntu 7.3.0-10.10 was not re-inspected here.

## State sequence and evidence boundaries

PM phases below follow the kernel's [device PM documentation](https://docs.kernel.org/driver-api/pm/devices.html#entering-hibernation).
The snapshot and image-writing paths are distinct: freeze precedes snapshot;
original execution thaws before writing the image, then poweroff callbacks can
run for platform hibernation. The restore kernel boots independently, freezes its
devices before image replacement, and the image kernel runs restore callbacks.
Failed image creation/restoration follows thaw paths. Poweroff callback execution
depends on hibernation mode; it must not be assumed for every shutdown path.

| Phase | Established behavior / inference |
| --- | --- |
| Probe | Base PAS `qcom_pas_probe` copies `auto_boot` and calls `rproc_add`. X1E80100 ADSP/CDSP descriptors enable auto boot. SMP2P probe allocates outbound SMEM and starts inbound discovery. Probe is not rerun merely because RAM is restored. |
| Successful start before snapshot | Core `rproc_start` sets `RPROC_RUNNING` after subdevice start. `rproc_boot` holds a power reference. |
| Freeze → freeze_late → freeze_noirq → snapshot | No PAS driver PM hook reconciles remote lifecycle at the inspected base. SMP2P also has no PM registration before P3. Thus a running image may preserve old state/references/negotiation. This is source inference consistent with the report, not a Dell trace. |
| Original-kernel thaw → image write → poweroff | PAS has no driver poweroff hook. Any later hardware shutdown cannot retroactively change the saved image. No claim is made that runtime PM or generic power-domain activity stops a remote cleanly. |
| Power loss → restore-kernel probe → image replacement | Hardware/SMEM may be rebuilt while the saved image retains its earlier software state. The restore kernel's probe does not reconcile restored objects. Its firmware activity and timing require an exact configuration audit. |
| Image-kernel restore_noirq → restore_early → restore → complete | P3 resets SMP2P only. It neither calls remoteproc shutdown/boot nor repairs remoteproc power references or subdevices. A saved RUNNING object is therefore not proof of live firmware. |
| Later stop/start | Core error handling can retain old state; another boot can return success without loading firmware when the saved power reference is already nonzero. A userspace state label or successful boot return is insufficient acceptance evidence. |

Evidence anchors: base SMP2P `qcom_smp2p_probe`,
`qcom_smp2p_alloc_outbound_item`, `qcom_smp2p_start_in`,
`qcom_smp2p_check_ssr`, `qcom_smp2p_driver`; base PAS
`qcom_pas_probe`, `x1e80100_*_resource`, `qcom_pas_driver`;
base core `rproc_start`, `rproc_boot`, `__rproc_shutdown`, `rproc_stop`
(all linked in the provenance table). Absence of driver hooks does **not** prove
absence of all subsystem/domain callbacks: PM callback precedence and actual Dell
dependency ordering remain unverified.

### What -22 does and does not establish

At the inspected base, PAS `qcom_pas_stop` requests Q6 stop, then calls
`qcom_pas_shutdown`; its return produces the reported shutdown diagnostic.
Later DTB shutdown or SMEM lock cleanup can overwrite that return. Consequently
the printed error alone does not prove the final return to the core. The helper
and secure firmware cause were not traced to establish the Lenovo errno origin.

Core `__rproc_shutdown` accepts RUNNING/ATTACHED/CRASHED, decrements the power
reference and calls `rproc_stop` when appropriate. A stop failure restores that
reference. `rproc_stop` sets OFFLINE only after resource-table reset, driver stop
and subdevice unprepare succeed. Thus persistent RUNNING is compatible with a
failed stop; it is not evidence that the core rejects RUNNING as invalid.
The exact failing layer on Lenovo and Dell remains UNKNOWN. Blindly assigning
OFFLINE, ignoring errors or adding guessed PM stop/start hooks is not justified.

## Locked contract and acceptance criteria

[hibernate-remoteproc-h1.json](hibernate-remoteproc-h1.json) records six UNKNOWN
requirements. [The stdlib gate](../scripts/hibernate-remoteproc-h1.py) defaults to
reading only that file, emits JSON `NO_GO`, `admitted: false`, and **always exits 1**.
An empty `errors` list means a valid blocked record, never candidate approval.
Malformed/missing files, changed types, missing requirements, extra fields and
unsupported VERIFIED/GO assertions produce validation errors and still deny.
The script does not fetch sources, inspect hardware, run commands or execute
contract content. It is deliberately a locked research gate; a future admission
path requires reviewed code and evidence, not editing an UNKNOWN to VERIFIED.
The broader H1 validator's exit 0 means structurally valid REVIEW_REQUIRED and
must not be interpreted as passing this admission gate.

Before a reviewer can replace this lock, require all of:

1. **Exact base:** Ubuntu source/package identity and hashes, full revisions and
   ordered patch hashes; semantic comparison of relevant core/PAS/SMP2P/PM paths.
2. **Dell inventory:** DT compatible/status, firmware identities, enabled remotes,
   consumers and initial states. No assumption that remoteproc numeric IDs are stable.
3. **Lifecycle design:** explicit state/reference/resource sequence for probe,
   freeze/snapshot, thaw, poweroff, restore and restore-kernel interference;
   audited SMEM, IRQ, PAS, power-domain and remote/subdevice dependency ordering.
4. **Failure handling:** balanced multiple-client references, GLINK/rpmsg/sysmon/SSR
   teardown/recreation, crash races, timeouts and partial failure unwind. A failed
   quiesce must prevent unsafe imaging. Manual stop/start alone does not satisfy this.
5. **Reconciliation:** reviewed SMP2P restore semantics plus actual firmware/PAS
   recovery; no stale pointers or software-only RUNNING assertions. Successful
   independent remote services and subsequent controlled stop/start must agree.
6. **Separately authorized Dell validation:** running-at-image and initially-offline
   remotes, failed-image thaw, `test_resume`, ordinary suspend and three real
   power-off restores of the same session. Record trace/state/refcount/service
   evidence and EC v8 thermal/SCMI, NVMe, Wi-Fi, Bluetooth and display regressions,
   recovery and rollback. `test_resume` cannot substitute for lost hardware state.

No firmware, boot, kernel, swap, power-state or thermal changes were performed.
No hibernation/reboot, kernel build, push or merge is part of this work.

## Offline verification

Run from the repository root:

```sh
python3 -m unittest discover -s tests -p test_hibernate_remoteproc_h1.py
python3 -m unittest discover -s tests
python3 scripts/hibernate-remoteproc-h1.py
```

The final command must exit 1. Tests validate admission behavior only. TDD RED
was observed with a minimal locked-output gate lacking input validation: 13
assertion failures across malformed/missing/mutated-input cases. GREEN adds
strict record validation. Runtime remoteproc correctness remains untested.

Verification on 2026-11-07: focused suite **5 tests passed**; full repository
unittest discovery **123 tests passed**. Default gate produced NO_GO with six
blockers, empty validation errors and exit 1. `git diff --check` passed.

## Verificación adicional del árbol Ubuntu 7.3 del XPS — 2026-11-07

El integrador inspeccionó directamente las fuentes del paquete Ubuntu `linux-source-7.3.0=7.3.0-10.10` en el XPS, sin copiar ni modificar los archivos:

- `drivers/soc/qcom/smp2p.c`: contiene `qcom_smp2p_check_ssr`; **no contiene** `qcom_smp2p_restore_noirq` ni una asignación `.restore_noirq` en ese archivo. La corrección P3 no está incorporada ahí.
- `drivers/remoteproc/qcom_q6v5_pas.c`: contiene `qcom_pas_stop`, `qcom_pas_probe`; **no declara** `.pm =` ni callback `.restore_noirq` en ese archivo. Esto no excluye acciones PM del subsistema, genpd o firmware.
- `drivers/remoteproc/remoteproc_core.c`: contiene `rproc_boot` y manejo de apagado/estado, pero la existencia de estas funciones no demuestra que el estado guardado se reconcilie con el firmware tras hibernación.

El contrato se ejecutó contra los artefactos versionados con **salida 1, `NO_GO`, `admitted=false`, 6 bloqueos y 0 errores de validación**. La suite conjunta del worktree XPS: **146 pruebas OK (una omitida)**.

La observación de ausencia de hooks es local y estática. No se inició/paró ningún coprocesador, no se actualizó firmware y no se hicieron pruebas de suspensión, hibernación ni restauración.

## Source-aware no-op checker — incremental issue #25 step

The optional checker reads an **explicitly supplied, already available** Linux
source directory. It does not locate/download a kernel, call git, preprocess or
compile C, run tree-provided commands, modify source, use sudo or touch firmware.
Run later on the XPS against the selected Ubuntu tree; no Ubuntu tree was supplied
or inspected in this implementation session:

```sh
python3 -I scripts/hibernate-remoteproc-h1.py --source-tree /path/to/linux-source-7.3.0
```

Exit **1** is intentional for every report. Without the option, the original
four-field output and version-1 locked contract are unchanged. With the option,
`source_report` is added, with its own `schema_version: 1`, scope
`file_local_lexical_only`, per-file SHA-256, definition observations, SMP2P restore
shape, PAS driver PM binding/phase hooks and sorted unique `reason_codes`.
Source failures live in that report; top-level `errors` still means contract
validation errors. A valid contract is not a valid source tree or approval.

The checker opens only these relative paths, through directory descriptors with
no symlink following below the supplied root. Files must be regular, UTF-8 and
at most 4 MiB each. Nonexistent roots/files, invalid encoding, directories,
symlinks, oversized input and recognized malformed C produce unknown observations
and `SOURCE_INPUT_UNREADABLE`, never evidence of absence. No recursive discovery
or source writes occur. Use a stable tree: three reads do not create an atomic
snapshot. Hashes fingerprint read bytes, not package authenticity or patch order.

### Exact lexical expectations

These names are deliberately tied to the proposal-base audit, rather than
accepting historical `adsp_*` names as equivalents:

| File | Required unique int/void function definitions |
| --- | --- |
| `drivers/soc/qcom/smp2p.c` | `qcom_smp2p_probe`, `qcom_smp2p_alloc_outbound_item`, `qcom_smp2p_start_in`, `qcom_smp2p_check_ssr` |
| `drivers/remoteproc/qcom_q6v5_pas.c` | `qcom_pas_probe`, `qcom_pas_stop` |
| `drivers/remoteproc/remoteproc_core.c` | `rproc_start`, `rproc_boot`, `__rproc_shutdown`, `rproc_stop` |

`definitions` records parameter text; `missing_definitions` identifies absent
or nonunique recognized definitions. Comments, string/character literals,
prototypes, calls and preprocessor directive text cannot satisfy these checks.
This is a name/definition inventory, **not** ABI or function-body correctness
verification. Attributes or alternative declarations outside the narrow grammar
require manual review, not guessed equivalence.

For SMP2P, `qcom_smp2p_restore_noirq(struct device *dev)` must have the proposal's
ordered lexical anchors: driver-data lookup; cached input, entry count,
negotiation and SSR resets; inbound value/last-value reset; outbound allocation
and negative-return propagation; reverse outbound reclaim through a defined
`qcom_smp2p_claim_outbound_entry`; inbound discovery; kick; success return.
The exact registration chain must also exist:
`qcom_smp2p_driver.driver.pm = &qcom_smp2p_pm_ops`, whose explicit
`restore_noirq` field is `pm_sleep_ptr(qcom_smp2p_restore_noirq)`.
Whitespace between C tokens is tolerated in bodies; binding expressions use
the proposal spelling. Equivalent wrappers, renamed callbacks and macro-built
initializers are not silently accepted.

`smp2p_restore` is `missing`, `unrecognized`, `expected_shape`, or `unknown`.
`expected_shape` means only that ordered text and bindings were observed. It
does not validate control flow, helper bodies, memory lifetime, error handling
semantics, compilation, active configuration or upstream inclusion. Extra code
can change behavior despite matching anchors. The checker deliberately cannot
certify a patch's correctness. Conditional text is inspected without selecting
branches and produces `PREPROCESSOR_NOT_EVALUATED`; even `#if 0` text is lexical
evidence only. Duplicate definitions are not a positive match.

PAS inspection follows the exact `qcom_pas_driver` initializer's nested
`.driver.pm`. `pas_driver_pm` is `absent`, `present` (including an explicitly
assigned NULL), or `unknown`. The explicit named `dev_pm_ops` initializer is
inspected for prepare/complete, suspend/resume and runtime PM, and all
freeze/thaw/poweroff/restore phases including late/early/noirq. Hook values are
unevaluated expressions; `absent` means no explicit field in a recognized ops
initializer, `not_registered` means no driver `.pm`, and `unknown` means the
binding/initializer was not understood. A macro-generated PM table stays unknown.
No driver-local result excludes callbacks selected by PM domains, types, classes
or buses; their precedence and delegation require separate inspection of the
[PM core rules](https://docs.kernel.org/driver-api/pm/devices.html#system-power-management-phases).

| Reason code | Interpretation |
| --- | --- |
| `SOURCE_INPUT_UNREADABLE` | At least one fixed source input could not be inspected; see per-file status. |
| `EXPECTED_API_MISSING` | At least one expected definition was absent/nonunique in the supported grammar. |
| `SMP2P_RESTORE_MISSING` | No recognized restore definition in the inspected file. |
| `SMP2P_RESTORE_UNRECOGNIZED` | Restore exists but its signature, ordered anchors or registration chain differs. |
| `SMP2P_RESTORE_SHAPE_OBSERVED` | Proposal-shaped lexical evidence only; no lifecycle approval. |
| `PAS_DRIVER_PM_ABSENT`, `PAS_DRIVER_PM_PRESENT`, `PAS_DRIVER_PM_UNKNOWN` | File-local registration observation only. |
| `PREPROCESSOR_NOT_EVALUATED` | Conditional source was observed; build configuration is unresolved. |
| `PAS_LIFECYCLE_UNRECONCILED` | Always retained; this checker cannot establish safe PM compensation. |
| `C7_REMOTEPROC_SMP2P_EQUIVALENCE_UNPROVEN` | Always retained; remoteproc and SMP2P are distinct state machines. |
| `SOURCE_PROVENANCE_UNVERIFIED`, `DELL_RUNTIME_UNVERIFIED` | Always retained; hashes/static inspection do not supply those proofs. |

### What safe PM state compensation still requires

The [original SMP2P proposal](https://lists.openwall.net/linux-kernel/2026/10/09/2521)
repairs cached shared-memory negotiation. Its reported manual remote stops before
imaging and starts after restore do not cover a running-at-image PAS remote.
Any C7-style assumption that SMP2P reset also fixes remoteproc is **UNPROVEN**.
Adding a `.pm` pointer, observing RUNNING, returning success from `rproc_boot`,
or forcing OFFLINE would not establish real firmware state.

A future reviewed compensation design needs a transition table for every
initial remote state and every phase: freeze/snapshot, successful and failed
image thaw, image-write/poweroff, independent restore-kernel activity and
image-kernel restore. It must distinguish thaw without power loss from restore
after power loss. It must specify ownership and synchronization of each client
power reference, state and resource table, firmware/PAS session, SMEM mapping,
IRQ, power-domain vote and subdevice. Quiesce failure must abort imaging safely;
partial teardown/restart needs balanced unwind, observable failure propagation,
crash/SSR race handling and bounded recovery. Initially offline remotes must not
be spuriously booted. Generic stop/start callbacks are not an implementation of
these invariants, especially with multiple clients or unavailable noirq services.

The exact Dell DT topology, enabled ADSP/CDSP/other remotes, firmware/PAS behavior,
client reference ownership, GLINK/rpmsg/sysmon/SSR ordering, secure-firmware errno
origin, PM-domain overrides and restore-kernel interference remain unknown.
Ubuntu package authentication, full revisions, ordered patch hashes and semantic
equivalents require separate evidence. The previous local Ubuntu observations
above are historical input, not freshly reproduced by this checker. No kernel
fix is proposed. Runtime acceptance still requires the separately authorized
Dell experiments and regression evidence listed earlier; NO_GO remains locked.

### Fixture verification

`tests/fixtures/remoteproc-source` contains small **synthetic lexical fixtures**,
not vendored Linux sources, compilable drivers or firmware simulations. The base
fixture lacks SMP2P restore and PAS PM; the `p3` overlay models the proposal's
restore text. Tests cover negative mutations, misleading comments/prototypes,
unbound callbacks, changed API names, phase-hook observations, conditional text,
unreadable input and unchanged source bytes. No full source download is needed.

```sh
python3 -m unittest discover -s tests -p 'test_hibernate_remoteproc*.py' -q
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

## Validación independiente en fuente Ubuntu 7.3 — 2026-11-07

Se ejecutó el verificador con `--source-tree` apuntando a los archivos originales del paquete `linux-source-7.3.0=7.3.0-10.10` del Dell XPS, sin escribir en ellos. Resultado: **salida 1, `NO_GO`, `admitted=false`, seis bloqueos**, conservando la admisión cerrada. Observaciones *léxicas locales*, no afirmaciones sobre firmware real:

- `smp2p.c`: `qcom_smp2p_probe`, `qcom_smp2p_alloc_outbound_item`, `qcom_smp2p_start_in` y `qcom_smp2p_check_ssr` localizados. `qcom_smp2p_restore_noirq` **ausente** en esa fuente, no se registró enlace PM de restore.
- `qcom_q6v5_pas.c`: funciones PAS probe/stop localizadas, sin registro directo `.pm` en `qcom_pas_driver` de esa revisión. Esto **no** descarta PM de subsistemas/power-domains externos.
- `remoteproc_core.c`: funciones start/boot/shutdown/stop localizadas; su presencia no asegura que firmware y referencias guardadas se reconcilien tras restituir memoria.

La ejecución descubrió un falso faltante inicial en `qcom_smp2p_check_ssr`: su tipo de retorno real es `bool`, y el parser reconocía solo `int|void`. Se añadió un test **RED** que falló ante esa firma, se corrigió únicamente el reconocimiento de `bool` y se obtuvo **GREEN** con **158 pruebas completas (una omitida)**; el `NO_GO` de restore/remoteproc permanece intacto. Se compararon SHA256 de los tres archivos de fuente antes y después: **sin mutaciones**.

**No se aplicó el parche SMP2P**, no se encendió/apagó ningún coprocesador ni se ejecutaron operaciones de energía, kernel o arranque. Estos hallazgos afinan el diagnóstico, no cierran el issue #25.
