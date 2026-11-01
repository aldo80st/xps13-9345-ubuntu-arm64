# PD-mapper regression after installing Qualcomm IRIS video firmware

**Status: root cause verified and recovered on 2026-11-01** (Ubuntu 26.10, Dell XPS 13 9345, kernel 7.3.0-10-generic).

## Symptoms and root cause

After staging the missing IRIS firmware in:
`/lib/firmware/updates/qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn`

a previously functioning userspace `pd-mapper.service` began to fail at boot with:

```
pd-mapper: no pd maps available
pd-mapper.service: Failed with result 'start-limit-hit'
```

**Root cause:** `pd-mapper` scans the first matching firmware directory under `/lib/firmware/updates/` and does **not** fall back to the base location when that directory exists without matching `.jsn` descriptors. A trace of the actual process using `strace -f -e trace=openat,newfstatat,readlinkat` showed successful `openat` on `/lib/firmware/updates/qcom/x1e80100/dell/xps13-9345` and then exit with `no pd maps available`.

The legitimate `adspr.jsn`, `cdspr.jsn` and related map files were present and readable in `/lib/firmware/qcom/x1e80100/dell/xps13-9345/`. The new `updates/` directory inadvertently shadowed them.

## Verified recovery

Move the *same verified* Dell video firmware into the existing base directory; remove only the empty overlay tree you created, then clear the service's failure state and start it:

```bash
sudo bash scripts/relocate-qcom-iris-firmware.sh
systemctl is-active pd-mapper.service
```

The script checks the XPS 9345 DMI model, checks the source and destination SHA-256 (`8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629`), refuses to overwrite unexpected files, verifies that base `.jsn` maps remain readable, removes only its own verified old file and empty overlay directories, and restarts `pd-mapper.service`.

**Observed results:** `FIRMWARE_RELOCATED_TO_BASE_AND_SHA256_VERIFIED`, `PD_MAPPER_ACTIVE`, `NRestarts=0`, and only `systemd-modules-load.service` remained failed. The hardware codec still requires real decode validation; a service being active is not evidence of complete subsystem functionality.

## Important warning

Do not solve this by disabling `pd-mapper.service` just to hide a failed unit. Nor should you blindly copy map files from other machines into `updates/`. Confirm that the expected `.jsn` descriptors exist and restore the search semantics by removing the overlay that caused the regression.

A future distribution package may manage this firmware; do not delete or replace an unexpected package-owned file. Document `dpkg -S` results and use the package manager if the base file becomes officially packaged.

Source: [Debian protection-domain-mapper implementation](https://sources.debian.org/src/protection-domain-mapper/1.0-4/pd-mapper.c).
