#!/usr/bin/env bash
# H2: offline object + DTB only. Inputs are never mounted writable.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
DOCKER=${HIBERNATE_H2_DOCKER:-docker}
die() { local rc=$1; shift; echo "hibernate-ec-build-h2: $*" >&2; exit "$rc"; }
usage() {
    echo 'usage: hibernate-ec-build-h2.sh --source DIR --config FILE --output NEW_DIR --image IMAGE [--baseline FILE]' >&2
}
SOURCE= CONFIG= OUTPUT= IMAGE= BASELINE=
while (($#)); do
    case "$1" in
        --help|-h) usage; exit 0;;
        --source|--config|--output|--image|--baseline)
            (($# >= 2)) && [[ -n $2 && $2 != --* ]] || { usage; exit 2; }
            case "$1" in
                --source) SOURCE=$2;; --config) CONFIG=$2;; --output) OUTPUT=$2;;
                --image) IMAGE=$2;; --baseline) BASELINE=$2;;
            esac
            shift 2;;
        *) usage; exit 2;;
    esac
done
[[ -n $SOURCE && -n $CONFIG && -n $OUTPUT && -n $IMAGE ]] || { usage; exit 2; }
safe_path() {
    [[ $1 =~ ^/[A-Za-z0-9._/+@-]+$ && /$1/ != */../* ]] || die 3 'unsafe absolute path'
}
for p in "$SOURCE" "$CONFIG" "$OUTPUT"; do safe_path "$p"; done
[[ $IMAGE =~ ^[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?$ ]] || die 3 'invalid image'
[[ -d $SOURCE && -f $CONFIG ]] || die 3 'source/config missing'
SOURCE=$(realpath -e -- "$SOURCE")
CONFIG=$(realpath -e -- "$CONFIG")
safe_path "$SOURCE"; safe_path "$CONFIG"
[[ ! -e $SOURCE/.config ]] || die 3 'source contains in-tree .config'
for f in Makefile drivers/platform/arm64/dell-xps-ec.c arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts; do
    [[ -f $SOURCE/$f ]] || die 3 "missing source file: $f"
done
[[ ! -e $OUTPUT && ! -L $OUTPUT ]] || die 3 'output must be new'
OUTPUT=$(realpath -m -- "$OUTPUT")
safe_path "$OUTPUT"
case "$OUTPUT" in "$ROOT/.local/"*) ;; *) die 3 'output must resolve under repository .local';; esac
case "$OUTPUT/" in "$SOURCE/"*|"$CONFIG/"*) die 3 'output overlaps input';; esac
if [[ -n $BASELINE ]]; then
    safe_path "$BASELINE"
    [[ -f $BASELINE ]] || die 3 'baseline missing'
    BASELINE=$(realpath -e -- "$BASELINE")
    safe_path "$BASELINE"
fi
# Reuse M3's strict relevant-symbol parser and SCMI contract; no Kconfig edits.
python3 -I - "$ROOT" "$CONFIG" "$BASELINE" <<'PY' || die 3 'config contract failed'
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('m3', Path(sys.argv[1]) / 'scripts/hibernate-thermal-m3-gate.py')
m3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m3)
cfg = m3._kconfig(Path(sys.argv[2]))
required = {**m3.SCMI_REQUIRED, 'CONFIG_EC_DELL_XPS': 'm', 'CONFIG_HIBERNATION': 'y'}
if cfg is None or any(cfg.get(k) != v for k, v in required.items()):
    raise SystemExit(1)
if sys.argv[3]:
    baseline = m3._kconfig(Path(sys.argv[3]))
    if baseline is None or any(baseline.get(k) != v for k, v in m3.SCMI_REQUIRED.items()):
        raise SystemExit(1)
PY
command -v "$DOCKER" >/dev/null || die 4 'docker unavailable'
IMAGE_ID=$("$DOCKER" image inspect --format '{{.Id}}' "$IMAGE") || die 4 'local image missing; no pull'
[[ $IMAGE_ID == sha256:* ]] || die 4 'missing image identity'
# mkdir without -p for the final component refuses an existing output atomically.
mkdir -p -- "$(dirname -- "$OUTPUT")"
mkdir -m 700 -- "$OUTPUT" || die 3 'output creation failed'
[[ $(realpath -e -- "$OUTPUT") == "$OUTPUT" ]] || die 3 'output resolution changed'
BUILD="$OUTPUT/build"
mkdir -m 700 -- "$BUILD"
CONFIG_SHA=$(sha256sum -- "$CONFIG" | cut -d' ' -f1)
BASE_SHA=
[[ -z $BASELINE ]] || BASE_SHA=$(sha256sum -- "$BASELINE" | cut -d' ' -f1)
{
    echo 'status=started; not build acceptance'
    echo "image=$IMAGE"; echo "image_id=$IMAGE_ID"
    echo "source=$SOURCE"; echo "config=$CONFIG"; echo "config_sha256=$CONFIG_SHA"
    echo "baseline=$BASELINE"; echo "baseline_sha256=$BASE_SHA"
    echo "source_makefile_sha256=$(sha256sum -- "$SOURCE/Makefile" | cut -d' ' -f1)"
    echo "source_ec_sha256=$(sha256sum -- "$SOURCE/drivers/platform/arm64/dell-xps-ec.c" | cut -d' ' -f1)"
    echo "source_dts_sha256=$(sha256sum -- "$SOURCE/arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts" | cut -d' ' -f1)"
    echo 'targets=modules_prepare drivers/platform/arm64/dell-xps-ec.o qcom/x1e80100-dell-xps13-9345.dtb'
    echo 'source_identity=selected file hashes only; not a full source-tree attestation'
} > "$OUTPUT/manifest.txt"
read -r -d '' INNER <<'INNER_EOF' || true
set -euo pipefail
umask 022
for t in make gcc aarch64-linux-gnu-gcc aarch64-linux-gnu-ld aarch64-linux-gnu-as bison flex bc perl python3 rustc bindgen clang pahole; do
    command -v "$t" >/dev/null || { echo "missing build tool: $t" >&2; exit 5; }
done
{
    uname -m
    gcc --version
    aarch64-linux-gnu-gcc --version
    aarch64-linux-gnu-ld --version
    rustc --version; bindgen --version; clang --version; pahole --version
    cat /etc/hibernate-kconfig-packages.txt
    cat /etc/hibernate-ec-build-h2-packages.txt
} > /out/versions.txt
cp /input/config /out/.config
export KCONFIG_NOSILENTUPDATE=1
build() {
    make -C /src O=/out ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
        CC=aarch64-linux-gnu-gcc HOSTCC=gcc \
        RUSTC="$RUSTC" BINDGEN="$BINDGEN" RUST_LIB_SRC="$RUST_LIB_SRC" \
        LIBCLANG_PATH="$LIBCLANG_PATH" -j1 "$@"
}
build modules_prepare
cmp /input/config /out/.config
build drivers/platform/arm64/dell-xps-ec.o
build qcom/x1e80100-dell-xps13-9345.dtb
cmp /input/config /out/.config
for f in drivers/platform/arm64/dell-xps-ec.o arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dtb; do
    test -s "/out/$f"
    sha256sum "/out/$f"
done > /out/artifacts.sha256
INNER_EOF
set +e
"$DOCKER" run --rm --pull never --network none --read-only \
    --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" --pids-limit 256 --memory 2g --memory-swap 2g \
    --tmpfs /tmp:rw,size=256m,mode=1777 \
    -v "$SOURCE:/src:ro" -v "$CONFIG:/input/config:ro" -v "$BUILD:/out:rw" \
    -e HOME=/tmp "$IMAGE_ID" bash -c "$INNER" > "$OUTPUT/make.log" 2>&1
rc=$?
set -e
echo "container_exit=$rc" >> "$OUTPUT/manifest.txt"
[[ $(sha256sum -- "$CONFIG" | cut -d' ' -f1) == "$CONFIG_SHA" ]] || die 6 'input config changed'
[[ -z $BASELINE || $(sha256sum -- "$BASELINE" | cut -d' ' -f1) == "$BASE_SHA" ]] || die 6 'baseline changed'
[[ $rc == 0 ]] || die 6 "container failed ($rc); inspect $OUTPUT/make.log"
[[ -s $BUILD/drivers/platform/arm64/dell-xps-ec.o && -s $BUILD/arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dtb && -s $BUILD/artifacts.sha256 ]] || die 6 'missing artifacts'
cmp -- "$CONFIG" "$BUILD/.config" || die 6 'output config drift'
echo 'status=object-and-dtb-built; no runtime acceptance' >> "$OUTPUT/manifest.txt"
echo "H2 object and DTB built: $OUTPUT (no runtime acceptance)"
