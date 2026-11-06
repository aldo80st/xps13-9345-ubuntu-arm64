#!/usr/bin/env bash
# Reversible user-local Ollama API for Ubuntu ARM64. Never runs as root.
set -Eeuo pipefail
umask 077
VERSION=0.40.14
SHA=39bb333b7b4c0bafcdd7fad35eab1ae9aaf4518ea0f2c731de4376e3a29c94d0
URL=https://github.com/ollama/ollama/releases/download/v0.40.14/ollama-linux-arm64.tar.zst
MODEL=qwen3.5:0.8b
ROOT="$HOME/.local/opt/ollama"
DEST="$ROOT/v$VERSION"
CACHE="$HOME/.cache/xps-ollama-api"
MODELS="$HOME/.local/share/ollama/models"
UNIT="$HOME/.config/systemd/user/ollama-local.service"
MARKER="# Managed by xps13-9345-ubuntu-arm64 local-llm-api.sh"
ACTION="$1"
fail() { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || fail "Missing command: $1"; }
owned() { test ! -f "$UNIT" || grep -Fxq "$MARKER" "$UNIT" || fail "Refusing to change unmanaged service"; }
verify() { python3 "$(dirname "$0")/verify-local-llm-api.py" "$MODEL"; }
rollback() {
  owned
  if test -f "$UNIT"; then
    systemctl --user disable --now ollama-local.service
    rm -- "$UNIT"
    systemctl --user daemon-reload
  fi
  echo "Service stopped; binary and model data kept for safe recovery."
}
install() {
  test "$(uname -m)" = aarch64 || fail "Expected Linux aarch64"
  test "$(id -u)" != 0 || fail "Run as regular user"
  for cmd in curl sha256sum tar zstd systemctl python3 ss; do need "$cmd"; done
  systemctl --user show-environment >/dev/null || fail "No systemd user manager"
  owned
  if ! systemctl --user is-active --quiet ollama-local.service; then
    if ss -lntH '( sport = :11434 )' | grep -q .; then fail "Port 11434 in use"; fi
  fi
  mkdir -p "$ROOT" "$CACHE" "$MODELS" "$(dirname "$UNIT")"
  if test ! -x "$DEST/bin/ollama"; then
    file="$CACHE/ollama-linux-arm64-v$VERSION.tar.zst"
    got=""
    if test -f "$file"; then
      got="$(sha256sum "$file" | awk '{print $1}')"
    fi
    if test "$got" != "$SHA"; then
      curl -fL --retry 3 --retry-delay 3 --continue-at - -o "$file" "$URL"
      got="$(sha256sum "$file" | awk '{print $1}')"
    fi
    test "$got" = "$SHA" || fail "Invalid release digest; no extraction"
    stage="$(mktemp -d "$ROOT/.stage.XXXXXXXX")"
    trap 'test -z "$stage" || rm -rf -- "$stage"' EXIT
    tar -I zstd -xf "$file" -C "$stage"
    test -x "$stage/bin/ollama" || fail "Unexpected archive layout"
    mv -- "$stage" "$DEST"
    stage=""
    rm -- "$file"
  fi
  test -x "$DEST/bin/ollama" || fail "Missing executable"
  cat > "$UNIT" <<EOF
$MARKER
[Unit]
Description=Ollama local LLM API (loopback only)
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5
[Service]
Type=simple
ExecStart=$DEST/bin/ollama serve
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_MODELS=$MODELS
Environment=OLLAMA_NO_CLOUD=1
Environment=OLLAMA_VULKAN=0
Environment=OLLAMA_CONTEXT_LENGTH=4096
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_MAX_QUEUE=8
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
UMask=0077
[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable ollama-local.service
  systemctl --user restart ollama-local.service
  ready=0
  for i in $(seq 1 50); do
    if curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  test "$ready" = 1 || fail "HTTP server not ready"
  OLLAMA_HOST=127.0.0.1:11434 "$DEST/bin/ollama" pull "$MODEL"
  verify
  echo "Restarting user service for recovery check..."
  systemctl --user restart ollama-local.service
  ready=0
  for i in $(seq 1 50); do
    if curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  test "$ready" = 1 || fail "Service failed to recover after restart"
  verify
}
case "$ACTION" in
  install) install ;;
  verify) verify ;;
  status) systemctl --user --no-pager --plain status ollama-local.service || true ;;
  rollback) rollback ;;
  *) echo "Usage: $0 {install|verify|status|rollback}"; exit 2 ;;
esac
