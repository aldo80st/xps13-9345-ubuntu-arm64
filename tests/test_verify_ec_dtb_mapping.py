"""Binary FDT fixtures; no boot/device writes or external compiler needed."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify-ec-dtb-mapping.py"
SPEC = importlib.util.spec_from_file_location("ec_mapping", SCRIPT)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def cells(*v):
    return struct.pack(">%dI" % len(v), *v)


def strings(*v):
    return b"".join(x.encode("ascii") + b"\0" for x in v)


def fixture():
    d = {}
    def node(path, **props):
        parent = path
        while parent not in d:
            d[parent] = {}
            if parent == "/":
                break
            parent = parent.rsplit("/", 1)[0] or "/"
        d[path].update(props)
    node("/", compatible=strings("dell,xps13-9345", "qcom,x1e80100"))
    node("/__symbols__", pmk8550_vadc=strings(M.ADC), i2c5=strings(M.I2C),
         tlmm=strings(M.TLMM), ec_int_n_default=strings(M.PIN))
    node(M.ADC, compatible=strings("qcom,spmi-adc5-gen3"),
         reg=cells(0x9000, 0x9100), phandle=cells(11),
         **{"#io-channel-cells": cells(1)})
    node(M.I2C, compatible=strings("qcom,geni-i2c"), status=strings("okay"))
    node(M.TLMM, compatible=strings("qcom,x1e80100-tlmm"), phandle=cells(12),
         **{"#interrupt-cells": cells(2), "interrupt-controller": b""})
    node(M.PIN, pins=strings("gpio66"), function=strings("gpio"),
         phandle=cells(13), **{"bias-disable": b""})
    order = (0x14a, 0x14b, 0x144, 0x145, 0x146, 0x147, 0x148)
    labels = ("lpddr5_therm", "sys_therm2", "vph_pwr_therm",
              "usb_charger_right_therm", "ssd_conn_therm",
              "vreg_rtmr0_1p8_therm", "keyboard_therm")
    names = tuple("sys_therm%d" % n for n in range(1, 8))
    node(M.EC, compatible=strings("dell,xps13-9345-ec"), reg=cells(0x3b),
         **{"io-channel-names": strings(*names),
            "io-channels": cells(*(v for c in order for v in (11, c))),
            "interrupts-extended": cells(12, 66, 8),
            "pinctrl-0": cells(13), "pinctrl-names": strings("default")})
    for c, label in zip(order, labels):
        node(M.ADC + "/channel@%x" % c, reg=cells(c), label=strings(label))
    return d


def blob(nodes, properties_after_children_at=None):
    names = bytearray()
    offsets = {}
    structure = bytearray()
    def padded(data):
        return data + bytes((-len(data)) % 4)
    def walk(path):
        structure.extend(cells(1))
        structure.extend(padded((path.rsplit("/", 1)[-1]).encode() + b"\0"))
        def properties():
            for name, raw in nodes[path].items():
                if name not in offsets:
                    offsets[name] = len(names)
                    names.extend(name.encode() + b"\0")
                structure.extend(cells(3, len(raw), offsets[name]))
                structure.extend(padded(raw))
        if path != properties_after_children_at:
            properties()
        for child in sorted(nodes):
            if child != "/" and (child.rsplit("/", 1)[0] or "/") == path:
                walk(child)
        if path == properties_after_children_at:
            properties()
        structure.extend(cells(2))
    walk("/")
    structure.extend(cells(9))
    so = 56
    st = so + len(structure)
    return cells(0xd00dfeed, st + len(names), so, st, 40, 17, 16, 0,
                 len(names), len(structure)) + bytes(16) + structure + names


class MappingTests(unittest.TestCase):
    def audit(self, nodes):
        return M.audit_bytes(blob(nodes))

    def test_exact_mapping_and_scope(self):
        r = self.audit(fixture())
        self.assertEqual(r["status"], "STATIC_MAPPING_PASS")
        self.assertFalse(r["boot_authorized"])
        self.assertFalse(r["hardware_accepted"])

    def test_historical_order(self):
        d = fixture()
        d[M.EC]["io-channels"] = cells(*(v for c in
            (0x144, 0x145, 0x146, 0x147, 0x148, 0x14a, 0x14b) for v in (11, c)))
        with self.assertRaisesRegex(M.GateError, "WRONG_SENSOR_PROVIDER_OR_ORDER"):
            self.audit(d)

    def test_wrong_provider_cells(self):
        d = fixture()
        d[M.EC]["io-channels"] = cells(*(v for c in M.CHANNELS for v in (12, c)))
        with self.assertRaisesRegex(M.GateError, "WRONG_SENSOR_PROVIDER_OR_ORDER"):
            self.audit(d)

    def test_redirect_symbol(self):
        d = fixture()
        d["/__symbols__"]["pmk8550_vadc"] = strings(M.TLMM)
        with self.assertRaisesRegex(M.GateError, "WRONG_SYMBOL_TARGET"):
            self.audit(d)

    def test_wrong_adc_compatible(self):
        d = fixture()
        d[M.ADC]["compatible"] = strings("not,adc")
        with self.assertRaisesRegex(M.GateError, "WRONG_ADC_PROVIDER"):
            self.audit(d)

    def test_label(self):
        d = fixture()
        d[M.ADC + "/channel@14a"]["label"] = strings("wrong")
        with self.assertRaisesRegex(M.GateError, "WRONG_ADC_CHANNEL_OR_LABEL"):
            self.audit(d)

    def test_names_single_string(self):
        d = fixture()
        d[M.EC]["io-channel-names"] = strings(" ".join(M.NAMES))
        with self.assertRaisesRegex(M.GateError, "WRONG_SENSOR_NAMES"):
            self.audit(d)

    def test_compatible_single_string(self):
        d = fixture()
        d["/"]["compatible"] = strings("dell,xps13-9345 qcom,x1e80100")
        with self.assertRaisesRegex(M.GateError, "WRONG_PLATFORM"):
            self.audit(d)

    def test_disabled_required_node_and_ancestor(self):
        for path in (M.ADC, M.EC, M.TLMM, M.I2C, M.PIN,
                     M.ADC.rsplit("/", 1)[0], M.ADC + "/channel@14a"):
            with self.subTest(path=path):
                d = fixture()
                d[path]["status"] = strings("disabled")
                with self.assertRaisesRegex(M.GateError, "REQUIRED_NODE_DISABLED"):
                    self.audit(d)

    def test_irq_provider_and_trigger(self):
        for value in (cells(11, 66, 8), cells(12, 65, 8), cells(12, 66, 1)):
            d = fixture()
            d[M.EC]["interrupts-extended"] = value
            with self.assertRaisesRegex(M.GateError, "WRONG_IRQ"):
                self.audit(d)

    def test_irq_provider_binding(self):
        d = fixture()
        del d[M.TLMM]["interrupt-controller"]
        with self.assertRaisesRegex(M.GateError, "WRONG_IRQ_PROVIDER"):
            self.audit(d)

    def test_pinctrl(self):
        d = fixture()
        d[M.PIN]["pins"] = strings("gpio67")
        with self.assertRaisesRegex(M.GateError, "WRONG_PINCTRL"):
            self.audit(d)

    def test_duplicate_phandle_any_node(self):
        d = fixture()
        d["/"]["phandle"] = cells(11)
        with self.assertRaisesRegex(M.GateError, "DUPLICATE_OR_CONFLICTING_PHANDLE"):
            self.audit(d)

    def test_historical_hash(self):
        raw = blob(fixture())
        with mock.patch.object(M, "REJECTED", hashlib.sha256(raw).hexdigest()):
            with self.assertRaisesRegex(M.GateError, "HISTORICAL_DTB_REJECTED"):
                M.audit_bytes(raw)

    def test_sha_mismatch(self):
        with self.assertRaisesRegex(M.GateError, "SHA256_MISMATCH"):
            M.audit_bytes(blob(fixture()), "0" * 64)

    def test_truncated_and_invalid_header(self):
        raw = blob(fixture())
        for bad in (raw[:-1], bytes(64), raw[:30],
                    raw[:8] + cells(1) + raw[12:]):
            with self.subTest(length=len(bad)):
                with self.assertRaises(M.GateError):
                    M.audit_bytes(bad)

    def test_property_after_child(self):
        d = fixture()
        d[M.EC + "/unexpected-child"] = {}
        with self.assertRaisesRegex(M.GateError, "PROPERTY_AFTER_CHILD"):
            M.audit_bytes(blob(d, properties_after_children_at=M.EC))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_fifo_fails_without_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fifo"
            os.mkfifo(p)
            r = subprocess.run([sys.executable, str(SCRIPT), str(p)],
                               capture_output=True, text=True, timeout=3)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(json.loads(r.stdout)["status"], "NO_GO")

    def test_cli_failure_scope(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.dtb"
            p.write_bytes(bytes(64))
            r = subprocess.run([sys.executable, str(SCRIPT), str(p)],
                               capture_output=True, text=True, timeout=5)
            self.assertEqual(r.returncode, 1)
            report = json.loads(r.stdout)
            self.assertEqual(report["status"], "NO_GO")
            self.assertFalse(report["boot_authorized"])
            self.assertFalse(report["hardware_accepted"])


if __name__ == "__main__":
    unittest.main()
