"""Read-only inspector fixture tests. No actual privileged hardware actions."""
import os
from pathlib import Path
import stat
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import xps_authz_native_readonly as m


class Fixture:
    def __init__(self):
        self.data = {}
        self.dirs = {}
        self.resolved = {}
        self.stats = {}
        self.data[Path("/proc/device-tree/model")] = m.MODEL + b"\0"
        self.data[Path("/proc/thread-self/status")] = b"Name:\ttest\nCapEff:\t0000000000000000\n"
        names = sorted(m.EXPECTED_SENSORS)
        self.dirs[m.THERMAL] = tuple(f"thermal_zone{i}" for i in range(len(names)))
        self.zone = {}
        for i, name in enumerate(names):
            p = m.THERMAL / f"thermal_zone{i}"
            self.zone[name] = p
            self.data[p / "type"] = name.encode() + b"\n"
            self.data[p / "temp"] = b"30000\n" if name == m.BATTERY_SENSOR else b"40000\n"
        for n, v in (("qcom-battmgr-ac", b"0\n"), ("qcom-battmgr-usb", b"1\n")):
            self.data[m.POWER / n / "online"] = v
        b = m.POWER / "qcom-battmgr-bat"
        self.data[b / "present"] = b"1\n"
        self.data[b / "energy_full"] = b"1000000\n"
        self.data[b / "energy_now"] = b"990000\n"
        self.stats[m.MODULE] = object()
        self.data[m.MODULE / "srcversion"] = m.STOCK_SRCVERSION.encode() + b"\n"
        self.data[m.MODULE / "refcnt"] = b"0\n"
        self.dirs[m.MODULE / "holders"] = ()
        self.dirs[m.VIDEOS] = ("video16", "video17", "v4l-subdev0")
        for basename, role, minor in (
            ("video16", "qcom-iris-decoder", 22), ("video17", "qcom-iris-encoder", 24)
        ):
            p = m.VIDEOS / basename
            self.data[p / "name"] = role.encode() + b"\n"
            self.data[p / "dev"] = f"81:{minor}\n".encode()
            self.resolved[p / "device/driver"] = m.IRIS_DRIVER
            self.stats[Path("/dev") / basename] = types.SimpleNamespace(
                st_mode=stat.S_IFCHR | 0o660, st_rdev=os.makedev(81, minor)
            )

    def read(self, p, limit=m.MAX_READ):
        if p not in self.data:
            raise FileNotFoundError(str(p))
        v = self.data[p]
        if len(v) > limit:
            raise m.InspectionError("oversized fixture")
        return v

    def names(self, p):
        if p not in self.dirs:
            raise FileNotFoundError(str(p))
        return self.dirs[p]

    def resolve(self, p):
        if p not in self.resolved:
            raise FileNotFoundError(str(p))
        return self.resolved[p]

    def stat(self, p):
        if p not in self.stats:
            raise FileNotFoundError(str(p))
        return self.stats[p]


