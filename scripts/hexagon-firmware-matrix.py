#!/usr/bin/env python3
"""Static-only evaluation of Dell and Qualcomm CDSP firmware/shell pairs.

No writes, device openings, firmware updates, FastRPC calls, or privilege use.
This evaluates embedded segment-digest admission, NOT firmware boot signatures.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

BASE = Path("/lib/firmware/qcom/x1e80100")
LAB = Path.home() / "labs/xps13-9345-hexagon"
FIRMWARE = {
    "dell_00046": (
        BASE / "dell/xps13-9345/qccdsp8380.mbn.zst",
        "3df4de099b23df0969c172fa2660e02c1ba4e1b5c280eb0198a89194f400d875",
    ),
    "qualcomm_00094": (
        BASE / "cdsp.mbn.zst",
        "09fdb2fefe124338daa3e3eca1df9a719bb199f56af264bf0bf9a255ee3f3489",
    ),
}
SHELLS = {
    "dell_00046": (
        LAB / "staging/cdsp",
        {
            "fastrpc_shell_3": "a9411d2ff447e285197be2385c89e12123789834a0d9c8974b6e55a3d9cf79dc",
            "fastrpc_shell_unsigned_3": "5e15232f86a258e720e34fefb236b25dbd5abedd2300d561401950bfc9595e45",
        },
    ),
    "qualcomm_00094": (
        LAB / "firmware-candidates/cdsp-00094",
        {
            "fastrpc_shell_3": "57720f6199ce51e92b510240871779887b2d6fa4037422983b4ef7d8d3464a58",
            "fastrpc_shell_unsigned_3": "496b08874a6f97086fd87a342868bc07017162d1e16c97bfa0e9516849e64a97",
        },
    ),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def elf_segment_hashes(blob):
    if blob[:5] != b"\x7fELF\x01" or len(blob) < 52:
        raise ValueError("Expected 32-bit ELF")
    phoff = struct.unpack_from("<I", blob, 28)[0]
    size, count = struct.unpack_from("<HH", blob, 42)
    if size < 32 or count < 1 or phoff + size * count > len(blob):
        raise ValueError("Invalid ELF headers")
    hashes = []
    for i in range(count):
        hdr = phoff + i * size
        start = struct.unpack_from("<I", blob, hdr + 4)[0]
        length = struct.unpack_from("<I", blob, hdr + 16)[0]
        if length == 0:
            continue
        if start + length > len(blob):
            raise ValueError("Invalid ELF segment")
        hashes.append(hashlib.sha256(blob[start:start + length]).digest())
    if not hashes:
        raise ValueError("Empty program segment list")
    return hashes


def main():
    if sys.platform != "linux":
        raise RuntimeError("Linux required")
    firmware = {}
    for key, (file, digest) in FIRMWARE.items():
        blob = subprocess.run(
            ["zstd", "-dcq", str(file)], check=True, capture_output=True
        ).stdout
        if sha(blob) != digest:
            raise ValueError(f"Firmware hash changed: {key}")
        firmware[key] = blob
    shell_hashes = {}
    for key, (folder, expected) in SHELLS.items():
        shell_hashes[key] = {}
        for name, digest in expected.items():
            blob = (folder / name).read_bytes()
            if sha(blob) != digest:
                raise ValueError(f"Shell hash changed: {key}/{name}")
            shell_hashes[key][name] = elf_segment_hashes(blob)

    matrix = {}
    for fw_key, blob in firmware.items():
        matrix[fw_key] = {}
        for shell_key, by_name in shell_hashes.items():
            matrix[fw_key][shell_key] = {
                name: {
                    "matched": sum(h in blob for h in segments),
                    "total": len(segments),
                }
                for name, segments in by_name.items()
            }
    for key in FIRMWARE:
        for data in matrix[key][key].values():
            if data["matched"] != data["total"]:
                raise ValueError(f"Expected matching firmware/shell pair failed: {key}")
    print(json.dumps({
        "method": "read_only_static_segment_digest_admission",
        "matrix": matrix,
        "oem_secure_boot_signature_verified": False,
        "dsp_boot_test_performed": False,
        "npu_inference_performed": False,
        "replacement_safe_to_install": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"FIRMWARE_COMPARISON_FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
