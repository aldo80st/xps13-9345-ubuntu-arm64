# XPS AUTHZ v1.1 M3 diagnostic installer

The installer stages a local diagnostic channel. The reviewed payload must provide diagnostic IPC only. Activation, privilege grants, and G-ID acceptance are separate gates.

## Build after payload approval

Run the builder as an unprivileged user from the reviewed checkout. Supply a trusted JSON manifest with exactly these keys and their reviewed lowercase 64-digit SHA-256 values:

| Source | Destination |
| --- | --- |
| `scripts/xps_authz_ipc.py` | `/usr/local/libexec/xps-authz-diagnostic/xps_authz_ipc.py` |
| `scripts/xps_authz_diagnostic.py` | `/usr/local/libexec/xps-authz-diagnostic/xps_authz_diagnostic.py` |
| `deploy/xps-authz-diagnostic/xps-authz-diagnostic@.service` | `/etc/systemd/system/xps-authz-diagnostic@.service` |
| `deploy/xps-authz-diagnostic/xps-authz-diagnostic.socket` | `/etc/systemd/system/xps-authz-diagnostic.socket` |

Approve the diagnostic code's pin to the reviewed IPC bytes from main, the NSS assumptions, and the service's use of the fixed libexec path before issuing the manifest. Review the units for disabled, diagnostic-only staging. Pass the reviewed manifest to the builder instead of generating it from the current checkout.

```sh
python3 -B scripts/build_xps_authz_diagnostic_installer.py \
  --manifest /absolute/path/to/reviewed-manifest.json \
  --output /absolute/private/path/xps-authz-diagnostic-installer.py
```

The builder reads the four named sources and checks every digest before creating the exclusive output file. Identical reviewed source bytes produce identical installer bytes. Record the printed artifact SHA-256 in the approval record and give the owner that digest through the trusted review channel.

## Owner execution after artifact approval

In a locally authenticated root session on the Dell XPS 13 9345 running Linux aarch64 `7.3.0-11-generic`, verify that the socket and all template instances are inactive and that there are no existing definitions or enablement links for those names. Inspect the read-only output of `systemctl list-units --all 'xps-authz-diagnostic*'` and `systemctl list-unit-files 'xps-authz-diagnostic*'`. Proceed only on a fresh diagnostic installation when both checks confirm absence. Keep concurrent unit and account administration paused during this operation.

Set the two variables below to the approved artifact SHA-256 and the local copy's absolute path. Copy the artifact into a fresh root-private directory, verify the copied bytes, and execute that copy only if verification succeeds.

```sh
approved_sha256='REPLACE_WITH_APPROVED_64_DIGIT_SHA256'
source='/absolute/path/to/xps-authz-diagnostic-installer.py'
umask 077
stage=$(/usr/bin/mktemp -d /root/xps-authz-diagnostic.XXXXXXXX) &&
  /usr/bin/install -o root -g root -m 0600 -- "$source" "$stage/installer.py" &&
  printf '%s  %s\n' "$approved_sha256" "$stage/installer.py" |
    /usr/bin/sha256sum --check --strict - &&
  /usr/bin/env -i /usr/bin/python3 -I -S "$stage/installer.py" --install-diagnostic-only
```

The installer verifies the host pin, embedded digests, root-owned protected directory ancestors, absent destinations, absent runtime socket, and absent account and group. It uses the host's trusted local account tooling and NSS policy. It creates a system account with its own primary group and validates the resulting NSS identity against root and the pinned owner UID 1000 and the owner's primary GID. It stages root-owned files using exclusive creation. The procedure issues no daemon reload, enable, or start command.

Capture the exit status and effect messages locally. A failure can leave account database changes, a runtime directory, or full or partial files. A timeout can leave account or group records, as reported by the post-command NSS checks. Preserve staged effects for reviewed cleanup and confirm service inactivity with the read-only checks above. Retrying over existing effects is refused.

**Ordering:** For a fresh XPS, this installer is the account-creation step of M1/S4; do not create the account separately before running it. If xps-agent already exists, stop and reconcile explicitly.
