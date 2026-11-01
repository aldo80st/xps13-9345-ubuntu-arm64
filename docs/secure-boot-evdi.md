# DisplayLink D6000, EVDI and Secure Boot

## Symptoms (observed 2026-11-01)
- Ubuntu 26.10 / kernel 7.3.0-10-generic / aarch64.
- DisplayLink 6.4, evdi-dkms 1.15.0+dfsg.
- DKMS module is signed and MOK certificate is enrolled.
- `modprobe evdi` -> `Operation not permitted`; kernel lockdown reports module loading restricted.
- `systemd-modules-load` fails due to `/etc/modules-load.d/evdi.conf`.
- DisplayLink service logged hundreds of failed starts.

## Critical distinction
`mokutil --test-key` proving a certificate is enrolled is **not** proof that it is in the kernel's module-signing trust keyrings.

Canonical's LP #2131181 describes an MOK certificate going to the wrong keyring. A kernel-team correction was published in October 2026, but whether the running kernel includes it must be established. This is a **possible cause**, not yet a verified root cause here.

## Safe read-only checks
```bash
mokutil --sb-state
mokutil --test-key /var/lib/shim-signed/mok/MOK.der
modinfo evdi | grep -E 'filename:|signer:|sig_key:|vermagic:'
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
