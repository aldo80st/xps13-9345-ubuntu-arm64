# Qualcomm IRIS video codec: qcvss8380.mbn

## Observed
The kernel requests `qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn` and gets `-2` (ENOENT). This repeats when video nodes are opened. It may prevent hardware video decoding.

Upstream Ubuntu bug [2171351](https://go.mail-archive.com/ubuntu-bugs%40lists.ubuntu.com/msg6324429.html) documents an extractor omission on another Snapdragon Dell laptop.

## Candidate (NOT YET INSTALLED / TESTED)
A Dell-extracted Qualcomm Adreno graphics firmware snapshot is documented by [valpackett/firmware-dell-qcom](https://github.com/valpackett/firmware-dell-qcom). The XPS 9345 entry points to the equivalent Latitude 7455 binary. The staged decompressed candidate from that repo was verified on 2026-11-01:

- Source: `qcom/x1e80100/dell/latitude-7455/qcvss8380.mbn.zst` (December 2025 A10 driver)
- Uncompressed size: **2,318,952 bytes**
- SHA-1: `a0e6a3e58398efa76c3fc0dbd8e51b0c5749fe67` (matches source README).
- SHA-256: `8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629` (measured locally).
- **Caution:** bug 2171351 lists a *different* 2,323,048-byte driver version and SHA-256 `d52c28872ebbaf8087a30bf196d15ee24839fd62a2d91b605edfa73c09bbd8d4`. Do not treat these as identical.

A safer long-term solution is correct vendor firmware packaging in `linux-firmware` / `qcom-firmware-extract`.

## Official vendor provenance — independent check still pending
Dell offers an [official XPS 13 9345-compatible Adreno package KPF2C (31.0.121.0, A09)](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=kpf2c), with package SHA-256 `83ca322727b86d80042fe06824cc4dcef705bab511d31aca4a25bbf741ee5d91`.
An automated direct CDN request returned HTTP 403 on 2026-11-01; therefore **we have NOT independently extracted the candidate blob from this verified Dell package**. The staged file's checksum proves consistency with a third-party repo's published hash, not Dell's package authenticity. Prefer vendor-source verification before installing executable device firmware on a production laptop.

## Staging (unprivileged, no kernel changes)
```bash
bash scripts/stage-qcom-iris.sh
```

## Install (explicit local administrator approval required)
Review the script, then run from an interactive terminal:
```bash
bash scripts/install-qcom-iris.sh
```
This installs only the SHA-256-verified local file into
`/lib/firmware/updates/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn`
using sudo. No raw blob is committed to this repo. Kernel firmware lookup uses `/lib/firmware/updates/` before the base firmware directory.

After a reboot, validate kernel logs and actual hardware decode. A missing firmware warning disappearing is **not** proof that decoding itself is functional.

To revert the change: remove the single installed file using sudo after verifying its SHA-256 matches this guide; reboot. Do not remove files owned by system packages.

Sources: [Linux firmware search paths](https://docs.kernel.org/7.1/driver-api/firmware/fw_search_path.html), [XPS device tree](https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/e739acbe05b06de78ef7089470f122432f651faa/arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts).
