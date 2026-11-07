#!/usr/bin/env python3
"""Stage reviewed Dell EC v8 upstream patches in an *isolated* kernel source copy.

Never changes a kernel installation, running CPU policy, boot firmware, or input tree.
Only supports the pinned 2026-11-07 EC v8 series and a fresh .local output path.
An applied patch series is NOT evidence that the driver builds or runs safely.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SHA = {
    "v8-1.diff": "c73f41f2e3c91afd388aa442b616f82c0be0f39b9a3185391da387cd099ea6e0",
    "v8-2.diff": "5eaba144c037a94d700e73b248883246494683b4aa8a36d71c17a3625a5c5938",
    "v8-3.diff": "8a25b419d57694ceceaa024f3152c4363268d2faf9fffe0ec1531a4f64f05620",
}
EC_KCONFIG = """config EC_DELL_XPS
\ttristate "Dell XPS 9345 Embedded Controller driver"
\tdepends on ARCH_QCOM || COMPILE_TEST
\tdepends on I2C
\tdepends on IIO
\thelp
\t  Driver for the Embedded Controller in the Qualcomm Snapdragon-based
\t  Dell XPS 13 9345, which handles thermal management and fan speed
\t  control.

\t  Say M or Y here to include this support.

"""


def patch2_without_kconfig(text: str) -> str:
    """Retain unchanged upstream file diffs; omit incompatible Kconfig hunk."""
    start = "diff --git a/drivers/platform/arm64/Kconfig b/drivers/platform/arm64/Kconfig\n"
    end = "diff --git a/drivers/platform/arm64/Makefile b/drivers/platform/arm64/Makefile\n"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("Unexpected upstream patch layout")
    a, b = text.index(start), text.index(end)
    if b <= a:
        raise ValueError("Patch sections reversed")
    result = text[:a] + text[b:]
    if result.count("diff --git") != 3:
        raise ValueError("Unexpected upstream file count")
    return result


def kconfig_add_dell_ec(text: str) -> str:
    """Port only EC_DELL_XPS stanza, anchor on existing Ubuntu 7.3 symbol."""
    anchor = "config EC_HUAWEI_GAOKUN\n"
    if text.count(anchor) != 1 or "config EC_DELL_XPS\n" in text:
        raise ValueError("Missing/ambiguous insertion anchor or EC already present")
    return text.replace(anchor, EC_KCONFIG + anchor, 1)


def check_bundle(directory: Path) -> None:
    for name, expected in SHA.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Untrusted/mismatched upstream patch: {name}")


def _apply(directory: Path, patch_file: Path) -> None:
    result = subprocess.run(
        ["patch", "--batch", "--forward", "-p1", "-d", str(directory),
         "-i", str(patch_file), "--fuzz=2"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise ValueError(f"Patch does not cleanly apply: {patch_file.name}")


def stage(source: Path, destination: Path, patches: Path, repo: Path) -> dict:
    source = source.resolve(strict=True)
    repo = repo.resolve(strict=True)
    patches = patches.resolve(strict=True)
    # Ensure output is a new path inside THIS repo's ignored local scratch.
    output_root = (repo / ".local").resolve(strict=True)
    destination = destination.resolve(strict=False)
    if not destination.is_relative_to(output_root) or destination == output_root:
        raise ValueError("Output must be an unused subdirectory inside repo/.local/")
    if destination.exists():
        raise ValueError("Output already exists: refuse overwrite")
    if output_root.is_relative_to(source) or source.is_relative_to(output_root):
        # Input is allowed under the worktree's .local, but output must not
        # overlap source in either direction.
        if destination.is_relative_to(source) or source.is_relative_to(destination):
            raise ValueError("Source and output overlap")
    if not (source / "drivers/platform/arm64/Kconfig").is_file():
        raise ValueError("Input is not a supported Linux source tree")
    check_bundle(patches)
    with tempfile.TemporaryDirectory(prefix="ec-v8-staging-", dir=output_root) as temp:
        tmp = Path(temp)
        tree = tmp / "tree"
        shutil.copytree(source, tree, symlinks=True)
        _apply(tree, patches / "v8-1.diff")
        filtered = tmp / "v8-2-without-kconfig.diff"
        filtered.write_text(patch2_without_kconfig(
            (patches / "v8-2.diff").read_text(encoding="utf-8")),
            encoding="utf-8")
        _apply(tree, filtered)
        kconf = tree / "drivers/platform/arm64/Kconfig"
        kconf.write_text(kconfig_add_dell_ec(kconf.read_text(encoding="utf-8")),
                         encoding="utf-8")
        _apply(tree, patches / "v8-3.diff")
        required = [
            "drivers/platform/arm64/dell-xps-ec.c",
            "Documentation/devicetree/bindings/embedded-controller/dell,xps13-9345-ec.yaml",
            "arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts",
        ]
        for name in required:
            if not (tree / name).is_file():
                raise ValueError(f"Required EC component missing: {name}")
        if "embedded-controller@3b" not in (tree / required[-1]).read_text():
            raise ValueError("Expected EC DTS node not found")
        tree.rename(destination)
    return {"status": "STAGED_REVIEW_REQUIRED",
            "source_untouched": True,
            "ec_driver": True,
            "ec_dt_node": True,
            "patch_count": len(SHA),
            "boot_or_kernel_installed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-tree", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    try:
        result = stage(args.source_tree, args.output,
                       repo / "patches/dell-ec-v8", repo)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "NO_GO", "reason": str(exc).split(":")[0]}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
