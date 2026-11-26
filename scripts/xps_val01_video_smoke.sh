#!/usr/bin/env bash
# XPS-VAL-01: isolated, opt-in H.264 decode smoke test; no driver installation.
# This tests pipeline completion, NOT real-time playback, compositor, or Chrome VA-API.
set -euo pipefail
umask 077
for tool in gst-launch-1.0 gst-inspect-1.0 timeout mktemp stat date; do
  command -v "$tool" >/dev/null || { echo "SKIP missing=$tool"; exit 77; }
done
for element in videotestsrc x264enc h264parse filesink filesrc avdec_h264 fakesink; do
  gst-inspect-1.0 "$element" >/dev/null 2>&1 || { echo "SKIP gst_plugin=$element"; exit 77; }
done
work=$(mktemp -d "${TMPDIR:-/tmp}/xps-val01-h264.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
echo "SUITE=XPS-VAL-01-H264 DATA=synthetic RESOLUTION=1920x1080 FRAMES=120"
t0=$(date +%s%3N)
timeout 20s gst-launch-1.0 -q videotestsrc num-buffers=120 pattern=ball \
  ! 'video/x-raw,width=1920,height=1080,format=I420,framerate=30/1' \
  ! x264enc speed-preset=ultrafast tune=zerolatency bitrate=2200 key-int-max=30 threads=4 \
  ! h264parse ! 'video/x-h264,stream-format=byte-stream,alignment=au' \
  ! filesink location="$work/fixture.h264"
echo "ENCODE=PASS elapsed_ms=$(($(date +%s%3N)-t0)) bytes=$(stat -c '%s' "$work/fixture.h264")"
t0=$(date +%s%3N)
timeout 12s gst-launch-1.0 -q filesrc location="$work/fixture.h264" \
  ! h264parse ! avdec_h264 max-threads=4 ! fakesink sync=false
echo "CPU_DECODE=PASS elapsed_ms=$(($(date +%s%3N)-t0))"
decoder=""
for p in /sys/class/video4linux/video*/name; do
  [ -r "$p" ] || continue
  [ "$(cat "$p")" = "qcom-iris-decoder" ] && decoder="/dev/$(basename "$(dirname "$p")")" && break
done
# The current GStreamer decoder element registers a read-only device property
# and defaults to /dev/video16. Do NOT attempt to set device= (ignored with warning).
# Fail closed if the discovered Iris node is different from that known default.
if [ "$decoder" = "/dev/video16" ] && gst-inspect-1.0 v4l2h264dec >/dev/null 2>&1; then
  t0=$(date +%s%3N)
  if timeout 12s gst-launch-1.0 -q filesrc location="$work/fixture.h264" \
     ! h264parse ! v4l2h264dec ! fakesink sync=false; then
    echo "IRIS_V4L2_DECODE=PASS elapsed_ms=$(($(date +%s%3N)-t0))"
  else
    echo "IRIS_V4L2_DECODE=FAIL (do not assume missing firmware or driver)" >&2
    exit 1
  fi
else
  echo "IRIS_V4L2_DECODE=SKIP (no matching accessible device/plugin)"
fi
echo "RESULT=PASS ARTIFACTS=removed_by_trap WRITES=temporary_only"
