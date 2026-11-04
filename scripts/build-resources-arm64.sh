#!/usr/bin/env bash
# Reproducible, user-local GNOME Resources 51.0 Qualcomm ARM64 build.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PATCHES=(
  "$ROOT/patches/resources-51-qualcomm-cpu-metrics.patch"
  "$ROOT/patches/resources-51-qualcomm-adreno-gpu.patch"
  "$ROOT/patches/resources-51-msm-fdinfo.patch"
)
UPSTREAM="https://gitlab.gnome.org/GNOME/Incubator/resources.git"
TAG="51.0"
COMMIT="a44f9a1aecb68b2d893eecffd78112f80b0969c5"
APP_ID="org.gnome.Resources.QualcommTest"
IMAGE="xps-resources-arm64-builder:ubuntu26.10"
PREFIX="${RESOURCES_TEST_PREFIX:-$HOME/.local/opt/resources-qualcomm-51}"
CACHE="${RESOURCES_BUILD_CACHE:-$HOME/.cache/xps-resources-arm64}"
WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "ERROR: this workflow is for an aarch64 host." >&2
  exit 2
fi
required_programs=(git docker)
if [[ "${RESOURCES_CI_ONLY:-0}" != "1" ]]; then
  required_programs+=(glib-compile-schemas)
fi
for program in "${required_programs[@]}"; do
  command -v "$program" >/dev/null || { echo "Missing: $program" >&2; exit 2; }
done
for patch in "${PATCHES[@]}"; do
  [[ -f "$patch" ]] || { echo "Missing patch: $patch" >&2; exit 2; }
done
mkdir -p "$WORK/source" "$WORK/out" "$CACHE/cargo" "$CACHE/target"
if [[ "${RESOURCES_CI_ONLY:-0}" != "1" ]]; then
  mkdir -p "$PREFIX/schema"
fi

if [[ -n "${RESOURCES_SOURCE_REPO:-}" ]]; then
  upstream_sha="$(git -C "$RESOURCES_SOURCE_REPO" rev-list -n 1 "$TAG")"
  [[ "$upstream_sha" == "$COMMIT" ]] || {
    echo "Unexpected $TAG source commit: $upstream_sha" >&2; exit 3;
  }
  git -C "$RESOURCES_SOURCE_REPO" archive "$TAG" | tar -xf - -C "$WORK/source"
else
  git clone --quiet --depth 1 --branch "$TAG" "$UPSTREAM" "$WORK/source"
  upstream_sha="$(git -C "$WORK/source" rev-parse HEAD)"
  [[ "$upstream_sha" == "$COMMIT" ]] || {
    echo "Unexpected $TAG source commit: $upstream_sha" >&2; exit 3;
  }
fi
for patch in "${PATCHES[@]}"; do
  git -C "$WORK/source" apply --check "$patch"
  git -C "$WORK/source" apply "$patch"
done

docker build -t "$IMAGE" -f "$ROOT/containers/resources-arm64/Dockerfile" "$ROOT"
docker run --rm --user "$(id -u):$(id -g)" --cap-drop=ALL \
  --security-opt no-new-privileges \
  -v "$WORK:/src:rw" -v "$CACHE:/cache:rw" \
  -e HOME=/tmp -e CARGO_HOME=/cache/cargo -e CARGO_TARGET_DIR=/cache/target \
  -e APP_ID="$APP_ID" -e GETTEXT_PACKAGE=resources -e DEVLOPMENT_BUILD=false \
  -e VERSION=51.0.0 -e LOCALEDIR=/usr/share/locale \
  -e LIBEXECDIR="$PREFIX" \
  -e RESOURCES_FILE="$PREFIX/resources.gresource" \
  "$IMAGE" sh -ec '
    cd /src/source
    cargo fmt --all -- --check
    cargo test --locked --all-targets
    # The process-data library is a standalone Cargo package; the root test
    # command above does NOT execute its unit tests.
    cargo test --locked --manifest-path lib/process_data/Cargo.toml --all-targets
    cargo build --locked --bins
    glib-compile-resources --sourcedir=data/resources \
      --target=/src/out/resources.gresource data/resources/resources.gresource.xml
    cp /cache/target/debug/resources /src/out/resources-test
    for helper in resources-processes resources-adjust resources-kill; do
      cp "/cache/target/debug/$helper" "/src/out/$helper"
    done
  '

# In CI, validate build artifacts and tests without installing a desktop
# launcher or writing into a host user's GNOME profile.
if [[ "${RESOURCES_CI_ONLY:-0}" == "1" ]]; then
  test -s "$WORK/out/resources-test"
  test -s "$WORK/out/resources.gresource"
  test -s "$WORK/out/resources-processes"
  echo "PASS: Resources 51.0 source=$COMMIT (CI, Qualcomm CPU + Adreno + MSM process telemetry)"
  sha256sum "$WORK/out/resources-test" "$WORK/out/resources.gresource"
  exit 0
fi

sed -e "s/@app-id@/$APP_ID/g" \
    -e 's/@gettext-package@/resources/g' \
    -e 's@path="/org/gnome/Resources/"@path="/org/gnome/Resources/QualcommTest/"@' \
    "$WORK/source/data/org.gnome.Resources.gschema.xml.in" \
    > "$WORK/out/$APP_ID.gschema.xml"
install -m 755 "$WORK/out/resources-test" "$PREFIX/resources-test"
for helper in resources-processes resources-adjust resources-kill; do
  install -m 755 "$WORK/out/$helper" "$PREFIX/$helper"
done
install -m 644 "$WORK/out/resources.gresource" "$PREFIX/resources.gresource"
install -m 644 "$WORK/out/$APP_ID.gschema.xml" "$PREFIX/schema/$APP_ID.gschema.xml"
glib-compile-schemas --strict "$PREFIX/schema"

cat > "$PREFIX/run" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export GSETTINGS_SCHEMA_DIR="$DIR/schema"
exec "$DIR/resources-test" "$@"
LAUNCH
chmod 755 "$PREFIX/run"

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Resources (Qualcomm test)
Comment=GNOME Resources 51.0 with Qualcomm CPU sensor support
Exec=$PREFIX/run
Icon=org.gnome.Resources
Categories=System;Monitor;
Terminal=false
DESKTOP

echo "PASS: Resources 51.0 source=$COMMIT (Qualcomm CPU + Adreno GPU + MSM process telemetry)"
sha256sum "$PREFIX/resources-test" "$PREFIX/resources.gresource"
echo "Launch: $PREFIX/run"
echo "Rollback: rm -rf '$PREFIX' '$HOME/.local/share/applications/$APP_ID.desktop'"
echo "The Ubuntu /usr/bin/resources package was not changed."
