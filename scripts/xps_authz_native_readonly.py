"""Fixed read-only XPS AUTHZ v1.1 native inspection candidate.

No module commands, no shell, no device opens, no writes, no workload and no
privileged CLI. The production caller may instantiate this only in a reviewed
root-owned worker. Fixture injection is a trusted laboratory API, never IPC.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import time
from typing import Protocol

MODEL = b"Dell XPS 13 9345"
KERNEL = "7.3.0-11-generic"
ARCH = "aarch64"
STOCK_SRCVERSION = "575ECCB0F64EE1485C4E2FE"
STOCK_SHA = "2183021a89244ad917b3afcbe24f2515c5d671033082f783c22ab817e6c6236b"
KERNEL_SHA = "ab0a1a7dd0af5057a898303f51bca3725066919ec65f1a586d73b99cf00c82e5"
STOCK = Path("/usr/lib/modules") / KERNEL / "kernel/drivers/media/platform/qcom/iris/qcom-iris.ko.zst"
MODULE = Path("/sys/module/qcom_iris")
THERMAL = Path("/sys/class/thermal")
POWER = Path("/sys/class/power_supply")
VIDEOS = Path("/sys/class/video4linux")
IRIS_DRIVER = Path("/sys/bus/platform/drivers/qcom-iris")
EXPECTED_VIDEO_NAMES = frozenset(("qcom-iris-decoder", "qcom-iris-encoder"))
BATTERY_SENSOR = "qcom-battmgr-bat"
# Exact native schema observed on official 7.3.0-11, 2026-11-24.
# Unknown, duplicate or missing zones deny the sample. Kernel updates require
# revalidation, not a fallback to guessed indices or an incomplete max.
EXPECTED_SENSORS = frozenset(
    [f"aoss{i}-thermal" for i in range(4)]
    + [f"camera{i}-thermal" for i in range(2)]
    + [f"cpu{i}-{j}-{side}-thermal" for i in range(3) for j in range(4) for side in ("btm", "top")]
    + [f"cpuss{i}-{side}-thermal" for i in range(3) for side in ("btm", "top")]
    + [f"gpuss-{i}-thermal" for i in range(8)]
    + [f"nsp{i}-thermal" for i in range(4)]
    + ["mem-thermal", "pm8550-thermal", "pm8550ve-2-thermal", "pm8550ve-8-thermal",
       "pm8550ve-9-thermal", "pmc8380-3-thermal", "pmc8380-4-thermal", "pmc8380-5-thermal",
       "pmc8380-6-thermal", BATTERY_SENSOR, "video-thermal"]
)
MAX_READ = 65536
CAP_SYS_MODULE = 16
CAP_SYS_PTRACE = 19


class InspectionError(RuntimeError):
    """Unavailable or untrustworthy evidence; never convert to safe PASS."""


class Reader(Protocol):
    def read(self, path: Path, limit: int = MAX_READ) -> bytes: ...
    def names(self, path: Path) -> tuple[str, ...]: ...
    def resolve(self, path: Path) -> Path: ...
    def stat(self, path: Path) -> os.stat_result: ...


class SystemReader:
    """Trusted OS reader; paths are exclusively constructed by fixed inspectors."""
    def read(self, path: Path, limit: int = MAX_READ) -> bytes:
        if type(limit) is not int or not 0 < limit <= MAX_READ:
            raise InspectionError("bad read limit")
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise InspectionError("not regular pseudo-file")
            data = bytearray()
            while len(data) <= limit:
                chunk = os.read(fd, min(4096, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > limit:
                raise InspectionError("oversized pseudo-file")
            return bytes(data)
        finally:
            os.close(fd)

    def names(self, path: Path) -> tuple[str, ...]:
        names = tuple(sorted(os.listdir(path)))
        if len(names) > 8192:
            raise InspectionError("directory exceeds bound")
        return names

    def resolve(self, path: Path) -> Path:
        return path.resolve(strict=True)

    def stat(self, path: Path) -> os.stat_result:
        return path.stat()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise InspectionError(message)


def text(r: Reader, path: Path, limit: int = 1024) -> str:
    return r.read(path, limit).decode("ascii", errors="strict").strip()


def integer(r: Reader, path: Path) -> int:
    value = text(r, path, 64)
    require(re.fullmatch(r"-?[0-9]{1,18}", value) is not None, "invalid integer")
    return int(value)


def bit(r: Reader, path: Path) -> bool:
    value = integer(r, path)
    require(value in (0, 1), "invalid boolean sensor")
    return bool(value)


def verify_host(r: Reader, arch: str, release: str) -> None:
    require(arch == ARCH and release == KERNEL, "host architecture/kernel mismatch")
    require(r.read(Path("/proc/device-tree/model"), 256).rstrip(b"\0") == MODEL,
            "host model mismatch")


@dataclass(frozen=True)
class PowerThermal:
    external: bool
    battery_pct: float
    battery_temp_c: float
    max_other_temp_c: float
    sensor_count: int

    def allowed(self, *, starting: bool) -> bool:
        return (self.external and self.battery_pct >= 30 and self.battery_temp_c < 40
                and self.max_other_temp_c < (55 if starting else 65))


def read_power_thermal(r: Reader) -> PowerThermal:
    zones: dict[str, int] = {}
    for dirname in r.names(THERMAL):
        if re.fullmatch(r"thermal_zone[0-9]+", dirname) is None:
            continue
        p = THERMAL / dirname
        name = text(r, p / "type", 128)
        require(name in EXPECTED_SENSORS and name not in zones, "thermal schema drift")
        temp = integer(r, p / "temp")
        require(-10000 < temp < 110000, "invalid thermal sample")
        zones[name] = temp
    require(set(zones) == EXPECTED_SENSORS, "thermal sensors missing")
    # Read both power inputs; missing one is UNKNOWN, not False.
    external = [bit(r, POWER / name / "online") for name in ("qcom-battmgr-ac", "qcom-battmgr-usb")]
    b = POWER / "qcom-battmgr-bat"
    require(bit(r, b / "present"), "battery absent")
    full, remaining = integer(r, b / "energy_full"), integer(r, b / "energy_now")
    require(full > 0 and 0 <= remaining <= full, "invalid battery energy")
    return PowerThermal(any(external), remaining * 100.0 / full, zones[BATTERY_SENSOR] / 1000,
                        max(v for name, v in zones.items() if name != BATTERY_SENSOR) / 1000,
                        len(zones))


@dataclass(frozen=True)
class LiveModule:
    loaded: bool
    srcversion: str | None
    refcnt: int | None
    holders: tuple[str, ...]


def read_live_module(r: Reader, witness: HostWitness | None = None) -> LiveModule:
    try:
        r.stat(MODULE)
    except FileNotFoundError:
        # Absence is meaningful only under a boot-bound witness established
        # by the authenticated owner on the physical host, never the agent.
        require(witness is not None and verified_host_view(r, witness),
                "module visibility unknown")
        require("qcom_iris" not in r.names(Path("/sys/module")),
                "module changed during sample")
        return LiveModule(False, None, None, ())
    src = text(r, MODULE / "srcversion", 64)
    require(re.fullmatch(r"[0-9A-F]{20,24}", src) is not None, "invalid srcversion")
    refs = integer(r, MODULE / "refcnt")
    require(refs >= 0, "invalid refcount")
    holders = r.names(MODULE / "holders")
    require(all(re.fullmatch(r"[A-Za-z0-9_]+", n) for n in holders), "invalid holder name")
    return LiveModule(True, src, refs, holders)


@dataclass(frozen=True)
class VideoDevice:
    role: str
    basename: str
    device_number: int


def read_iris_devices(r: Reader) -> tuple[VideoDevice, ...]:
    results: dict[str, VideoDevice] = {}
    for name in r.names(VIDEOS):
        if re.fullmatch(r"video[0-9]+", name) is None:
            continue
        p = VIDEOS / name
        try:
            role = text(r, p / "name", 128)
        except FileNotFoundError:
            continue  # unrelated device may disappear during enumeration
        if role not in EXPECTED_VIDEO_NAMES:
            continue
        require(role not in results, "duplicate iris device")
        require(r.resolve(p / "device/driver") == IRIS_DRIVER, "wrong iris driver")
        dev = text(r, p / "dev", 64)
        require(re.fullmatch(r"[0-9]{1,6}:[0-9]{1,6}", dev) is not None, "invalid sysfs dev number")
        major, minor = map(int, dev.split(":"))
        s = r.stat(Path("/dev") / name)
        require(stat.S_ISCHR(s.st_mode), "not character device")
        require((os.major(s.st_rdev), os.minor(s.st_rdev)) == (major, minor),
                "device number mismatch")
        results[role] = VideoDevice(role, name, s.st_rdev)
    require(set(results) == EXPECTED_VIDEO_NAMES, "iris device set incomplete")
    require(len({d.device_number for d in results.values()}) == 2, "device number alias")
    return tuple(results[k] for k in sorted(results))


def effective_capabilities(r: Reader) -> int:
    data = text(r, Path("/proc/thread-self/status"), MAX_READ)
    fields = re.findall(r"(?m)^CapEff:\s*([0-9a-fA-F]{1,16})$", data)
    require(len(fields) == 1, "effective capabilities unknown")
    return int(fields[0], 16)


def _identity(s: os.stat_result) -> tuple:
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_uid, s.st_mode


def hash_protected_file(path: Path, maximum: int) -> str:
    # Fixed canonical paths, no symlink resolution through writable ancestors.
    # Ubuntu /lib is usrmerged; use the canonical /usr/lib/modules path.
    allowed = {STOCK, Path("/boot/vmlinuz-" + KERNEL), Path("/boot/grub/grub.cfg")}
    require(path in allowed and path.is_absolute(), "unexpected root file")
    parts = path.parts
    require(parts[0] == "/" and len(parts) >= 2 and all(x not in ("", ".", "..") for x in parts[1:]),
            "invalid root path")
    dirflags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    dfd = os.open("/", dirflags)
    try:
        for segment in parts[1:-1]:
            ds = os.fstat(dfd)
            require(stat.S_ISDIR(ds.st_mode) and ds.st_uid == 0 and ds.st_mode & 0o022 == 0,
                    "unprotected root directory")
            newfd = os.open(segment, dirflags, dir_fd=dfd)
            os.close(dfd)
            dfd = newfd
        ds = os.fstat(dfd)
        require(stat.S_ISDIR(ds.st_mode) and ds.st_uid == 0 and ds.st_mode & 0o022 == 0,
                "unprotected root directory")
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=dfd)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_mode & 0o022 == 0,
                    "unprotected root file")
            require(0 < before.st_size <= maximum, "root file size outside bound")
            h = hashlib.sha256()
            total = 0
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    break
                total += len(block)
                require(total <= maximum, "root file grew outside bound")
                h.update(block)
            after = os.fstat(fd)
            named = os.stat(parts[-1], dir_fd=dfd, follow_symlinks=False)
            require(total == before.st_size and _identity(before) == _identity(after) == _identity(named),
                    "root file changed during read")
            return h.hexdigest()
        finally:
            os.close(fd)
    finally:
        os.close(dfd)


def read_official_hash() -> str:
    return hash_protected_file(STOCK, 16 * 1024 * 1024)


def audit_boot_readonly() -> dict:
    # Only hashes, no GRUB content, key material, UUIDs or cmdline values.
    fields = {}
    for label, path, maximum in (
        ("vmlinuz_sha256", Path("/boot/vmlinuz-" + KERNEL), 128 * 1024 * 1024),
        ("grub_cfg_sha256", Path("/boot/grub/grub.cfg"), 4 * 1024 * 1024),
    ):
        try:
            fields[label] = hash_protected_file(path, maximum)
        except (PermissionError, FileNotFoundError):
            fields[label] = None
    fields["vmlinuz_matches_pinned"] = (None if fields["vmlinuz_sha256"] is None
                                        else fields["vmlinuz_sha256"] == KERNEL_SHA)
    return fields


def _mount_rows(mountinfo: str) -> list[tuple[list[str], list[str]]]:
    rows = []
    for line in mountinfo.splitlines():
        left, sep, right = line.partition(" - ")
        if not sep:
            raise InspectionError("invalid mountinfo")
        a, b = left.split(), right.split()
        require(len(a) >= 6 and len(b) >= 3, "invalid mountinfo row")
        rows.append((a, b))
    return rows


def proc_mount_full_visibility(mountinfo: str) -> bool:
    try:
        all_rows = _mount_rows(mountinfo)
        rows = [(a, b) for a, b in all_rows if a[4] == "/proc"]
        if len(rows) != 1:
            return False
        a, b = rows[0]
        if b[0] != "proc" or a[3] != "/":
            return False
        if any(re.match(r"^/proc/(?:[0-9]+|self|thread-self)(?:/|$)", x[4])
               for x, _ in all_rows):
            return False
        options = set(a[5].split(",")) | set(b[2].split(","))
        return not any((o.startswith("hidepid=") and o != "hidepid=0") or o.startswith("subset=")
                       for o in options)
    except InspectionError:
        return False


def sysfs_module_full_visibility(mountinfo: str) -> bool:
    try:
        all_rows = _mount_rows(mountinfo)
        rows = [(a, b) for a, b in all_rows if a[4] == "/sys"]
        if len(rows) != 1:
            return False
        a, b = rows[0]
        return (a[3] == "/" and b[0] == "sysfs"
                and not any(x[4] == "/sys/module" or x[4].startswith("/sys/module/")
                            for x, _ in all_rows))
    except InspectionError:
        return False


@dataclass(frozen=True)
class HostWitness:
    """Trusted owner-issued, root-protected, per-boot host observation.

    The owner activation must establish these values from the physical host,
    not a nested container or the MCP. This object alone is not attestation;
    production provisioning/authentication remains an explicit gate.
    """
    boot_id: str
    pid_namespace: str


def verified_host_view(r: Reader, witness: HostWitness) -> bool:
    try:
        if type(witness) is not HostWitness:
            return False
        boot_id = text(r, Path("/proc/sys/kernel/random/boot_id"), 64)
        if re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot_id) is None:
            return False
        if boot_id != witness.boot_id or re.fullmatch(r"pid:\[[0-9]+\]", witness.pid_namespace) is None:
            return False
        if os.readlink("/proc/1/ns/pid") != witness.pid_namespace:
            return False
        if os.readlink("/proc/thread-self/ns/pid") != witness.pid_namespace:
            return False
        if text(r, Path("/proc/1/comm"), 64) != "systemd":
            return False
        s = text(r, Path("/proc/thread-self/status"), MAX_READ)
        ns = re.findall(r"(?m)^NSpid:\s*([0-9\t ]+)$", s)
        if len(ns) != 1 or len(ns[0].split()) != 1:
            return False
        mounts = text(r, Path("/proc/thread-self/mountinfo"), MAX_READ)
        return proc_mount_full_visibility(mounts) and sysfs_module_full_visibility(mounts)
    except (OSError, ValueError, InspectionError):
        return False


@dataclass(frozen=True)
class Users:
    visible: bool
    count: int | None


def inspect_device_users(devices: tuple[VideoDevice, ...], witness: HostWitness | None = None) -> Users:
    # Native root-only gate with independently provisioned per-boot host witness.
    # No command lines, environments, fd targets or contents are read.
    r = SystemReader()
    if os.geteuid() != 0 or witness is None:
        return Users(False, None)
    try:
        require(verified_host_view(r, witness), "host proc/sysfs view not established")
        require(effective_capabilities(r) & (1 << CAP_SYS_PTRACE) != 0, "missing process visibility capability")
        target = {d.device_number for d in devices}
        require(len(target) == 2, "invalid iris device set")
        end = time.monotonic() + 5.0
        n_pids = n_threads = n_fds = 0
        users: set[int] = set()
        with os.scandir("/proc") as procs:
            for process in procs:
                if not process.name.isascii() or not process.name.isdigit():
                    continue
                n_pids += 1
                require(n_pids <= 8192 and time.monotonic() < end, "process scan limit")
                try:
                    with os.scandir(Path("/proc") / process.name / "task") as tasks:
                        for task in tasks:
                            if not task.name.isascii() or not task.name.isdigit():
                                continue
                            n_threads += 1
                            require(n_threads <= 32768 and time.monotonic() < end, "thread scan limit")
                            try:
                                with os.scandir(Path(task.path) / "fd") as fds:
                                    for fd in fds:
                                        n_fds += 1
                                        require(n_fds <= 250000 and time.monotonic() < end, "fd scan limit")
                                        try:
                                            st = fd.stat(follow_symlinks=True)
                                        except (FileNotFoundError, ProcessLookupError):
                                            continue
                                        if stat.S_ISCHR(st.st_mode) and st.st_rdev in target:
                                            users.add(int(process.name))
                            except (FileNotFoundError, ProcessLookupError) as exc:
                                # Cannot prove that a vanished fd directory means
                                # all threads/descriptors have exited.
                                raise InspectionError("thread fd directory visibility changed") from exc
                except (FileNotFoundError, ProcessLookupError) as exc:
                    # /proc/<pid>/task can disappear after leader exit even
                    # while sibling threads survive. Never assume group exit.
                    raise InspectionError("process task directory visibility changed") from exc
        require(time.monotonic() < end, "process scan deadline")
        # This is still a sample, not a lock on future opens. Kernel refcount
        # and the non-force unload guard are mandatory at the commit point.
        return Users(True, len(users))
    except (OSError, ValueError, InspectionError):
        return Users(False, None)


def collect_native_readonly() -> dict:
    r = SystemReader()
    u = os.uname()
    verify_host(r, u.machine, u.release)
    caps = effective_capabilities(r)
    require(caps & (1 << CAP_SYS_MODULE) == 0, "audit has CAP_SYS_MODULE")
    digest = read_official_hash()
    module = read_live_module(r)
    devices = read_iris_devices(r)
    power = read_power_thermal(r)
    return {
        "scope": "read-only snapshot; no module operation, no thermal workload",
        "arch": ARCH,
        "kernel": KERNEL,
        "host_model_ok": True,
        "cap_sys_module_absent": True,
        "official_module_sha256": digest,
        "official_module_matches": digest == STOCK_SHA,
        "loaded_srcversion_matches": module.loaded and module.srcversion == STOCK_SRCVERSION,
        "module_refcnt": module.refcnt,
        "module_holders_count": len(module.holders),
        "iris_device_roles": [d.role for d in devices],
        "sensor_count": power.sensor_count,
        "external_power": power.external,
        "battery_pct": round(power.battery_pct, 2),
        "battery_temp_c": power.battery_temp_c,
        "max_other_temp_c": power.max_other_temp_c,
        "thermal_start_envelope_ok": power.allowed(starting=True),
        "boot": audit_boot_readonly(),
        "uid": os.geteuid(),
        "privileged_audit_acceptance": "NOT_RUN",
    }
