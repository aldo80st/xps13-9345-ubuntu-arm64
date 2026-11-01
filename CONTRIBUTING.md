# Contributing / Contribuciones

Report bugs and verified fixes using [the validation template](docs/report-template.md).
Use a new issue for each independent symptom or root cause and cross-link upstream reports.
For changes, submit a PR with a reversible procedure, source of the firmware/package, checksums and before/after test evidence.

## Privacy and security
- Remove hostnames, usernames, serial numbers, service tags, MAC/IP addresses and private paths.
- **Never** upload raw hardware firmware binaries, keys, certificates with sensitive metadata, BitLocker recovery secrets or complete unfiltered logs.
- Do not propose disabling Secure Boot or shim validation as the default fix.
- If not tested on the XPS 9345, label the claim as hypothesis or unverified candidate.
- Keep community binaries outside git; scripts should download from upstream/vendor sources and verify cryptographic checksums.

## State semantics
- Observed: directly measured.
- Candidate: prepared but not applied.
- Tested: attempted, with reproducible evidence.
- Verified: actual device functionality works after reboot and rollback is documented.
- Regressed: functionality broke after a change and rollback was tested.

Español: cualquier contribución debe distinguir hechos medidos de hipótesis, respetar la privacidad y permitir revertir los cambios.
