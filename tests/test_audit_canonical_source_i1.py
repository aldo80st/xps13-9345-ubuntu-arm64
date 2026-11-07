"""Reproducible tests for checking the exact Canonical PPA source archive."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit-canonical-source-i1.py"
PREFIX = "linux-qcom-x1e-7.3.0/"
VERSION = "7.3.0-31.31"
FILES = {
    "debian.qcom-x1e/config/annotations": b"# FORMAT: 4\n# ARCH: arm64\nCONFIG_HIBERNATION policy<{'arm64': 'n'}>\nCONFIG_ARM_SCMI_CPUFREQ policy<{'arm64': 'm'}>\nCONFIG_PCIE_QCOM policy<{'arm64': 'y'}>\nCONFIG_QCOM_PDC policy<{'arm64': 'y'}>\nCONFIG_QCOM_SMP2P policy<{'arm64': 'm'}>\n",
    "debian.qcom-x1e/changelog": b"linux-qcom-x1e (7.3.0-31.31) stonking; urgency=medium\n",
    "arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts": b"// dell dts fixture\n",
    "drivers/irqchip/qcom-pdc.c": b"// pdc fixture\n",
    "drivers/pci/controller/dwc/pcie-qcom.c": b"// pci fixture\n",
    "drivers/remoteproc/qcom_q6v5_pas.c": b"// pas fixture\n",
    "drivers/soc/qcom/smp2p.c": b"// smp2p fixture\n",
    "drivers/clk/qcom/gcc-x1e80100.c": b"// clock fixture\n",
}
CONFIG = b"# CONFIG_HIBERNATION is not set\nCONFIG_ARM_SCMI_CPUFREQ=m\nCONFIG_PCIE_QCOM=y\nCONFIG_QCOM_PDC=y\nCONFIG_QCOM_SMP2P=m\n"


class SourceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name)
        self.tarball = self.p / f"linux-qcom-x1e_{VERSION}.tar.gz"
        self.dsc = self.p / f"linux-qcom-x1e_{VERSION}.dsc"
        self.config = self.p / "buildinfo.config"
        self.config.write_bytes(CONFIG)
        self.files = dict(FILES)
        self.repack()

    def repack(self):
        with tarfile.open(self.tarball, "w:gz") as archive:
            for name, body in sorted(self.files.items()):
                member = tarfile.TarInfo(PREFIX + name)
                member.size = len(body)
                archive.addfile(member, io.BytesIO(body))
        digest = hashlib.sha256(self.tarball.read_bytes()).hexdigest()
        self.dsc.write_text(
            "-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\n"
            "Format: 1.0\nSource: linux-qcom-x1e\n"
            f"Version: {VERSION}\nChecksums-Sha256:\n"
            f" {digest} {self.tarball.stat().st_size} {self.tarball.name}\n"
            "-----BEGIN PGP SIGNATURE-----\nplaceholder\n"
        )

    def run_gate(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--dsc", str(self.dsc),
             "--tarball", str(self.tarball), "--buildinfo-config", str(self.config),
             "--json"], capture_output=True, text=True, timeout=16
        )
        return r, json.loads(r.stdout)

    def test_valid_archive_is_evidence_not_boot_permission(self):
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(o["status"], "NO_GO")
        self.assertTrue(o["source_sha256_verified"])
        self.assertFalse(o["install_authorized"])
        self.assertFalse(o["dsc_signature_verified"])
        self.assertFalse(o["git_commit_equivalence_verified"])
        self.assertIn("HIBERNATION_NOT_ENABLED", o["blockers"])
        self.assertFalse(o["dell_ec_present"])

    def test_tampered_archive_fails(self):
        with self.tarball.open("ab") as f:
            f.write(b"tamper")
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(o["status"], "INVALID")
        self.assertEqual(o["error_code"], "SOURCE_TARBALL_MISMATCH")

    def test_wrong_source_package_fails(self):
        s = self.dsc.read_text().replace("Source: linux-qcom-x1e", "Source: linux-custom")
        self.dsc.write_text(s)
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(o["error_code"], "WRONG_SOURCE_PACKAGE")

    def test_wrong_release_fails(self):
        self.dsc.write_text(self.dsc.read_text().replace("Version: 7.3.0-31.31", "Version: 7.3.0-99.99"))
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(o["error_code"], "RELEASE_MISMATCH")

    def test_missing_dts_fails_closed(self):
        self.files.pop("arch/arm64/boot/dts/qcom/x1e80100-dell-xps13-9345.dts")
        self.repack()
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(o["error_code"], "REQUIRED_ARCHIVE_MEMBER_MISSING")

    def test_missing_annotations_fails_closed(self):
        self.files.pop("debian.qcom-x1e/config/annotations")
        self.repack()
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(o["status"], "INVALID")

    def test_source_and_binary_config_disagreement_fails(self):
        self.config.write_bytes(CONFIG.replace(b"# CONFIG_HIBERNATION is not set", b"CONFIG_HIBERNATION=y"))
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(o["error_code"], "ANNOTATION_BINARY_CONFIG_MISMATCH")

    def test_annotations_enable_does_not_mean_restore(self):
        self.files["debian.qcom-x1e/config/annotations"] = (
            self.files["debian.qcom-x1e/config/annotations"].replace(b"'arm64': 'n'", b"'arm64': 'y'")
        )
        self.config.write_bytes(CONFIG.replace(b"# CONFIG_HIBERNATION is not set", b"CONFIG_HIBERNATION=y"))
        self.repack()
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(o["status"], "NO_GO")
        self.assertNotIn("HIBERNATION_NOT_ENABLED", o["blockers"])
        self.assertIn("HARDWARE_RESTORE_UNVERIFIED", o["blockers"])

    def test_smp2p_config_drift_fails(self):
        self.config.write_bytes(CONFIG.replace(b"CONFIG_QCOM_SMP2P=m", b"CONFIG_QCOM_SMP2P=y"))
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(o["error_code"], "ANNOTATION_BINARY_CONFIG_MISMATCH")

    def test_absent_file_fails(self):
        self.dsc.unlink()
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(o["status"], "INVALID")

    def test_no_mutation(self):
        originals = (self.tarball.read_bytes(), self.dsc.read_bytes(), self.config.read_bytes())
        self.run_gate()
        self.assertEqual(originals, (self.tarball.read_bytes(), self.dsc.read_bytes(), self.config.read_bytes()))

    def test_committed_real_source_snapshot_preserves_no_go(self):
        evidence = json.loads((ROOT / 'docs/hibernate-canonical-source-i1-evidence.json').read_text())
        self.assertEqual(evidence['version'], VERSION)
        self.assertEqual(evidence['declared_tar_sha256'],
                         '41e6c1e13aa14a6c4bc66f8e8faa33d6364eb309fa8f8c726a1e0ebee84a4051')
        self.assertEqual(evidence['annotations']['HIBERNATION'], 'n')
        self.assertEqual(len(evidence['selected_files_sha256']), 8)
        self.assertFalse(evidence['install_authorized'])
        self.assertFalse(evidence['git_commit_equivalence_verified'])

    def test_ec_presence_is_detected_but_never_qualifies_restoration(self):
        self.files["drivers/platform/arm64/dell-xps-ec.c"] = b"// EC test marker\n"
        self.repack()
        r, o = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertTrue(o["dell_ec_present"])
        self.assertFalse(o["install_authorized"])


if __name__ == "__main__":
    unittest.main()
