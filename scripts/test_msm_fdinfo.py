"""Unit tests of the safe, read-only Qualcomm DRM validation helper."""
import pathlib
import tempfile
import unittest

from verify_msm_fdinfo import (
    check_driver,
    parse_msm_by_process,
    parse_msm_stats,
    sample,
    stable_activity_ns,
)

SAMPLE_RON = b"""[
    (
        pid: 42,
        starttime: 123,
        gpu_usage_stats: {
            Enumerator(1): MsmStats(
                gfx_ns: 120000,
            ),
        },
    ),
]
"""


class MsmRuntimeTests(unittest.TestCase):
    def test_parser_accepts_valid_ron_and_rejects_unrelated_devices(self):
        payload = SAMPLE_RON + b'\xff'
        self.assertEqual(parse_msm_stats(payload), [(1, 120000)])
        self.assertEqual(parse_msm_by_process(payload), {(42, 123, 1): 120000})
        self.assertEqual(parse_msm_stats(b"GPU unavailable"), [])
        self.assertEqual(parse_msm_by_process(b"GPU unavailable"), {})

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
            helper.write_text("#!/bin/sh\ncat <<'EOF'\n" + SAMPLE_RON.decode() + "\nEOF\n")
            helper.chmod(0o700)
            count, ns, cards, identities = sample(helper, root)
            self.assertEqual((count, ns, cards), (1, 120000, {1}))
            self.assertEqual(identities, {(42, 123, 1): 120000})

    def test_activity_requires_a_stable_process_lifetime(self):
        before = {(11, 222, 1): 100}
        after = {(11, 222, 1): 140, (99, 999, 1): 5000000}
        self.assertEqual(stable_activity_ns(before, after), (1, 40))
        self.assertEqual(stable_activity_ns(before, {(11, 222, 1): 10}), (1, 0))
        self.assertEqual(stable_activity_ns(before, {(11, 333, 1): 900}), (0, 0))


if __name__ == "__main__":
    unittest.main()
