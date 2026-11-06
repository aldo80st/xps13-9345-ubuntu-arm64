# Local LLM API — XPS 13 9345 ARM64

**Current status: candidate, NOT executed on the XPS.** This PR is independent of the NPU architecture PR #17.

Objective: run an OpenAI-compatible LLM API on localhost using **Ollama v0.40.14** and **qwen3.5:0.8b**. This first stable baseline is CPU-based; it does not claim Hexagon NPU acceleration.

The installer is non-root and installs only under the current user's home directory. It verifies the official Linux ARM64 release's SHA-256 prior to extraction, creates a systemd *user* unit with automatic restart, disables remote/cloud inference, binds only 127.0.0.1, pulls the model, and performs real HTTP tests. It leaves firmware, drivers, FastRPC, system services, firewall and network settings untouched.

Usage (only on the XPS and once remote access works):

- bash scripts/local-llm-api.sh install
- bash scripts/local-llm-api.sh verify
- bash scripts/local-llm-api.sh status
- bash scripts/local-llm-api.sh rollback

**Acceptance pending execution:** HTTP 200 from /api/version, model listed on /v1/models, three real POST /v1/chat/completions requests with non-empty content, successful SSE stream ending [DONE], listening only on localhost, and repeat success after restarting the user service. The user service starts at login; persistent availability while logged out requires additional approval to enable linger. API has no authentication: never expose it to LAN or Tailscale without a separate access design.

**Rollback:** stops and removes the managed unit, retains the binary and downloaded model data for inspection. Nothing is merged or deployed automatically.

**Release source:** https://github.com/ollama/ollama/releases/tag/v0.40.14

**Pinned sha256:** 39bb333b7b4c0bafcdd7fad35eab1ae9aaf4518ea0f2c731de4376e3a29c94d0

**Model:** https://ollama.com/library/qwen3.5

**Reference:** https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx
