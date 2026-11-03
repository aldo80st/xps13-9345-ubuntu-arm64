# [Ubuntu 26.10 ARM64] Enrolled shim MOK is not imported into kernel trusted keyrings with efi=noruntime (XPS 13 9345)

## Package

- Source package: `linux`
- Binary package: `linux-image-7.3.0-10-generic` (`7.3.0-10.10`)
- Architecture: `arm64`
- Distribution: Ubuntu 26.10
- Hardware: Dell XPS 13 9345, Qualcomm Snapdragon X Elite
- `ubuntu-x1e-settings`: version 34; the distro's GRUB drop-in intentionally includes `efi=noruntime` on Qualcomm.
- Secure Boot is enabled; shim validation and kernel Lockdown are enabled.
- Related device: Dell D6000 DisplayLink USB dock (`17e9:6006`), kernel module EVDI 1.15.0+dfsg.

## Expected result

A Machine Owner Key (MOK) enrolled in shim, approved for trust, should become available to the kernel's applicable trusted keyring when the signed Ubuntu kernel boots with Secure Boot enabled. A compatible, correctly signed EVDI DKMS module should then pass kernel module signature verification without disabling Secure Boot/shim validation.

## Actual result

- EVDI DKMS built and signed for the running kernel. The PKCS#7/SHA512 module signature was verified with OpenSSL CMS against the local public MOK X.509 certificate (exit status 0).
- `mokutil --test-key /var/lib/shim-signed/mok/MOK.der` confirms the key is enrolled but reports `Failed to access kernel trusted keyring: Required key not available`.
- The shim MOKvar handoff table is exposed at `/sys/firmware/efi/mok-variables/` and includes `MokListRT`, `MokListXRT`, `MokListTrustedRT`. The enrolled public certificate is present in `MokListRT`.
- Privileged `keyctl show`: `.machine` **0**, `.platform` **0**, `.secondary_trusted_keys` **5**, `.builtin_trusted_keys` **5** asymmetric keys; module signer absent from trusted keyrings.
- Kernel logs on normal boot include `integrity: secureboot mode unknown, no efi`, `Lockdown: modprobe: unsigned module loading is restricted`; `modprobe evdi` fails with `Operation not permitted`. DisplayLink cannot initialize two monitors.
- `efi=noruntime` comes from the official `ubuntu-x1e-settings` package and is deliberately retained as a firmware workaround.

## Controlled diagnostic A/B experiment

With informed owner approval, one *temporary* GRUB boot had only `efi=noruntime` removed (not persisted), leaving Secure Boot enabled, shim validation active and the officially signed kernel unchanged.

Ubuntu did boot and remote access resumed. EFI services were reportedly enabled, but integrity logged `integrity: secureboot mode unknown`, plus `MODSIGN: Couldn't get UEFI db list` and `Couldn't get UEFI dbx list`. The `.machine` and `.platform` keyrings remained empty and EVDI still failed.

A subsequent normal boot restored `efi=noruntime`, Secure Boot enabled and remote access. **Please do not suggest removing `efi=noruntime` persistently; the one-time experiment did not fix the problem and may expose firmware instability.**

## Reproduction on this hardware

1. Boot the official Ubuntu 26.10 `7.3.0-10-generic` kernel with enabled Secure Boot, shim validation enabled, `ubuntu-x1e-settings` default `efi=noruntime` and the enrolled MOK.
2. Observe that MOK variables are present in the EFI config table under `/sys/firmware/efi/mok-variables/`.
3. Compare `mokutil --test-key`, the MOK certificate, the EVDI module signature and the `.machine` / `.platform` kernel keyrings.
4. Attempt to load EVDI (or another DKMS module signed by the enrolled MOK); the kernel refuses under Lockdown.
5. Observe missing DP outputs from the DisplayLink dock.

## Suspected kernel mechanisms / maintainers' review requested

The `security/integrity/platform_certs/load_uefi.c` path checks `EFI_RT_SUPPORTED_GET_VARIABLE` and can return before reading shim's static MOKvar config table. Separately, the EFI secureboot integrity state remains unknown even when firmware boot policy reports Secure Boot enabled. Merely removing `efi=noruntime` was empirically insufficient.

An **experimental RFC v3**, tested only outside the running kernel, attempts to access the static MOKvar table if early `EFI_SECURE_BOOT` is true and requires both `MokListTrustedRT` authorization and `MokListXRT` revocations to be present, parsing revocations before adding MOK. It uses `get_handler_for_mok` instead of `get_handler_for_db`. This is **not an accepted production fix**.

**CRITICAL SECURITY OPEN QUESTION:** Under `efi=noruntime`, firmware `dbx` may not be retrievable. The shim MOKX list is not necessarily equivalent to the firmware revocation database. We explicitly request Canonical EFI / kernel integrity / shim maintainer review of provenance and revocation guarantees **before** any kernel is built, signed or distributed with the proposed change. Please do not recommend disabling Secure Boot, shim validation or Lockdown.

## References and test evidence

- Evidence of supervised A/B trial and restored normal boot: https://github.com/aldo80st/xps13-9345-ubuntu-arm64/blob/sprint/superpowers-cycle-20261101/docs/efi-runtime-oneboot-result-20261103.md
- RFC v3 patch (non-deployable): https://github.com/aldo80st/xps13-9345-ubuntu-arm64/blob/sprint/superpowers-cycle-20261101/patches/0001-RFC-efi-mokvar-without-runtime.patch
- Implementation notes and security caveats: https://github.com/aldo80st/xps13-9345-ubuntu-arm64/blob/sprint/superpowers-cycle-20261101/docs/evdi-mok-rfc-implementation-20261103.md
- CI: 36 Python tests, with native userspace C harness of the exact kernel source (8 mock EFI scenarios) and the real Ubuntu EFI signature parser, ASan/UBSan and deterministic malformed-input sweep; all passed. https://github.com/aldo80st/xps13-9345-ubuntu-arm64/actions/runs/41700545026
- Tracking issue: https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/10

## Scope

This report is **about missing trust of an enrolled MOK on the official Ubuntu ARM64 kernel**, not a generic third-party DisplayLink installation request. The hardware/DKMS symptom is a reproducible indicator. No unapproved kernel changes have been installed.

System diagnostics may be uploaded separately through `ubuntu-bug linux` after reviewing information for privacy.
