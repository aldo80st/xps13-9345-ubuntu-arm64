# DisplayLink D6000, EVDI and Secure Boot

## Symptoms (observed 2026-11-01)
- Ubuntu 26.10 / kernel 7.3.0-10-generic / aarch64.
- DisplayLink 6.4, evdi-dkms 1.15.0+dfsg.
- DKMS module is signed and MOK certificate is enrolled.
- `modprobe evdi` -> `Operation not permitted`; kernel lockdown reports module loading restricted.
- `systemd-modules-load` fails due to `/etc/modules-load.d/evdi.conf`.
- DisplayLink service logged hundreds of failed starts.

## Critical distinction — updated 2026-11-02

**The EVDI PKCS#7 signature has been cryptographically verified successfully against the enrolled local MOK public certificate. Re-signing is NOT the next step.** The MOK config table in firmware contains that exact public certificate.

The system boots with `efi=noruntime`, **enforced by Ubuntu package `ubuntu-x1e-settings`**, and the kernel logs `integrity: secureboot mode unknown, no efi`. Its upstream `load_uefi.c` returns early if EFI Runtime Services cannot read variables **before** importing MOK certificates from the EFI config table. Therefore, the strongest remaining hypothesis is missing kernel trust keyring import caused by disabled EFI Runtime Services, not a mismatched signing key.

Canonical's LP #2131181 concerns certificates being loaded into an incorrect keyring and remains a secondary possible issue; it does not prove a fix for this early-return path. **Do not remove `efi=noruntime` persistently without reviewing the Qualcomm firmware workaround and establishing physical recovery.**

Read the [full read-only cryptographic and EFI MOK audit](secure-boot-evdi-mok-audit-20261102.md).

## Safe read-only checks
```bash
mokutil --sb-state
mokutil --test-key /var/lib/shim-signed/mok/MOK.der
/usr/sbin/modinfo evdi | grep -E 'filename:|signer:|sig_key:|vermagic:'
journalctl -b -u systemd-modules-load --no-pager -n 30
journalctl -k -b --no-pager | grep -iE 'MokList|lockdown|module verification'
grep -R '^evdi$' /etc/modules-load.d/ 2>/dev/null
```

## Recovery / resolution criteria
- Preserve Secure Boot and shim signature validation.
- Prefer a distribution kernel that properly loads enrolled MOK certificates, after confirming its changelog and testing a reboot.
- Do **not** use `mokutil --disable-validation`, unsigned kernel builds, module signature bypasses or arbitrary EFI edits.
- Verify that `evdi` loads successfully **and** both monitors work after reboot, without repeated service failures.
- Document rollback before touching boot configuration.

Sources: [Ubuntu MOK patch](https://lists.ubuntu.com/archives/kernel-team/2026-October/172721.html), [DisplayLink Secure Boot guide](https://support.displaylink.com/knowledgebase/articles/1181617-how-to-use-displaylink-ubuntu-driver-with-uefi-sec).
