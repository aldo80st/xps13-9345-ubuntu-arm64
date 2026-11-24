#!/usr/bin/env python3
"""Unprivileged M3 diagnostic IPC responder (no grants, no policy, no effects).

Intended to run via systemd socket activation (Accept=yes) under DynamicUser=yes
on accepted stream FD 0, using ``python3 -I -B`` and a pinned root-owned copy
of ``xps_authz_ipc.py`` verified by path provenance and exact SHA-256 digest.
Never listens on a socket in production, never reads or writes policy state,
never imports action adapters, and unconditionally denies ``audit``,
``iris-r0``, and ``thermal`` requests.
"""
from __future__ import annotations

import grp
import hashlib
import hmac
import logging
import os
from pathlib import Path
import pwd
import socket
import stat
import sys
import types

LOG = logging.getLogger(__name__)

AGENT_USER = "xps-agent"
OWNER_USER = "amarquez"
PINNED_LIBEXEC_DIR = Path("/usr/local/libexec/xps-authz-diagnostic")
PINNED_IPC_PATH = PINNED_LIBEXEC_DIR / "xps_authz_ipc.py"
PINNED_IPC_SHA256 = "28ccde3cd89bdf44e84b434a3b71e0158a7478d5d29f3a10adfe947c9e9d0cf4"
MAX_IPC_BYTES = 256 * 1024

FORBIDDEN_UIDS = frozenset({0, 1000})
FORBIDDEN_GIDS = frozenset({0, 1000})
FORBIDDEN_ADMIN_GROUPS = frozenset({
    "root",
    "sudo",
    "adm",
    "docker",
    "lxd",
    "wheel",
    "shadow",
    "disk",
    "staff",
    "operator",
    "systemd-journal",
})


def _verify_root_provenance(path: Path) -> None:
    """Verify ``path`` and all ancestors are root-owned, non-symlink, non-writable."""
    if not isinstance(path, Path) or not path.is_absolute():
        raise PermissionError("pinned IPC path must be absolute")
    if "home" in path.parts[:3]:
        raise PermissionError("user home paths are prohibited for production IPC")

    for directory in reversed(path.parents):
        st = os.lstat(directory)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise PermissionError(f"untrusted directory component: {directory}")
        if st.st_uid != 0 or st.st_gid != 0 or (st.st_mode & 0o022) != 0:
            raise PermissionError(f"directory component not strictly root-owned: {directory}")

    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise PermissionError("pinned IPC module must be a regular non-symlink file")
    if st.st_uid != 0 or st.st_gid != 0 or (st.st_mode & 0o022) != 0:
        raise PermissionError("pinned IPC module must be root-owned and non-writable")


