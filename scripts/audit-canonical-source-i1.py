#!/usr/bin/env python3
"""Read-only audit of a pinned Ubuntu Concept qcom-x1e .dsc, tarball and buildinfo.

The archive digest is compared to the PPA source declaration. The OpenPGP
signature is NOT verified here; a matching digest does not establish binary
reproducibility, git ancestry, PM restore, or permission to boot the image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

SOURCE = "linux-qcom-x1e"
MAX_SOURCE_SIZE = 900_000_000
MAX_DSC_SIZE = 100_000
MAX_CONFIG_SIZE = 6_000_000
MAX_MEMBER_SIZE = 7_000_000
REQUIRED = {
    "annotations": "debian.qcom-x1e/config/annotations",
    "changelog": "debian.qcom-x1e/changelog",
    "dell_dts": "arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts",
    "pdc": "drivers/irqchip/qcom-pdc.c",
    "pcie": "drivers/pci/controller/dwc/pcie-qcom.c",
    "pas": "drivers/remoteproc/qcom_q6v5_pas.c",
    "smp2p": "drivers/soc/qcom/smp2p.c",
    "clocks": "drivers/clk/qcom/gcc-x1e80100.c",
}
EC_PATH = "drivers/platform/arm64/dell-xps-ec.c"
SYMBOLS = ("HIBERNATION", "ARM_SCMI_CPUFREQ", "PCIE_QCOM", "QCOM_PDC", "QCOM_SMP2P")
DVALUE = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+-[0-9]+\.[0-9]+$")
ANNOTATION = re.compile(r"^CONFIG_([A-Z0-9_]+)\s+policy<\{'arm64': '([ymn])'\}>")


class SourceInvalid(ValueError):
    pass


def small_text(path, limit):
    try:
        if not path.is_file() or path.stat().st_size > limit:
            raise SourceInvalid("MISSING_OR_OVERSIZED_INPUT")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SourceInvalid("UNREADABLE_INPUT") from exc


def sha256_file(path):
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(2 ** 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SourceInvalid("UNREADABLE_INPUT") from exc
    return digest.hexdigest()


def dsc_declaration(path, archive):
    data = small_text(path, MAX_DSC_SIZE)
    fields = {}
    for key in ("Source", "Version"):
        matched = re.findall(r"^" + re.escape(key) + r":\s*(\S+)\s*$", data, re.M)
        if len(matched) != 1:
            raise SourceInvalid("INVALID_DSC_DECLARATION")
        fields[key] = matched[0]
    if fields["Source"] != SOURCE:
        raise SourceInvalid("WRONG_SOURCE_PACKAGE")
    version = fields["Version"]
    if not VERSION.fullmatch(version) or path.name != f"{SOURCE}_{version}.dsc" or archive.name != f"{SOURCE}_{version}.tar.gz":
        raise SourceInvalid("RELEASE_MISMATCH")
    match = re.search(r"(?m)^Checksums-Sha256:\s*\n((?:[ \t]+[^\n]+\n)+)", data)
    if not match:
        raise SourceInvalid("MISSING_CHECKSUM_SECTION")
    claims = []
    for line in match.group(1).splitlines():
        pieces = line.split()
        if len(pieces) != 3:
            raise SourceInvalid("MALFORMED_SOURCE_CHECKSUM")
        hexdigest, length, filename = pieces
        if filename == archive.name:
            if not DVALUE.fullmatch(hexdigest) or not length.isdigit():
                raise SourceInvalid("MALFORMED_SOURCE_CHECKSUM")
            claims.append((hexdigest, int(length)))
    if len(claims) != 1:
        raise SourceInvalid("MISSING_OR_DUPLICATE_TARBALL_CHECKSUM")
    return version, claims[0]


def archive_files(archive, version):
    prefix = SOURCE + "-" + version.split("-")[0] + "/"
    pending = {prefix + v: k for k, v in REQUIRED.items()}
    ec = prefix + EC_PATH
    output = {}
    ec_present = False
    try:
        with tarfile.open(archive, "r|gz") as records:
            for entry in records:
                if entry.name not in pending and entry.name != ec:
                    continue
                if not entry.isfile() or entry.size < 0 or entry.size > MAX_MEMBER_SIZE:
                    raise SourceInvalid("INVALID_ARCHIVE_MEMBER")
                if entry.name == ec:
                    if ec_present:
                        raise SourceInvalid("DUPLICATE_EC_MEMBER")
                    ec_present = True
                    continue
                name = pending[entry.name]
                if name in output:
                    raise SourceInvalid("DUPLICATE_ARCHIVE_MEMBER")
                source = records.extractfile(entry)
                if source is None:
                    raise SourceInvalid("INVALID_ARCHIVE_MEMBER")
                body = source.read(MAX_MEMBER_SIZE + 1)
                if len(body) != entry.size or len(body) > MAX_MEMBER_SIZE:
                    raise SourceInvalid("INVALID_ARCHIVE_MEMBER")
                output[name] = body
    except (tarfile.TarError, OSError, EOFError, ValueError) as exc:
        if isinstance(exc, SourceInvalid):
            raise
        raise SourceInvalid("UNREADABLE_ARCHIVE") from exc
    if set(output) != set(REQUIRED):
        raise SourceInvalid("REQUIRED_ARCHIVE_MEMBER_MISSING")
    return output, ec_present


def source_annotations(body):
    try:
        text = body.decode("utf-8")
    except UnicodeError as exc:
        raise SourceInvalid("INVALID_ANNOTATIONS") from exc
    actual = {}
    for line in text.splitlines():
        m = ANNOTATION.fullmatch(line.strip())
        if not m or m.group(1) not in SYMBOLS:
            continue
        key, value = m.groups()
        if key in actual:
            raise SourceInvalid("DUPLICATE_CONFIG_SYMBOL")
        actual[key] = value
    if set(actual) != set(SYMBOLS):
        raise SourceInvalid("MISSING_CONFIG_SYMBOL")
    return actual


def buildinfo_config(path):
    text = small_text(path, MAX_CONFIG_SIZE)
    actual = {}
    for line in text.splitlines():
        on = re.fullmatch(r"CONFIG_([A-Z0-9_]+)=([ymn])", line.strip())
        off = re.fullmatch(r"# CONFIG_([A-Z0-9_]+) is not set", line.strip())
        if on:
            key, value = on.groups()
        elif off:
            key, value = off.group(1), "n"
        else:
            continue
        if key not in SYMBOLS:
            continue
        if key in actual:
            raise SourceInvalid("DUPLICATE_CONFIG_SYMBOL")
        actual[key] = value
    if set(actual) != set(SYMBOLS):
        raise SourceInvalid("MISSING_CONFIG_SYMBOL")
    return actual


def audit(dsc, archive, config):
    version, (claim, size) = dsc_declaration(dsc, archive)
    try:
        if not archive.is_file() or archive.stat().st_size > MAX_SOURCE_SIZE:
            raise SourceInvalid("MISSING_OR_OVERSIZED_INPUT")
        if archive.stat().st_size != size or sha256_file(archive) != claim:
            raise SourceInvalid("SOURCE_TARBALL_MISMATCH")
    except OSError as exc:
        raise SourceInvalid("UNREADABLE_INPUT") from exc
    files, ec_present = archive_files(archive, version)
    changelog = files["changelog"].decode("utf-8", errors="replace")
    if not changelog.startswith(f"{SOURCE} ({version}) "):
        raise SourceInvalid("CHANGELOG_RELEASE_MISMATCH")
    annotation = source_annotations(files["annotations"])
    config_values = buildinfo_config(config)
    if annotation != config_values:
        raise SourceInvalid("ANNOTATION_BINARY_CONFIG_MISMATCH")
    blockers = ["HARDWARE_RESTORE_UNVERIFIED", "GIT_COMMIT_EQUIVALENCE_UNVERIFIED"]
    if annotation["HIBERNATION"] != "y":
        blockers.insert(0, "HIBERNATION_NOT_ENABLED")
    if not ec_present:
        blockers.append("DELL_EC_NOT_IN_SOURCE")
    return {
        "status": "NO_GO",
        "source": SOURCE,
        "version": version,
        "source_sha256_verified": True,
        "declared_tar_sha256": claim,
        "selected_files_sha256": {
            key: hashlib.sha256(data).hexdigest()
            for key, data in sorted(files.items())
        },
        "annotations": annotation,
        "buildinfo_kconfig_matches_annotations": True,
        "dell_ec_present": ec_present,
        "dsc_signature_verified": False,
        "git_commit_equivalence_verified": False,
        "binary_reproducibility_verified": False,
        "install_authorized": False,
        "blockers": blockers,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsc", type=Path, required=True)
    parser.add_argument("--tarball", type=Path, required=True)
    parser.add_argument("--buildinfo-config", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        out = audit(args.dsc, args.tarball, args.buildinfo_config)
        rc = 1
    except SourceInvalid as exc:
        out = {"status": "INVALID", "error_code": str(exc), "source_sha256_verified": False,
               "install_authorized": False, "dsc_signature_verified": False}
        rc = 2
    if args.json:
        print(json.dumps(out, sort_keys=True))
    else:
        print(out["status"] + ": " + ", ".join(out.get("blockers", [out.get("error_code", "")])))
    return rc


if __name__ == "__main__":
    sys.exit(main())
