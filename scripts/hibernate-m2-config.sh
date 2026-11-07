#!/usr/bin/env bash
# M2 Kconfig harness: run `make olddefconfig` in a sandboxed container against a
# read-only Ubuntu source tree and a read-only baseline config. Writes ONLY to --output.
# Exit codes: 0 ok | 2 usage | 3 bad/unsafe path or arg | 4 docker unavailable/image missing
#             5 container tool/version check failed | 6 olddefconfig failed
#             7 audit reported drift/failure | 8 harness internal error
set -euo pipefail

EXP_GCC=15.3 EXP_RUST=1.97.1 EXP_BINDGEN=0.72.1 EXP_PAHOLE=1.31 EXP_LLVM=22
DOCKER="${HIBERNATE_M2_DOCKER:-docker}"

usage() {
  cat >&2 <<USAGE
usage: $0 --source DIR --baseline FILE --output DIR --image IMAGE [--audit SCRIPT.py]
  --source    Ubuntu 7.3.0-10.10 kernel source tree (mounted read-only)
  --baseline  baseline config, e.g. /boot/config-7.3.0-10-generic (mounted read-only, never modified)
  --output    scratch dir; path must contain a ".local" component; created if absent
  --image     local image built from container/Dockerfile.hibernate-kconfig
  --audit     optional host audit script (scripts/audit-hibernate-config.py); nonzero => exit 7
USAGE
  exit $([ "${HELP:-0}" = 1 ] && echo 0 || echo 2)
}
die() { local c=$1; shift; echo "hibernate-m2-config: $*" >&2; exit "$c"; }

SOURCE="" BASELINE="" OUTPUT="" IMAGE="" AUDIT=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) HELP=1; usage;;
    --source|--baseline|--output|--image|--audit)
      [ $# -ge 2 ] || { echo "missing value for $1" >&2; usage; }
      case "$1" in
        --source) SOURCE=$2;; --baseline) BASELINE=$2;; --output) OUTPUT=$2;;
        --image) IMAGE=$2;; --audit) AUDIT=$2;;
      esac; shift 2;;
    *) echo "unknown argument: $1" >&2; usage;;
  esac
done
[ -n "$SOURCE" ] && [ -n "$BASELINE" ] && [ -n "$OUTPUT" ] && [ -n "$IMAGE" ] || { echo "--source, --baseline, --output, --image are required" >&2; usage; }

