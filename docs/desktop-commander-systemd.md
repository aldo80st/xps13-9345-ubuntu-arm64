# Persistent Desktop Commander Remote on Ubuntu ARM64 (systemd user service)

> Status: installation and first startup verified with Desktop Commander **0.3.1** on Ubuntu 26.10 / aarch64; **a subsequent handoff between concurrent agents was not successful**. Do not assume reconnection across a duplicated-agent cutover is solved.

## Why

A manual `npx @wonderwhy-er/desktop-commander@latest remote` process is tied to the launching terminal. After reboot the computer can be reachable via Tailscale but its remote MCP agent is unavailable.

## Install a pinned local copy (no sudo)

Use Node.js 22.12+ (the pilot used Node 24). This example pins Desktop Commander **0.3.1**, avoiding automatic changes across restarts:

```bash
mkdir -p "$HOME/.local/share/desktop-commander-remote"
npm install --prefix "$HOME/.local/share/desktop-commander-remote" \
  --ignore-scripts --omit=dev --no-audit --no-fund --save-exact \
  '@wonderwhy-er/desktop-commander@0.3.1'
mkdir -p "$HOME/.config/systemd/user"
```

Assumes `$HOME/.local/bin/node` points to a working Node 22.12+ runtime. Verify with `$HOME/.local/bin/node -v` and adjust the unit if needed.

## User unit

Save as `~/.config/systemd/user/desktop-commander-remote.service`:

```ini
[Unit]
Description=Desktop Commander Remote MCP Agent
StartLimitIntervalSec=600
StartLimitBurst=4

[Service]
Type=exec
WorkingDirectory=%h
Environment=HOME=%h
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=%h/.local/bin/node %h/.local/share/desktop-commander-remote/node_modules/@wonderwhy-er/desktop-commander/dist/index.js remote
Restart=on-failure
RestartSec=35s
TimeoutStopSec=15s
UMask=0077

[Install]
WantedBy=default.target
```

**Security note:** Remote Desktop Commander exposes file and command access under the logged-in user. Keep the device account secured. You may apply `NoNewPrivileges=yes` for a stricter setup, but that also blocks `sudo`/`pkexec` privilege elevation from commands launched inside this unit. Never put tokens in the unit file or publish the local session file.

## Enable and verify

When at the local machine, **stop any existing manually launched remote agent before enabling the unit**; concurrently running agents associated with the same persisted identity can lead to stale presence / offline state on disconnection.

```bash
systemd-analyze --user verify ~/.config/systemd/user/desktop-commander-remote.service
systemctl --user daemon-reload
systemctl --user enable --now desktop-commander-remote.service
systemctl --user is-active desktop-commander-remote.service
systemctl --user status desktop-commander-remote.service --no-pager
```

It starts on user-session login. For startup **before login**, `loginctl enable-linger "$USER"` (administrator authorization) may be needed. This additionally makes the remote agent available whenever the laptop boots and has network connectivity, so decide if that permanent access is acceptable. On the tested laptop `Linger=no`; pre-login startup was **not** configured or tested.

## Handoff issue observed

On 2026-11-01, the systemd service started, reused the authorized device session and reported `Channel subscribed`, `Device marked as online`, `Device ready`. The old terminal-based agent was then terminated. The account dashboard subsequently showed the device offline even though systemd had been active shortly before. This is a **suspected duplicated-instance presence race**, not a proven product defect. The follow-up systemd state could not be remotely read once the cloud relay reported offline.

Local recovery command:

```bash
systemctl --user restart desktop-commander-remote.service
systemctl --user status desktop-commander-remote.service --no-pager
```

If it remains offline, inspect local journal without publishing raw command payloads, verify network and the persisted OAuth device pairing. Do **not** reset/revoke OAuth as the first remedy.

Related upstream issues: [#661 stale persisted remote session](https://github.com/wonderwhy-er/DesktopCommanderMCP/issues/661), [#644 background jobs and systemd cgroups](https://github.com/wonderwhy-er/DesktopCommanderMCP/issues/644).

**Privacy:** the agent may log tool arguments, including command payloads, to the systemd journal. Do not paste raw logs publicly. Consider `StandardOutput=null` or an appropriate logging policy on production systems, retaining enough error visibility for diagnosis.
