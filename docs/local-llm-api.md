# Local LLM API — XPS 13 9345 ARM64

**Current status: verified locally on the XPS (2026-11-06).** The Ollama service and model were already present when the resumed live session began. The validation below was directly executed against the live API. This PR remains independent of NPU architecture PR #17.

Objective: run an OpenAI-compatible LLM API on localhost using **Ollama v0.40.14** and **qwen3.5:0.8b**. This first stable baseline is CPU-based; it does not claim Hexagon NPU acceleration.

The installer is non-root and installs only under the current user's home directory. It verifies the official Linux ARM64 release's SHA-256 prior to extraction, creates a systemd *user* unit with automatic restart, disables remote/cloud inference, binds only 127.0.0.1, pulls the model, and performs real HTTP tests. It leaves firmware, drivers, FastRPC, system services, firewall and network settings untouched.

Usage (only on the XPS and once remote access works):

- bash scripts/local-llm-api.sh install
- bash scripts/local-llm-api.sh verify
- bash scripts/local-llm-api.sh status
- bash scripts/local-llm-api.sh rollback

**Acceptance verified on the XPS (2026-11-06):** HTTP 200 from /api/version, model listed on /v1/models, repeated real POST /v1/chat/completions requests with non-empty content, SSE streaming ending in [DONE], bound exclusively to localhost, and recovery after restarting the user service; see the measured evidence below. The user service starts at login; persistent availability while logged out requires additional approval to enable linger. API has no authentication: never expose it to LAN or Tailscale without a separate access design.

**Rollback:** stops and removes the managed unit, retains the binary and downloaded model data for inspection. Nothing is merged or deployed automatically.

**Release source:** https://github.com/ollama/ollama/releases/tag/v0.40.14

**Pinned sha256:** 39bb333b7b4c0bafcdd7fad35eab1ae9aaf4518ea0f2c731de4376e3a29c94d0

**Model:** https://ollama.com/library/qwen3.5

**Reference:** https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx

## Evidencia de aceptación ejecutada en XPS — 2026-11-06

**Método:** SSH-equivalente Desktop Commander en Dell XPS 13 9345, Ubuntu ARM64, no simulación. Se usó Python stdlib `urllib.request` contra localhost. No se registraron credenciales, nombres reales de dispositivos ni salidas de diagnóstico completas.

| Verificación | Resultado medido |
| --- | --- |
| GET `/api/version` | `{"version":"0.40.14"}` |
| GET `/v1/models` | `qwen3.5:0.8b` presente |
| POST `/v1/chat/completions` (3 intentos) | **PASS 3/3**, respuestas de texto `cuatro` |
| Latencias POST sucesivas | 3.76 s, 0.39 s y 1.28 s (una sola muestra, no benchmark) |
| POST `/v1/chat/completions` SSE | **PASS**, 3 eventos y terminador `[DONE]`; 0.22 s |
| `systemd --user restart ollama-local.service` | **PASS**, PID nuevo y servicio `active/running` |
| GET `/api/version` después del reinicio | **PASS** |
| POST después del reinicio | **PASS**, salida de texto no vacía; 12.03 s (el modelo no respetó exactamente la forma pedida) |
| Enlace de escucha | **127.0.0.1:11434**, sin escucha detectada fuera del loopback |
| Estado systemd final | `enabled`, `active`, `Result=success`, `NRestarts=0` |
| Modelo residente | `qwen3.5:0.8b`, `size_vram=0` según `GET /api/ps` |

**Criterio de aceptación:** servicio local funcional, tres llamadas HTTP sucesivas, streaming y recuperación de reinicio **satisfechos**. La ausencia de VRAM según Ollama concuerda con ejecución sin GPU, pero no es una traza independiente de colocación de todos los operadores. **No** se verificó inferencia en NPU.

**Límites de evidencia:** no se ha efectuado prueba de estrés, disponibilidad extendida, reinicio completo de Ubuntu ni acceso al servidor tras cierre de sesión. Esta evidencia no demuestra SLA 24/7. La instancia observada ya estaba instalada a las 14:57 hora local; no volver a instalarla si funciona. No se realizó merge, modificación de firmware, FastRPC o puertos remotos.

**Operación:** `systemctl --user status ollama-local.service` y `curl http://127.0.0.1:11434/api/version`. La API puede consumirse por clientes locales con base URL `http://127.0.0.1:11434/v1`, sin exponerla a la red. No configurar `linger` ni proxy de autenticación sin autorización adicional.

## Retest de estabilidad y recuperación — 2026-11-06

**Observación adicional (hora local Chihuahua 15:34–15:37):** prueba independiente sobre el servicio existente sin reinstalar Ollama ni modificar FastRPC, kernel, firmware o red.

| Verificación | Evidencia |
| --- | --- |
| Servicio antes de prueba | `active/running`, Ollama `0.40.14`, `qwen3.5:0.8b` disponible |
| Escucha | `127.0.0.1:11434`, sin dirección no-loopback |
| Inferencia antes del reinicio | 3/3 HTTP 200 y respuestas de texto no vacías (0.76, 0.14, 0.21 s) |
| Streaming antes del reinicio | SSE con terminador `[DONE]`, PASS |
| Reinicio del servicio | `systemctl --user restart ollama-local.service`, completado sin errores; PID renovado |
| API tras el reinicio | GET `/api/version` 200, modelo presente en `/v1/models` |
| Inferencias consecutivas después de reiniciar | **6/6 PASS** (respuestas HTTP 200 no vacías) |
| Latencias post-reinicio | 18.22, 21.95, 25.40, 14.82, 13.64, 22.93 s; **no** confundir con benchmark de rendimiento |
| Streaming después del reinicio | 125 eventos SSE y terminador `[DONE]`, exit code 0 |
| Estado final | `ActiveState=active`, `SubState=running`, `UnitFileState=enabled`, `NRestarts=0`, `Result=success` |
| Backend | `size_vram=0`; ninguna prueba de ejecución Hexagon NPU |

**Dictamen:** la API OpenAI-compatible cumple el hito de **funcionalidad y recuperación local** con las pruebas efectuadas. Las respuestas largas y las latencias variables del modelo pequeño justifican pruebas posteriores de calidad y optimización, pero no invalidan la disponibilidad funcional medida. **Límite:** no se ha probado disponibilidad durante días, concurrencia, reinicio completo del equipo, suspensión ni servicio persistente sin sesión de usuario. No declarar SLA 24/7 ni NPU habilitada.

No se abrió un endpoint de red, no se hizo merge ni hubo intervención sobre dispositivos DSP.
