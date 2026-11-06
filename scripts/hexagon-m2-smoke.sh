#!/usr/bin/env bash
# User-local FastRPC+GenieX QAIRT smoke. Never modifies firmware or device ACLs.
set -Eeuo pipefail
action="${1:-preflight}"
HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="$HOME/labs/xps13-9345-hexagon"
GENIEX="$LAB/geniex/v0.10.0"
python3 "$HERE/hexagon-m2-preflight.py"
if test "$action" = preflight; then
  echo "Only static validation performed."
  exit 0
fi
if test "$action" != infer; then
  echo "Usage: $0 {preflight|infer}" >&2
  exit 2
fi
for node in /dev/fastrpc-cdsp /dev/dma_heap/system; do
  test -r "$node" && test -w "$node" || {
    echo "BLOCKED: temporary local ACL is required on $node" >&2
    exit 3
  }
done
test -x "$GENIEX/geniex" || { echo "GenieX missing" >&2; exit 4; }
test -e "$LAB/fastrpc/src/.libs/libcdsprpc.so" || { echo "FastRPC missing" >&2; exit 4; }
export LD_LIBRARY_PATH="$GENIEX:$GENIEX/qairt:$GENIEX/qairt/htp-files:$LAB/fastrpc/src/.libs"
# Requires specific risk acknowledgement: a previous QNN test crashed CDSP.
if [[ "${CONFIRM_CDSP_CRASH_RISK:-}" != "YES" ]]; then
  echo "BLOCKED: previous QNN inference crashed CDSP; stop before hardware call." >&2
  echo "Do not retry until hardware/kernel mitigation has been evaluated." >&2
  exit 5
fi
[[ -f "$LAB/install/qcom/conf.d/xps13-9345.yaml" ]] || {
  echo "BLOCKED: board YAML missing" >&2
  exit 6
}
[[ -r "$LAB/install/qcom/dsp/cdsp/fastrpc_shell_unsigned_3" ]] || {
  echo "BLOCKED: matching shell missing" >&2
  exit 6
}
# FastRPC uses semicolon-delimited search paths and CONFIG_BASE_DIR YAML.
export DSP_LIBRARY_PATH="$LAB/install/qcom/dsp/cdsp;$GENIEX/qairt/htp-files"
export ADSP_LIBRARY_PATH="$DSP_LIBRARY_PATH"
export GENIEX_DATADIR="$LAB/geniex/models"
echo "QAIRT-only Qwen3-0.6B w4a16, NPU requested. CPU fallback not available for QAIRT."
timeout --signal=TERM 180 "$GENIEX/geniex" --skip-update --log info infer \
  qualcomm/Qwen3-0.6B:w4a16 --compute npu --think=false \
  --max-tokens 32 --prompt "Responde solamente: cuatro"
