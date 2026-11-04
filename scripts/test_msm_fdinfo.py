"""Unit tests of the safe, read-only Qualcomm DRM validation helper."""
import pathlib
import tempfile
import unittest

from verify_msm_fdinfo import check_driver, parse_msm_stats, sample


class MsmRuntimeTests(unittest.TestCase):
    def test_parser_accepts_valid_ron_and_rejects_unrelated_devices(self):
        payload = (
            b"gpu_usage_stats: {\\n  Enumerator(1): MsmStats(\\n gfx_ns: 12345,\\n),\\n"
            b"  Enumerator(2): V3dStats( gfx_ns: 999, ),\\n}"
        )
        payload = payload.replace(b"\\n", b"\n")
        self.assertEqual(parse_msm_stats(payload), [(1, 12345)])
        self.assertEqual(parse_msm_stats(b"GPU unavailable"), [])

    def test_driver_check_requires_genuine_msm_sysfs_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            for name in ("msm_dpu", "evdi"):
                (root / "drivers" / name).mkdir(parents=True)
            for card, driver in ((0, "evdi"), (1, "msm_dpu")):
                path = root / f"card{card}" / "device"
                path.mkdir(parents=True)
                (path / "driver").symlink_to(root / "drivers" / driver)
            self.assertFalse(check_driver(0, root))
            self.assertTrue(check_driver(1, root))
            self.assertFalse(check_driver(3, root))

    def test_fake_helper_returns_anonymized_aggregates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root / "drivers" / "msm").mkdir(parents=True)
            binding = root / "card1" / "device"
            binding.mkdir(parents=True)
            (binding / "driver").symlink_to(root / "drivers" / "msm")
            helper = root / "mock-helper"
            helper.write_text(
                "#!/bin/sh\n"
                "printf 'Enumerator(1): MsmStats(\\n gfx_ns: 120000,\\n),\\n'\n"
            )
            helper.chmod(0o700)
            count, ns, cards = sample(helper, root)
            self.assertEqual((count, ns, cards), (1, 120000, {1}))


if __name__ == "__main__":
    unittest.main()
