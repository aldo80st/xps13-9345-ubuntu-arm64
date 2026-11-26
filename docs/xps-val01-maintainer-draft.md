# Upstream report drafts — XPS 13 9345 ARM64 (DO NOT SEND)

**2026-11-21 | Status: DRAFT / NOT PUBLISHED.** Two separate concerns have different upstream owners. Do not combine them in a single regression report. Replace every TODO with verifiable evidence before publication. Review with a second engineer and obtain explicit permission to contact maintainers.

## Draft A — Dell XPS EC / ADC / reboot correlation

**Proposed subject:** Dell XPS 13 9345: request for guidance on EC/PMIC thermal validation across Ubuntu 7.3.0-10/-11

Hardware: Dell XPS 13 9345, Snapdragon X Elite (ARM64); BIOS 2.14.0.
Distribution: Ubuntu 26.10, currently Linux `7.3.0-11-generic`; prior `7.3.0-10-generic`.
Relevant series: [Dell EC v8 cover letter (2026-10-26)](https://lists.openwall.net/linux-kernel/2026/10/26/28) and [thermal zones v2 (2026-10-22)](https://lkml.rescloud.iu.edu/2610.2/17102.html).

**Observed:** A prior session was unexpectedly interrupted around 2026-11-20 19:44 local time; a separate reboot around 22:07 is recorded. Historical local report (#50) mentions `qcom-spmi-adc5-gen3` ADC timeouts and `sys_therm1: -110` near that window. This line has NOT been independently re-extracted in the present work. Linux 7.3.0-11 does not currently expose the previously staged `dell-xps-ec` module; three SCMI CPUFreq policies (0/4/8) remain observable and use ondemand. The machine has not been experimentally rebooted or stressed for this report.

**What we do NOT claim:** The EC patch caused the reset; the absence of a timeout in one boot establishes stability; or the thermal-zone patch is merged in the running Ubuntu kernel.

**Questions:** Which exact upstream branch/commit is expected to contain EC v8 and any dependencies for Qualcomm PMIC ADC5 Gen3? Is there a maintainer-preferred bounded, non-invasive way to distinguish EC thermal telemetry stalls from an unrelated platform reset? Are there known incompatibilities between independent DTS thermal-zone additions and the EC series?

**To collect before posting:** Sanitized `journalctl -b -3` relevant lines with monotonic timestamps, boot IDs redacted, verified kernel release per boot, exact Ubuntu source config and module provenance, pstore status if safely readable, repeat observations without inducing crashes. Do NOT attach raw logs.

**Proposed outcome:** Request guidance or comment on an existing series, not a new driver implementation. No `Tested-by` without a verified matching patch stack.

## Draft B — Qualcomm Iris V4L2 functional, Chrome VA-API initialization failure

**Proposed subject:** Qualcomm X1E80100 / Linux 7.3.0-11: V4L2 H.264 decode works, Chrome 158 VA-API fails to initialize

Environment: Dell XPS 13 9345, Ubuntu 26.10 aarch64, kernel 7.3.0-11, Chrome 158.0.8127.36, Wayland, Mesa 26.2.4, Adreno X1-85. External display testing includes a Dell D6000 DisplayLink dock (EVDI); repeat with the internal display only before submitting a DRM/Chromium bug.

**Observed:** `/dev/video16` advertises `qcom-iris-decoder`, H.264/HEVC/VP9/AV1; GStreamer `v4l2h264dec` decodes an isolated synthetic 1080p H.264 stream without error. Chrome has rendered frames locally, but `chrome://gpu` displays an empty Video Acceleration decoding table and the log contains `vaInitialize failed: unknown libva error`. A real H.264 live playback session selected `FFmpegVideoDecoder` (not a platform decoder) and reported repeated `DEMUXER_UNDERFLOW`; these observations alone do not establish that software decoding caused the live-stream interruption.

**Related implementation work:** [qcom-va-driver](https://github.com/radxa-pkg/qcom-va-driver) is an experimental userspace backend; [Iris HFI gen2 proposed fixes v1 (2026-10-29)](https://lists.openwall.net/linux-kernel/2026/10/29/306) may be required for some VA-API features. Neither is installed as the active Chrome backend on this host.

**Questions:** Is `qcom-va-driver` H.264 decoding on X1E80100 supported with the exact Iris firmware and running kernel? Which kernel commits from the HFI gen2 series are prerequisites? What is the recommended Chromium VA-API support/debugging path on ARM64/Wayland for this hardware?

**To collect before posting:** Test a known public stream with explicit codec/profile/resolution, capture Chrome decoder name and drop counter, `vainfo` in an isolated driver path, identify tested firmware version and exact patches; no private media URL or cookies. Do not assert a Chromium bug without testing the adapter and documented support limits.

**Proposed outcome:** File a focused compatibility observation in the appropriate existing driver/Chromium tracker, *after* checking for duplicates and obtaining publication approval.
