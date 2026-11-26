#!/usr/bin/env python3
"""Read-only, no-DSP-call verification for Dell XPS 13 9345 Hexagon lab."""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
import sys

LAB = Path.home() / "labs/xps13-9345-hexagon"
FW = Path("/lib/firmware/qcom/x1e80100/dell/xps13-9345/qccdsp8380.mbn.zst")
FW_SHA = "3df4de099b23df0969c172fa2660e02c1ba4e1b5c280eb0198a89194f400d875"
EXPECTED = {
    "fastrpc_shell_3", "fastrpc_shell_unsigned_3", "libc++.so.1", "libc++abi.so.1",
    "libsysmon_skel.so", "libsysmondomain_skel.so", "libsysmonquery_skel.so",
    "libsysmonhvxthrottle_skel.so", "libstabilitydomain_skel.so",
    "libbenchmark_skel.so", "libloadalgo_skel.so", "libcrm_test_skel.so",
    "libQ6MSFR_manager_skel.so", "libQ6MSFR_manager_skel_intermediate.so",
    "example_image.so", "example_image_runner.so", "version.so",
}

def verify_binary(binary, firmware):
    if binary[:5] != b"\x7fELF\x01" or len(binary) < 52:
        raise ValueError("Unexpected ELF type")
    offset = struct.unpack_from("<I", binary, 28)[0]
    size, count = struct.unpack_from("<HH", binary, 42)
    if size < 32 or count < 1 or offset + count * size > len(binary):
        raise ValueError("Invalid program header table")
    good = total = 0
    for i in range(count):
        row = offset + i * size
        segment = struct.unpack_from("<I", binary, row + 4)[0]
        length = struct.unpack_from("<I", binary, row + 16)[0]
        if not length:
            continue
        if segment + length > len(binary):
            raise ValueError("ELF segment out of file")
        total += 1
        good += hashlib.sha256(binary[segment:segment + length]).digest() in firmware
    return good, total

def main():
    if os.uname().machine != "aarch64":
        raise RuntimeError("Requires ARM64 host")
    firmware = subprocess.run(["zstd", "-q", "-d", "-c", str(FW)],
                              capture_output=True, check=True).stdout
    if hashlib.sha256(firmware).hexdigest() != FW_SHA:
        raise RuntimeError("Unexpected Dell CDSP firmware hash")
    folder = LAB / "staging/cdsp"
    if not folder.is_dir():
        raise RuntimeError("Staging folder missing")
    for name in EXPECTED:
        blob = (folder / name).read_bytes()
        good, total = verify_binary(blob, firmware)
        if not total or good != total:
            raise RuntimeError(f"CDSP rejects {name}: {good}/{total}")
    nodes = ("/dev/fastrpc-cdsp", "/dev/dma_heap/system")
    remote = []
    for base in Path("/sys/class/remoteproc").glob("remoteproc*"):
        if (base / "name").read_text().strip() == "cdsp":
            remote.append((base / "state").read_text().strip())
    output = {
        "firmware_sha256": FW_SHA, "dsp_objects_authorized": len(EXPECTED),
        "static_admission": "PASS", "cdsp_running": remote == ["running"],
        "device_access": {p: {"read": os.access(p, os.R_OK),
                              "write": os.access(p, os.W_OK)} for p in nodes},
        "npu_inference_proven": False
    }
    print(json.dumps(output, indent=2))
    return 0 if remote == ["running"] else 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"HEXAGON_PREFLIGHT_FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
