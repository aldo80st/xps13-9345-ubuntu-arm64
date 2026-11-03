# Dell XPS 13 9345 — Ubuntu ARM64 field notes

[Español](README.es.md) · Community troubleshooting notebook for Ubuntu 26.10 and Snapdragon X Elite (X1E80100).

**Goal:** reproducible, reviewable fixes that preserve Secure Boot. No experimental kernel patches, security bypasses or vendor firmware binaries are redistributed here.

## Hardware and tested baseline
- Dell XPS 13 9345 (ARM64, Snapdragon X Elite); Ubuntu 26.10; Linux `7.3.0-10-generic`.
- Initial observed state: Secure Boot enabled; `evdi` 1.15 DKMS module signed but not accepted by kernel; `qcom-iris` video firmware missing.
- A second device might behave differently. **Do not assume the procedures are universally validated.**

## Tracked investigations

| Problem | Evidence | Status | Documentation |
| --- | --- | --- | --- |
| DisplayLink D6000: EVDI fails under Secure Boot | `modprobe evdi`: Operation not permitted; service repeatedly fails | **Diagnosed; fix pending** | [EVDI/MOK](docs/secure-boot-evdi.md) |
| Qualcomm IRIS video firmware | Missing `qcvss8380.mbn`, `-2` in journal | **Official Dell firmware installed, preserved across reboot; V4L2 device present; real decoding test pending. Overlay regression fixed.** | [Video firmware](docs/qcom-iris.md) |
| Fan control / thermal throttling | Kernel EC patch v8 published Oct 25, 2026 | **Upstream patch; not installed** | [Thermal control](docs/thermal-ec.md) |
| Speaker channel mapping | PipeWire exposes FL/FR/RL/RR; real speaker output not fully validated | **Investigation** | [Audio](docs/audio.md) |

## Safe workflow

1. Run `bash scripts/diagnose-readonly.sh` (does not modify the system).
2. Review the evidence against the relevant issue guide.
3. Back up the affected configuration; verify version, hash, source and rollback.
4. Apply one change at a time and reboot only when needed.
5. Test the actual feature, capture before/after results and publish an anonymized write-up.

> Do not publish unredacted `journalctl` logs, `dmesg` dumps, machine serial numbers, MAC/IP addresses, usernames, private keys, BitLocker recovery keys or EFI variable contents.

## Iterative sprint verification (Superpowers)

A bounded, **read-only** iteration controller is available at [docs/sprint-cycle-method.md](docs/sprint-cycle-method.md). It records private checkpoints and publishes only redacted decisions. This is not an automatic system patcher and does not declare untested hardware working.

```bash
python3 -m unittest discover -v
python3 scripts/sprint_cycle.py --run --max-rounds 6
```

See [2026-11-01 validation](docs/sprint-cycles/2026-11-01-validation.md) and the [upstream solution gate](docs/sprint-2026-11-01-upstream-solutions-review.md).

## Sources
- [Dell XPS 9345 support patches and hardware matrix](https://github.com/alexVinarskis/linux-x1e80100-dell-tributo)
- [Ubuntu Secure Boot documentation](https://documentation.ubuntu.com/security/security-features/platform-protections/secure-boot/)
- [Canonical kernel patch for misrouted MOK certificates — LP 2131181](https://lists.ubuntu.com/archives/kernel-team/2026-October/172721.html)
- [Ubuntu bug 2171351 — missing qcvss8380 firmware](https://go.mail-archive.com/ubuntu-bugs%40lists.ubuntu.com/msg6324429.html)
- [Dell XPS BIOS 2.15.0](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=PK3V5)
- [EC / fan patch v8](https://lkml.rescloud.iu.edu/2610.3/01866.html)

Contributions are welcome. Please distinguish **observed**, **inferred**, **tested**, and **resolved**.