class TestReadOnly(unittest.TestCase):
    def setUp(self):
        self.r = Fixture()

    def test_host_and_cap(self):
        m.verify_host(self.r, m.ARCH, m.KERNEL)
        self.assertEqual(m.effective_capabilities(self.r), 0)
        with self.assertRaises(m.InspectionError):
            m.verify_host(self.r, "x86_64", m.KERNEL)
        with self.assertRaises(m.InspectionError):
            m.verify_host(self.r, m.ARCH, "wrong")
        self.r.data[Path("/proc/device-tree/model")] = b"wrong"
        with self.assertRaises(m.InspectionError):
            m.verify_host(self.r, m.ARCH, m.KERNEL)

    def test_exact_schema_and_start_envelope(self):
        s = m.read_power_thermal(self.r)
        self.assertEqual(s.sensor_count, 59)
        self.assertEqual(s.battery_pct, 99)
        self.assertTrue(s.allowed(starting=True))

    def test_missing_duplicate_and_unknown_sensor(self):
        original = self.r.dirs[m.THERMAL]
        self.r.dirs[m.THERMAL] = original[:-1]
        with self.assertRaises(m.InspectionError):
            m.read_power_thermal(self.r)
        self.r.dirs[m.THERMAL] = original
        p = self.r.zone["mem-thermal"] / "type"
        for n in (b"video-thermal\n", b"unknown\n"):
            self.r.data[p] = n
            with self.assertRaises(m.InspectionError):
                m.read_power_thermal(self.r)

    def test_bad_temp_and_missing_power(self):
        p = self.r.zone["mem-thermal"] / "temp"
        for v in (b"nan", b"110000", b"-10000", b"40000.1"):
            self.r.data[p] = v
            with self.assertRaises(m.InspectionError):
                m.read_power_thermal(self.r)
        self.r.data[p] = b"40000"
        del self.r.data[m.POWER / "qcom-battmgr-ac" / "online"]
        with self.assertRaises(FileNotFoundError):
            m.read_power_thermal(self.r)

    def test_limits_exact_and_all_soc_max(self):
        p = self.r.zone["gpuss-2-thermal"] / "temp"
        self.r.data[p] = b"55000"
        self.assertFalse(m.read_power_thermal(self.r).allowed(starting=True))
        self.assertTrue(m.read_power_thermal(self.r).allowed(starting=False))
        self.r.data[p] = b"65000"
        self.assertFalse(m.read_power_thermal(self.r).allowed(starting=False))
        self.r.data[p] = b"40000"
        self.r.data[self.r.zone[m.BATTERY_SENSOR] / "temp"] = b"40000"
        self.assertFalse(m.read_power_thermal(self.r).allowed(starting=True))

    def test_battery_and_external_edges(self):
        b = m.POWER / "qcom-battmgr-bat"
        self.r.data[b / "energy_now"] = b"300000"
        self.assertTrue(m.read_power_thermal(self.r).allowed(starting=True))
        self.r.data[b / "energy_now"] = b"299999"
        self.assertFalse(m.read_power_thermal(self.r).allowed(starting=True))
        self.r.data[b / "energy_now"] = b"1000001"
        with self.assertRaises(m.InspectionError):
            m.read_power_thermal(self.r)
        self.r.data[b / "energy_now"] = b"900000"
        self.r.data[m.POWER / "qcom-battmgr-usb" / "online"] = b"0"
        self.assertFalse(m.read_power_thermal(self.r).allowed(starting=True))
        self.r.data[m.POWER / "qcom-battmgr-usb" / "online"] = b"2"
        with self.assertRaises(m.InspectionError):
            m.read_power_thermal(self.r)

    def test_live_module_and_missing_vs_unknown(self):
        state = m.read_live_module(self.r)
        self.assertTrue(state.loaded)
        self.assertEqual(state.srcversion, m.STOCK_SRCVERSION)
        self.assertEqual(state.refcnt, 0)
        self.r.data[m.MODULE / "srcversion"] = b"not-a-srcversion"
        with self.assertRaises(m.InspectionError):
            m.read_live_module(self.r)
        self.r.data[m.MODULE / "srcversion"] = m.STOCK_SRCVERSION.encode() + b"\n"
        del self.r.data[m.MODULE / "refcnt"]
        with self.assertRaises(FileNotFoundError):
            m.read_live_module(self.r)
        del self.r.stats[m.MODULE]
        with self.assertRaises(m.InspectionError):
            m.read_live_module(self.r)
        self.r.dirs[Path("/sys/module")] = ("other",)
        witness = m.HostWitness("test-boot", "pid:[1]")
        with patch.object(m, "verified_host_view", return_value=True):
            self.assertFalse(m.read_live_module(self.r, witness).loaded)
            self.r.dirs[Path("/sys/module")] = ("qcom_iris",)
            with self.assertRaises(m.InspectionError):
                m.read_live_module(self.r, witness)

    def test_dynamic_device_names_and_driver_rdev(self):
        ds = m.read_iris_devices(self.r)
        self.assertEqual(len(ds), 2)
        self.r.resolved[m.VIDEOS / "video16/device/driver"] = Path("/sys/bus/platform/drivers/other")
        with self.assertRaises(m.InspectionError):
            m.read_iris_devices(self.r)
        self.r.resolved[m.VIDEOS / "video16/device/driver"] = m.IRIS_DRIVER
        self.r.stats[Path("/dev/video16")].st_rdev = os.makedev(81, 23)
        with self.assertRaises(m.InspectionError):
            m.read_iris_devices(self.r)

    def test_missing_and_duplicate_devices(self):
        self.r.dirs[m.VIDEOS] = ("video16",)
        with self.assertRaises(m.InspectionError):
            m.read_iris_devices(self.r)
        self.r.dirs[m.VIDEOS] = ("video16", "video17")
        self.r.data[m.VIDEOS / "video17/name"] = b"qcom-iris-decoder\n"
        with self.assertRaises(m.InspectionError):
            m.read_iris_devices(self.r)

    def test_proc_mount_visibility(self):
        line = "10 9 0:10 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw"
        self.assertTrue(m.proc_mount_full_visibility(line))
        self.assertTrue(m.proc_mount_full_visibility(line + ",hidepid=0"))
        for s in (line + ",hidepid=2", line + ",subset=pid",
                  line.replace(" / /proc ", " /other /proc "), line + "\n" + line, ""):
            self.assertFalse(m.proc_mount_full_visibility(s))

    def test_sysfs_overmount_and_proc_pid_overmount(self):
        sysline = "12 9 0:11 / /sys rw,relatime - sysfs sysfs rw"
        self.assertTrue(m.sysfs_module_full_visibility(sysline))
        for point in ("/sys/module", "/sys/module/qcom_iris"):
            over = "13 12 0:12 / " + point + " rw - tmpfs tmpfs rw"
            self.assertFalse(m.sysfs_module_full_visibility(sysline + "\n" + over))
        proc = "10 9 0:10 / /proc rw - proc proc rw"
        over = "14 10 0:12 / /proc/123/fd rw - tmpfs tmpfs rw"
        self.assertFalse(m.proc_mount_full_visibility(proc + "\n" + over))

    def test_leader_exits_task_dir_missing_is_unknown(self):
        # A PID was visible; leader exits before task enumeration. A surviving
        # thread may still hold the device. Do not report a visible zero.
        import contextlib
        @contextlib.contextmanager
        def scandir(path):
            if str(path) == "/proc":
                yield iter([types.SimpleNamespace(name="123")])
            elif str(path) == "/proc/123/task":
                raise FileNotFoundError("leader gone, sibling may survive")
            else:
                self.fail("unexpected scan")
        ds = (m.VideoDevice("qcom-iris-decoder", "video16", os.makedev(81, 22)),
              m.VideoDevice("qcom-iris-encoder", "video17", os.makedev(81, 24)))
        with patch.object(m.os, "geteuid", return_value=0), \
             patch.object(m, "verified_host_view", return_value=True), \
             patch.object(m, "effective_capabilities", return_value=1 << m.CAP_SYS_PTRACE), \
             patch.object(m.os, "scandir", side_effect=scandir):
            self.assertEqual(m.inspect_device_users(ds, m.HostWitness("test", "pid:[1]")),
                             m.Users(False, None))

    def test_missing_witness_denies_even_root(self):
        with patch.object(m.os, "geteuid", return_value=0):
            self.assertEqual(m.inspect_device_users(()), m.Users(False, None))

    def test_nonroot_process_visibility_unknown(self):
        with patch.object(m.os, "geteuid", return_value=1000):
            self.assertEqual(m.inspect_device_users(()), m.Users(False, None))

    def test_bad_capability_field(self):
        self.r.data[Path("/proc/thread-self/status")] = b"CapEff:\txyz\n"
        with self.assertRaises(m.InspectionError):
            m.effective_capabilities(self.r)


if __name__ == "__main__":
    unittest.main()
