#!/usr/bin/env python3
"""Offline semantic mapping gate for the Dell XPS 13 9345 EC v8 DTB.

No kernel, boot, firmware, device or file writes. This narrow gate does not
validate the entire device tree or authorize deployment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys

CHANNELS = (0x14a, 0x14b, 0x144, 0x145, 0x146, 0x147, 0x148)
LABELS = ("lpddr5_therm", "sys_therm2", "vph_pwr_therm",
          "usb_charger_right_therm", "ssd_conn_therm",
          "vreg_rtmr0_1p8_therm", "keyboard_therm")
NAMES = tuple("sys_therm%d" % n for n in range(1, 8))
REJECTED = "42aa439d646ee83bf20bbcf062dd8c9b441962167eed2d9b0d9bcd3b97c60e06"
MAX_DTB = 16 * 1024 * 1024
ADC = "/soc@0/arbiter@c400000/spmi@c42d000/pmic@0/adc@9000"
I2C = "/soc@0/geniqup@bc0000/i2c@b94000"
TLMM = "/soc@0/pinctrl@f100000"
PIN = TLMM + "/ec-int-n-state"
EC = I2C + "/embedded-controller@3b"


class GateError(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise GateError(reason)


def parse_dtb(data):
    """Bounded FDT v17 decoder; preserve exact property bytes and string lists."""
    require(40 <= len(data) <= MAX_DTB, "INVALID_DTB_SIZE")
    magic, total, so, st, mr, ver, compat, _, ss, sz = struct.unpack_from(">10I", data)
    require(magic == 0xd00dfeed and total == len(data) and ver == 17
            and compat <= ver, "INVALID_FDT_HEADER")
    require(so >= 40 and so % 4 == 0 and sz >= 4 and so + sz <= total
            and st >= 40 and st + ss <= total
            and (so + sz <= st or st + ss <= so)
            and 40 <= mr < min(so, st) and mr % 8 == 0,
            "INVALID_FDT_BLOCKS")
    limit = min(so, st)
    while True:
        require(mr + 16 <= limit, "INVALID_RESERVATION_MAP")
        address, length = struct.unpack_from(">QQ", data, mr)
        mr += 16
        if address == length == 0:
            break
    end = so + sz
    nodes = {}
    stack = []
    children_started = set()
    i = so
    while i + 4 <= end:
        token = struct.unpack_from(">I", data, i)[0]
        i += 4
        if token == 1:  # FDT_BEGIN_NODE
            j = data.find(b"\0", i, end)
            require(j >= i, "UNTERMINATED_NODE")
            name = data[i:j].decode("ascii")
            i = (j + 4) & ~3
            require(i <= end and "/" not in name and name not in (".", ".."),
                    "INVALID_NODE_NAME")
            if stack:
                children_started.add(stack[-1])
                require(bool(name), "EMPTY_CHILD_NAME")
                path = stack[-1].rstrip("/") + "/" + name
            else:
                require(not nodes and name == "", "INVALID_ROOT")
                path = "/"
            require(path not in nodes, "DUPLICATE_NODE")
            nodes[path] = {}
            stack.append(path)
        elif token == 2:  # FDT_END_NODE
            require(bool(stack), "UNBALANCED_NODE")
            stack.pop()
        elif token == 3:  # FDT_PROP
            require(stack and i + 8 <= end, "INVALID_PROPERTY")
            require(stack[-1] not in children_started, "PROPERTY_AFTER_CHILD")
            n, no = struct.unpack_from(">II", data, i)
            i += 8
            require(no < ss and i + n <= end, "INVALID_PROPERTY_LENGTH")
            j = data.find(b"\0", st + no, st + ss)
            require(j > st + no, "INVALID_PROPERTY_NAME")
            name = data[st + no:j].decode("ascii")
            require("/" not in name and name not in nodes[stack[-1]],
                    "DUPLICATE_OR_INVALID_PROPERTY")
            nodes[stack[-1]][name] = data[i:i + n]
            i = (i + n + 3) & ~3
            require(i <= end, "INVALID_PROPERTY_PADDING")
        elif token == 4:  # FDT_NOP
            continue
        elif token == 9:  # FDT_END
            require(not stack and "/" in nodes and i == end, "INVALID_FDT_END")
            return nodes
        else:
            raise GateError("INVALID_FDT_TOKEN")
    raise GateError("MISSING_FDT_END")


def get(nodes, node, prop, kind):
    require(node in nodes and prop in nodes[node], "MISSING_PROPERTY")
    raw = nodes[node][prop]
    if kind == "s":
        require(raw.endswith(b"\0"), "INVALID_STRING_LIST")
        return tuple(s.decode("ascii") for s in raw[:-1].split(b"\0"))
    require(kind == "x" and len(raw) % 4 == 0, "INVALID_CELL_LIST")
    return struct.unpack(">%dI" % (len(raw) // 4), raw)


def phandles(nodes):
    owners = {}
    for node, props in nodes.items():
        vals = []
        for key in ("phandle", "linux,phandle"):
            if key in props:
                cells = get(nodes, node, key, "x")
                require(len(cells) == 1 and 0 < cells[0] < 0xffffffff,
                        "INVALID_PHANDLE")
                vals.append(cells[0])
        if vals:
            require(len(set(vals)) == 1 and vals[0] not in owners,
                    "DUPLICATE_OR_CONFLICTING_PHANDLE")
            owners[vals[0]] = node
    return owners


def enabled(nodes, node):
    while True:
        require(node in nodes, "MISSING_REQUIRED_NODE")
        if "status" in nodes[node]:
            require(get(nodes, node, "status", "s") in (("okay",), ("ok",)),
                    "REQUIRED_NODE_DISABLED")
        if node == "/":
            break
        node = node.rsplit("/", 1)[0] or "/"


def validate(nodes):
    def prop(node, name, kind):
        return get(nodes, node, name, kind)

    require(prop("/", "compatible", "s") == ("dell,xps13-9345", "qcom,x1e80100"),
            "WRONG_PLATFORM")
    for name, path in (("pmk8550_vadc", ADC), ("i2c5", I2C),
                       ("tlmm", TLMM), ("ec_int_n_default", PIN)):
        require(prop("/__symbols__", name, "s") == (path,), "WRONG_SYMBOL_TARGET")
    for node in (ADC, I2C, TLMM, PIN, EC):
        enabled(nodes, node)
    require(prop(ADC, "compatible", "s") == ("qcom,spmi-adc5-gen3",)
            and prop(ADC, "reg", "x") == (0x9000, 0x9100),
            "WRONG_ADC_PROVIDER")
    require(prop(I2C, "compatible", "s") == ("qcom,geni-i2c",)
            and prop(I2C, "status", "s") == ("okay",),
            "WRONG_I2C_PROVIDER")
    require(prop(TLMM, "compatible", "s") == ("qcom,x1e80100-tlmm",)
            and nodes[TLMM].get("interrupt-controller") == b"",
            "WRONG_IRQ_PROVIDER")
    require(prop(EC, "compatible", "s") == ("dell,xps13-9345-ec",)
            and prop(EC, "reg", "x") == (0x3b,), "WRONG_EC_NODE")
    require(prop(ADC, "#io-channel-cells", "x") == (1,), "WRONG_ADC_CELLS")
    owners = phandles(nodes)
    def provider(node):
        values = [k for k, v in owners.items() if v == node]
        require(len(values) == 1, "MISSING_PROVIDER_PHANDLE")
        return values[0]
    a, t, p = (provider(node) for node in (ADC, TLMM, PIN))
    require(prop(EC, "io-channel-names", "s") == NAMES, "WRONG_SENSOR_NAMES")
    require(prop(EC, "io-channels", "x") ==
            tuple(v for ch in CHANNELS for v in (a, ch)),
            "WRONG_SENSOR_PROVIDER_OR_ORDER")
    for ch, label in zip(CHANNELS, LABELS):
        node = ADC + "/channel@%x" % ch
        enabled(nodes, node)
        require(prop(node, "reg", "x") == (ch,)
                and prop(node, "label", "s") == (label,),
                "WRONG_ADC_CHANNEL_OR_LABEL")
    require(prop(TLMM, "#interrupt-cells", "x") == (2,), "WRONG_IRQ_CELLS")
    require(prop(EC, "interrupts-extended", "x") == (t, 66, 8), "WRONG_IRQ")
    require(prop(EC, "pinctrl-0", "x") == (p,)
            and prop(EC, "pinctrl-names", "s") == ("default",)
            and prop(PIN, "pins", "s") == ("gpio66",)
            and prop(PIN, "function", "s") == ("gpio",)
            and nodes[PIN].get("bias-disable") == b"", "WRONG_PINCTRL")
    return {"mapping": "PASS", "channels": [hex(c) for c in CHANNELS],
            "sensor_names": list(NAMES), "irq_gpio": 66}


def audit_bytes(data, expected=None):
    require(40 <= len(data) <= MAX_DTB, "INVALID_DTB_SIZE")
    digest = hashlib.sha256(data).hexdigest()
    require(digest != REJECTED, "HISTORICAL_DTB_REJECTED")
    if expected is not None:
        require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None
                and expected == digest, "SHA256_MISMATCH")
    report = validate(parse_dtb(data))
    return {"status": "STATIC_MAPPING_PASS", "sha256": digest,
            **report, "boot_authorized": False, "hardware_accepted": False,
            "scope": "mapping/IRQ/pinctrl only; verify exact kernel base separately"}


def audit(path, expected=None):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        before = os.fstat(f.fileno())
        require(stat.S_ISREG(before.st_mode) and 40 <= before.st_size <= MAX_DTB,
                "INVALID_DTB_SIZE")
        data = f.read(MAX_DTB + 1)
        after = os.fstat(f.fileno())
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after) == identity(path.stat())
            and len(data) == before.st_size, "DTB_CHANGED_DURING_READ")
    return audit_bytes(data, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dtb", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        report = audit(args.dtb, args.expected_sha256)
    except (OSError, ValueError, struct.error) as exc:
        reason = str(exc) if isinstance(exc, GateError) else "INVALID_OR_UNREADABLE_DTB"
        print(json.dumps({"status": "NO_GO", "reason": reason,
                          "boot_authorized": False, "hardware_accepted": False}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

