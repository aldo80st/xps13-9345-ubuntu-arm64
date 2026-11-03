# Dell XPS 13 9345 ARM64 — DisplayLink A/B result (2026-11-03)

## Confirmed working state

The owner temporarily **disabled UEFI Secure Boot in Dell firmware** and rebooted Ubuntu. The owner directly confirmed that **both DisplayPort monitors connected to the Dell D6000 now work**. The assistant verified, live on the XPS, at 2026-11-03 15:42:25 -06:00:

```text
uname -r: 7.3.0-10-generic
mokutil --sb-state: SecureBoot disabled
/proc/cmdline: efi=noruntime still present
lsmod: evdi 86016 12  [loaded]
displaylink-driver.service: ActiveState=active, SubState=running
displaylink-driver.service: NRestarts=0, Result=success
USB dock: 17e9:6006 DisplayLink Dell Universal Dock D6000
card0-DVI-I-1: connected [EVDI virtual display]
card2-DVI-I-2: connected [EVDI virtual display]
card1-eDP-1: connected [internal panel]
card1-DP-1: disconnected [native DRM output; unrelated]
card1-DP-2: disconnected [native DRM output; unrelated]
```

Both EVDI virtual connectors expose 1920x1080 among their advertised modes (the mode list alone is not evidence of the currently selected mode). The service log confirms a running DisplayLinkManager and no continuing restart storm; EVDI appears in kernel logs being accessed by user applications.

## Previous non-working control

With **Secure Boot enabled** and `efi=noruntime` active, this *same official signed kernel* was unable to load the signed EVDI module because its MOK was enrolled in shim but absent from the Linux trusted keyrings (`.machine` and `.platform` empty); kernel Lockdown rejected the load. The DisplayLink service entered a restart loop. For details and one-boot EFI Runtime negative experiment, see:

- [Implementation and security notes](evdi-mok-rfc-implementation-20261103.md)
- [Controlled EFI Runtime experiment](efi-runtime-oneboot-result-20261103.md)

## Interpretation

This practical A/B result strongly supports a **Secure Boot module-signature trust-path / MOK integration problem** as the blocker for the previously nonworking monitors. The hardware, ARM64 DisplayLink userland and EVDI are functional when the kernel does not enforce the Secure Boot signing trust policy. It does **not** by itself validate any experimental RFC kernel patch or establish the correct firmware `dbx` revocation semantics.

## Operational state and next actions

- **Temporary workaround active:** Secure Boot disabled, `efi=noruntime` preserved, official kernel unchanged, dock and both external displays working.
- **Security trade-off:** firmware Secure Boot protection is not enforced while this workaround is active. Do not imply that signing/validation is retained.
- **Reversal:** enter Dell BIOS/UEFI with F2 at startup, restore **Enable Secure Boot**, save. With the current kernel, EVDI is expected to be rejected again and the DisplayLink-connected monitors may stop working. There is no automatic restoration.
- **Permanent goal:** a reviewed, correctly signed Ubuntu kernel fix that loads approved MOK into the trusted keyring without weakening the revocation model when `efi=noruntime` is required.
- **Launchpad:** Ubuntu `linux` bug [#2172878](https://bugs.launchpad.net/bugs/2172878).
- **Local handoff:** [GitHub issue #10](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/10) and [PR #9](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/pull/9) track the upstream/security review. RFC v3 is NOT deployed.

No kernel, GRUB, firmware keys, signing keys, installed drivers or boot parameters were changed by the assistant during this verification.
