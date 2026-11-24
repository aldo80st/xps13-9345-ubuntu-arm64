"""Static contract for inert XPS AUTHZ systemd fixtures."""

from configparser import ConfigParser
from pathlib import Path
import unittest


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "xps-authz-units"
PREFIX = "xps-authz-lab-"
SERVICES = ("broker", "audit", "thermal", "iris-r0", "recovery")
MODULE_WORKERS = {"iris-r0", "recovery"}


class UnitContractTest(unittest.TestCase):
    def read_unit(self, name, section):
        parser = ConfigParser(interpolation=None, delimiters=("=",))
        parser.optionxform = str
        with (FIXTURES / (PREFIX + name)).open(encoding="utf-8") as fixture:
            parser.read_file(fixture)
        self.assertEqual(parser.defaults(), {})
        self.assertEqual(parser.sections(), ["Unit", section])
        self.assertEqual(
            dict(parser["Unit"]),
            {
                "Description": parser["Unit"]["Description"],
                "ConditionPathExists": "!/usr/bin/true",
            },
        )
        return parser[section]

    def service(self, role):
        return self.read_unit(role + ".service", "Service")

    def test_fixture_inventory(self):
        expected = {PREFIX + role + ".service" for role in SERVICES}
        expected.add(PREFIX + "broker.socket")
        self.assertEqual({path.name for path in FIXTURES.iterdir()}, expected)
        for path in FIXTURES.iterdir():
            self.assertTrue(path.is_file() and not path.is_symlink(), path)

    def test_filesystem_socket(self):
        socket = self.read_unit("broker.socket", "Socket")
        self.assertEqual(
            dict(socket),
            {
                "ListenStream": "/run/xps-authz-lab.sock",
                "Accept": "no",
                "Service": PREFIX + "broker.service",
                "SocketUser": "root",
                "SocketGroup": "xps-agent",
                "SocketMode": "0660",
                "RemoveOnStop": "yes",
            },
        )

    def test_service_directives_and_capability_boundary(self):
        common = {
            "ExecStart": "/usr/bin/true",
            "NoNewPrivileges": "yes",
            "AmbientCapabilities": "",
            "ProtectSystem": "strict",
            "ProtectHome": "yes",
            "PrivateNetwork": "yes",
            "RestrictAddressFamilies": "AF_UNIX",
        }
        root_identity = {"User": "root", "Group": "root"}
        allowed_role_options = {
            "broker": set(root_identity) | {"ProtectKernelModules"},
            "audit": set(),
            "thermal": {
                "DynamicUser", "CPUQuota", "RuntimeMaxSec", "TimeoutStopSec",
                "KillMode", "SendSIGKILL", "ProtectKernelModules",
            },
        }
        for role in SERVICES:
            with self.subTest(role=role):
                service = self.service(role)
                expected = common.copy()
                if role in MODULE_WORKERS:
                    expected.update(root_identity, Type="oneshot",
                                    CapabilityBoundingSet="CAP_SYS_MODULE")
                else:
                    expected.update(Type="exec", CapabilityBoundingSet="",
                                    SystemCallFilter="~@module")
                self.assertEqual(
                    set(service), set(expected) | allowed_role_options.get(role, set())
                )
                for directive, value in expected.items():
                    self.assertEqual(service[directive], value, directive)

    def test_broker_identity(self):
        broker = self.service("broker")
        self.assertEqual(broker["User"], "root")
        self.assertEqual(broker["Group"], "root")
        self.assertEqual(broker["ProtectKernelModules"], "yes")

    def test_audit_preserves_module_file_visibility_in_configuration(self):
        audit = self.service("audit")
        self.assertNotIn("ProtectKernelModules", audit)
        self.assertEqual(audit["ProtectSystem"], "strict")
        self.assertEqual(audit["CapabilityBoundingSet"], "")
        self.assertEqual(audit["SystemCallFilter"], "~@module")

    def test_thermal_bounds(self):
        thermal = self.service("thermal")
        self.assertEqual(thermal["DynamicUser"], "yes")
        self.assertEqual(thermal["ProtectKernelModules"], "yes")
        self.assertEqual(thermal["KillMode"], "control-group")
        self.assertEqual(thermal["SendSIGKILL"], "yes")
        self.assertRegex(thermal["CPUQuota"], r"^[0-9]+%$")
        self.assertRegex(thermal["RuntimeMaxSec"], r"^[0-9]+s$")
        self.assertRegex(thermal["TimeoutStopSec"], r"^[0-9]+s$")
        quota = int(thermal["CPUQuota"][:-1])
        runtime = int(thermal["RuntimeMaxSec"][:-1])
        stop = int(thermal["TimeoutStopSec"][:-1])
        self.assertTrue(0 < quota <= 30, quota)
        self.assertTrue(runtime > 0 and stop > 0 and runtime + stop <= 12,
                        (runtime, stop))


if __name__ == "__main__":
    unittest.main()