def _load_pinned_ipc(ipc_path: Path = PINNED_IPC_PATH) -> types.ModuleType:
    """Load ``xps_authz_ipc`` strictly from verified root-owned path and SHA-256."""
    _verify_root_provenance(ipc_path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(ipc_path, flags)
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or fst.st_uid != 0 or fst.st_gid != 0 or (fst.st_mode & 0o022) != 0:
            raise PermissionError("pinned IPC descriptor failed provenance check")
        if fst.st_size <= 0 or fst.st_size > MAX_IPC_BYTES:
            raise PermissionError("pinned IPC module size out of bounds")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            source = handle.read()
    finally:
        if fd >= 0:
            os.close(fd)

    actual_sha256 = hashlib.sha256(source).hexdigest()
    if not hmac.compare_digest(actual_sha256, PINNED_IPC_SHA256):
        raise PermissionError("pinned IPC SHA-256 mismatch")

    module = types.ModuleType("xps_authz_ipc")
    module.__file__ = str(ipc_path)
    sys.modules["xps_authz_ipc"] = module
    try:
        exec(compile(source, str(ipc_path), "exec"), module.__dict__)
    except Exception:
        sys.modules.pop("xps_authz_ipc", None)
        raise
    return module


def _get_ipc(ipc_module: types.ModuleType | None = None) -> types.ModuleType:
    if ipc_module is not None:
        return ipc_module
    existing = sys.modules.get("xps_authz_ipc")
    if existing is not None:
        return existing
    if __name__ == "__main__":
        return _load_pinned_ipc(PINNED_IPC_PATH)
    import xps_authz_ipc  # noqa: PLC0415

    return xps_authz_ipc


def resolve_agent_identity() -> tuple[int, int]:
    """Resolve and validate ``xps-agent`` UID/GID via NSS (``pwd``, ``grp``, ``getgrouplist``).

    Rejects root, UID/GID 1000, the NSS-resolved owner account (``amarquez``),
    user-home accounts, mismatched primary group, and any supplementary or
    administrative group membership. This is an NSS/account inventory check
    only and does not prove live process isolation (gate G-ID remains separate).
    """
    forbidden_uids = set(FORBIDDEN_UIDS)
    forbidden_gids = set(FORBIDDEN_GIDS)
    try:
        owner_pw = pwd.getpwnam(OWNER_USER)
    except KeyError:
        owner_pw = None
    if owner_pw is not None:
        forbidden_uids.add(owner_pw.pw_uid)
        forbidden_gids.add(owner_pw.pw_gid)

    pw = pwd.getpwnam(AGENT_USER)
    if pw.pw_name != AGENT_USER:
        raise PermissionError("unexpected passwd entry name")
    uid = pw.pw_uid
    gid = pw.pw_gid
    if (
        type(uid) is not int
        or type(gid) is not int
        or not 0 < uid < 2**32 - 1
        or not 0 < gid < 2**32 - 1
    ):
        raise PermissionError("invalid xps-agent UID/GID range")
    if uid in forbidden_uids or gid in forbidden_gids:
        raise PermissionError("xps-agent must not share root, UID/GID 1000, or owner UID/GID")
    if pw.pw_dir == "/root" or pw.pw_dir.startswith("/home/"):
        raise PermissionError("xps-agent must not have an owner/root home directory")

    primary_group = grp.getgrgid(gid)
    named_group = grp.getgrnam(AGENT_USER)
    if primary_group.gr_name != AGENT_USER or named_group.gr_gid != gid:
        raise PermissionError("xps-agent primary group must match dedicated xps-agent group")
    if primary_group.gr_name in FORBIDDEN_ADMIN_GROUPS:
        raise PermissionError("xps-agent primary group is administrative")

    nss_gids = os.getgrouplist(AGENT_USER, gid)
    if set(nss_gids) != {gid}:
        raise PermissionError("xps-agent has supplementary NSS groups")
    for member_gid in nss_gids:
        if member_gid in forbidden_gids:
            raise PermissionError("xps-agent NSS group list contains forbidden GID")
        member_group = grp.getgrgid(member_gid)
        if member_group.gr_name in FORBIDDEN_ADMIN_GROUPS:
            raise PermissionError(f"xps-agent NSS group list contains admin group: {member_group.gr_name}")

    for group in grp.getgrall():
        if AGENT_USER in group.gr_mem:
            if group.gr_name in FORBIDDEN_ADMIN_GROUPS:
                raise PermissionError(f"xps-agent belongs to forbidden admin group: {group.gr_name}")
            if group.gr_gid != gid:
                raise PermissionError(f"xps-agent has supplementary group: {group.gr_name}")

    return uid, gid


class DiagnosticHandler:
    """Fail-closed diagnostic IPC handler using strict ``SO_PEERCRED``."""

    def __init__(
        self,
        expected_uid: int,
        expected_gid: int,
        *,
        ipc_module: types.ModuleType | None = None,
    ) -> None:
        if (
            type(expected_uid) is not int
            or type(expected_gid) is not int
            or not 0 < expected_uid < 2**32 - 1
            or not 0 < expected_gid < 2**32 - 1
        ):
            raise ValueError("dedicated non-root peer identity required")
        self._uid = expected_uid
        self._gid = expected_gid
        self._ipc = _get_ipc(ipc_module)

    @classmethod
    def from_system(
        cls,
        *,
        ipc_module: types.ModuleType | None = None,
    ) -> DiagnosticHandler:
        if os.geteuid() == 0 or os.getuid() == 0:
            raise PermissionError("diagnostic service must not execute as root")
        uid, gid = resolve_agent_identity()
        return cls(uid, gid, ipc_module=ipc_module)

    def _peer_ok(self, peer: object) -> bool:
        return (
            type(peer) is self._ipc.Peer
            and peer.uid == self._uid
            and peer.gid == self._gid
        )

    def status(self, peer: object):
        if not self._peer_ok(peer):
            return self._ipc.Reply(self._ipc.Result.DENIED, self._ipc.Reason.PEER_DENIED)
        return self._ipc.Reply(
            self._ipc.Result.STATUS,
            lease_remaining_s=0,
            audit_remaining=0,
            iris_remaining=0,
            thermal_remaining=0,
            recovery_pending=False,
        )

    def dispatch(self, request: object, peer: object):
        if not self._peer_ok(peer):
            return self._ipc.Reply(self._ipc.Result.DENIED, self._ipc.Reason.PEER_DENIED)
        if request not in (
            self._ipc.Request.AUDIT,
            self._ipc.Request.IRIS_R0,
            self._ipc.Request.THERMAL,
        ):
            return self._ipc.Reply(self._ipc.Result.DENIED, self._ipc.Reason.INVALID_FRAME)
        return self._ipc.Reply(
            self._ipc.Result.DENIED,
            self._ipc.Reason.NO_LEASE,
            lease_remaining_s=0,
            audit_remaining=0,
            iris_remaining=0,
            thermal_remaining=0,
            recovery_pending=False,
        )

    def handle(self, conn: socket.socket):
        return self._ipc.handle_connection(
            conn,
            self._uid,
            self._gid,
            self.dispatch,
            status_provider=self.status,
        )


def adopt_accepted_socket(fd: int = 0) -> socket.socket:
    """Adopt an accepted ``AF_UNIX`` ``SOCK_STREAM`` descriptor from systemd."""
    if type(fd) is not int or fd < 0:
        raise ValueError("invalid socket descriptor")
    st = os.fstat(fd)
    if not stat.S_ISSOCK(st.st_mode):
        raise ValueError("descriptor is not a socket")
    conn = socket.socket(fileno=fd)
    try:
        if conn.family != socket.AF_UNIX or conn.type != socket.SOCK_STREAM:
            raise ValueError("socket must be AF_UNIX SOCK_STREAM")
        if conn.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 0:
            raise ValueError("descriptor must be an accepted connection, not a listener")
    except Exception:
        conn.detach()
        raise
    return conn


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("diagnostic responder accepts no CLI arguments", file=sys.stderr)
        return 2
    if os.geteuid() == 0 or os.getuid() == 0:
        print("diagnostic responder must not run as root", file=sys.stderr)
        return 1
    try:
        ipc_mod = _load_pinned_ipc(PINNED_IPC_PATH)
        handler = DiagnosticHandler.from_system(ipc_module=ipc_mod)
        conn = adopt_accepted_socket(0)
        handler.handle(conn)
    except Exception:
        LOG.error("XPS AUTHZ diagnostic startup or descriptor adoption failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
