# Original Ubuntu kernel source — test fixture

This directory contains **unchanged** `load_uefi.c` and `efi_parser.c` from the official Ubuntu
26.10 `linux-source-7.3.0` package, version **7.3.0-10.10**, and a copy of the
GNU GPL version 2 under `COPYING`. The source retains its
`SPDX-License-Identifier: GPL-2.0` header. This copied kernel source is
licensed under the GPL; it is included separately as a testing fixture.

Source location inside the distribution package:
`security/integrity/platform_certs/load_uefi.c`.

SHA-256 of the unchanged `load_uefi.c`:
`2abff60cd5d5fcbdd5dfde3da3ca38bd9a16dbb6b1b3b822c38596ac7128424d`

SHA-256 of the unchanged `efi_parser.c`:
`ceec33b9e14193ad9ef7e191f17bbdb1c6c43f252f07dce1cfb8cdcf877fa1e7`

Tests construct a disposable directory, apply the RFC patch with `patch -p1`,
compile that exact kernel C file using mocked EFI functions and run
failure/permission scenarios in **userspace**. They do **not** alter real
Secure Boot, MOK, firmware, the kernel, GRUB or the Linux keyrings.

This fixture is for deterministic CI only. The mock does not replicate shim
authentication, hardware revocation databases, firmware behavior, or real
kernel keyring enforcement; passing tests do **not** authorize deployment.