safe_path() { # conservative charset: no spaces, quotes, commas, colons, shell/mount metachars
  [[ "$1" =~ ^/[A-Za-z0-9._/+@-]+$ ]] || die 3 "unsafe or non-absolute path: $1"
  case "/$1/" in */../*) die 3 "path traversal not allowed: $1";; esac
}
for p in "$SOURCE" "$BASELINE" "$OUTPUT"; do safe_path "$p"; done
[[ "$IMAGE" =~ ^[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?$ ]] || die 3 "invalid image name"

[ -d "$SOURCE" ] || die 3 "source is not a directory: $SOURCE"
[ -f "$BASELINE" ] || die 3 "baseline not a file: $BASELINE"
SOURCE=$(realpath -e -- "$SOURCE"); BASELINE=$(realpath -e -- "$BASELINE")
[ ! -e "$SOURCE/.config" ] || die 3 "source tree contains .config (in-tree config would pollute O= build)"
case "/$OUTPUT/" in */.local/*) ;; *) die 3 "--output must be under a .local directory";; esac
OUT_RESOLVED=$(realpath -m -- "$OUTPUT")
case "/$OUT_RESOLVED/" in */.local/*) ;; *) die 3 "--output resolves outside .local";; esac
case "$OUT_RESOLVED/" in /boot/*|/etc/*|/usr/*|/proc/*|/sys/*|/dev/*|/efi/*|/var/lib/*) die 3 "refusing system output path";; esac
case "$OUT_RESOLVED/" in "$SOURCE"/*) die 3 "output must not be inside source";; esac
if [ -n "$AUDIT" ]; then
  safe_path "$AUDIT"; [ -f "$AUDIT" ] || die 3 "audit script not found: $AUDIT"
  command -v python3 >/dev/null || die 3 "python3 required for --audit"
fi

command -v "$DOCKER" >/dev/null 2>&1 || die 4 "docker not found ($DOCKER)"
"$DOCKER" image inspect "$IMAGE" >/dev/null 2>&1 || die 4 "image not present locally: $IMAGE (build container/Dockerfile.hibernate-kconfig first; no auto pull)"

mkdir -p -- "$OUT_RESOLVED"
OUT_RESOLVED=$(realpath -e -- "$OUT_RESOLVED")
BASE_SHA_BEFORE=$(sha256sum -- "$BASELINE" | cut -d' ' -f1)
rm -f -- "$OUT_RESOLVED/.config" "$OUT_RESOLVED/versions.txt" "$OUT_RESOLVED/make.log" "$OUT_RESOLVED/manifest.txt"

# Fixed inner script: user data enters only via environment variables, never interpolated.
read -r -d '' INNER <<'INNER_EOF' || true
set -eu
fail() { echo "TOOLCHAIN CHECK FAILED: $*" >&2; exit 5; }
need() { command -v "$1" >/dev/null 2>&1 || fail "missing tool: $1"; }
for t in aarch64-linux-gnu-gcc rustc bindgen clang pahole bison flex m4 make; do need "$t"; done
v_gcc=$(aarch64-linux-gnu-gcc --version | head -1)
v_rust=$(rustc --version); v_bg=$(bindgen --version); v_cl=$(clang --version | head -1)
v_ph=$(pahole --version)
case "$v_gcc" in *" $EXP_GCC"*|*"$EXP_GCC."*) ;; *) fail "gcc: $v_gcc (want $EXP_GCC)";; esac
case "$v_rust" in "rustc $EXP_RUST "*) ;; *) fail "rustc: $v_rust (want $EXP_RUST)";; esac
case "$v_bg" in *"$EXP_BINDGEN"*) ;; *) fail "bindgen: $v_bg (want $EXP_BINDGEN)";; esac
case "$v_cl" in *"version $EXP_LLVM."*) ;; *) fail "clang: $v_cl (want $EXP_LLVM)";; esac
case "$v_ph" in *"$EXP_PAHOLE"*) ;; *) fail "pahole: $v_ph (want $EXP_PAHOLE)";; esac
[ -d "$RUST_LIB_SRC/core" ] || fail "RUST_LIB_SRC invalid: $RUST_LIB_SRC"
ls "$LIBCLANG_PATH"/libclang*.so* >/dev/null 2>&1 || fail "libclang not found in $LIBCLANG_PATH"
{ echo "$v_gcc"; echo "$v_rust"; echo "$v_bg"; echo "$v_cl"; echo "$v_ph"
  echo "RUST_LIB_SRC=$RUST_LIB_SRC"; echo "LIBCLANG_PATH=$LIBCLANG_PATH"
  bison --version | head -1; flex --version; m4 --version | head -1; } > /out/versions.txt
cp /baseline/config /out/.config
# Enable hibernation ONLY in the staging copy; baseline and source are never edited.
unset_n=$(grep -c '^# CONFIG_HIBERNATION is not set$' /out/.config || true)
any_n=$(grep -c '^\(# \)\?CONFIG_HIBERNATION[= ]' /out/.config || true)
[ "$unset_n" -eq 1 ] && [ "$any_n" -eq 1 ] || { echo "CONFIG_HIBERNATION line missing or ambiguous (unset=$unset_n any=$any_n)" >&2; exit 5; }
sed -i 's/^# CONFIG_HIBERNATION is not set$/CONFIG_HIBERNATION=y/' /out/.config
grep -qx 'CONFIG_HIBERNATION=y' /out/.config || { echo "failed to set CONFIG_HIBERNATION=y" >&2; exit 5; }
make -C /src O=/out ARCH=arm64 CC=aarch64-linux-gnu-gcc HOSTCC=gcc \
  RUSTC="$RUSTC" BINDGEN="$BINDGEN" RUST_LIB_SRC="$RUST_LIB_SRC" LIBCLANG_PATH="$LIBCLANG_PATH" \
  olddefconfig > /out/make.log 2>&1 || { tail -n 30 /out/make.log >&2; exit 6; }
INNER_EOF

set +e
"$DOCKER" run --rm --pull never \
  --network none --cap-drop ALL --security-opt no-new-privileges \
  --read-only --tmpfs /tmp:rw,size=256m,mode=1777 \
  --user "$(id -u):$(id -g)" --pids-limit 256 --memory 2g \
  -v "$SOURCE:/src:ro" \
  -v "$BASELINE:/baseline/config:ro" \
  -v "$OUT_RESOLVED:/out:rw" \
  -e EXP_GCC="$EXP_GCC" -e EXP_RUST="$EXP_RUST" -e EXP_BINDGEN="$EXP_BINDGEN" \
  -e EXP_PAHOLE="$EXP_PAHOLE" -e EXP_LLVM="$EXP_LLVM" -e HOME=/tmp \
  "$IMAGE" bash -c "$INNER"
rc=$?
set -e
code=8; [ "$rc" -eq 5 ] && code=5; [ "$rc" -eq 6 ] && code=6
[ "$rc" -eq 0 ] || die "$code" "container run failed (rc=$rc)"

BASE_SHA_AFTER=$(sha256sum -- "$BASELINE" | cut -d' ' -f1)
[ "$BASE_SHA_BEFORE" = "$BASE_SHA_AFTER" ] || die 8 "baseline changed during run"
CAND_SHA=$(sha256sum -- "$OUT_RESOLVED/.config" | cut -d' ' -f1)
{
  echo "image=$IMAGE"
  echo "source=$SOURCE"
  echo "baseline=$BASELINE"
  echo "baseline_sha256=$BASE_SHA_AFTER"
  echo "candidate=$OUT_RESOLVED/.config"
  echo "candidate_sha256=$CAND_SHA"
  echo "image_id=$("$DOCKER" image inspect --format '{{.Id}}' "$IMAGE")"
  echo "note=olddefconfig dependency resolution only; not proof of hibernation"
} > "$OUT_RESOLVED/manifest.txt"
echo "olddefconfig OK: $OUT_RESOLVED/.config (manifest.txt, versions.txt, make.log alongside)"

if [ -n "$AUDIT" ]; then
  set +e
  python3 -I -- "$AUDIT" --baseline "$BASELINE" --candidate "$OUT_RESOLVED/.config" --json | tee "$OUT_RESOLVED/audit.json"
  arc=${PIPESTATUS[0]}
  set -e
  [ "$arc" -eq 0 ] || die 7 "audit exited $arc (exit 1 = unrelated drift; other = error); see $OUT_RESOLVED/audit.json"
else
  echo "no --audit given: drift NOT evaluated" >&2
fi
exit 0
