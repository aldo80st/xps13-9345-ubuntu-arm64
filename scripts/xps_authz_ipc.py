#!/usr/bin/env python3
"""Strict local XPS AUTHZ request framing, peer identity and sanitized replies.

Laboratory component: no listener, privileged operation, owner grant, systemd
activation or filesystem mutation is provided here. The trusted caller must
supply a dispatch adapter implementing durable policy admission.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import logging
import re
import socket
import struct
import time
from typing import Callable

LOG = logging.getLogger(__name__)
MAX_FRAME = 8  # longest of iris-r0\\n and thermal\\n
MAX_REPLY = 512
READ_TIMEOUT_S = 2.0
WRITE_TIMEOUT_S = 1.0
UCRED = struct.Struct("=iII")


class Request(Enum):
    STATUS = "status"
    AUDIT = "audit"
    IRIS_R0 = "iris-r0"
    THERMAL = "thermal"


class Result(Enum):
    STATUS = "STATUS"
    ACCEPTED = "ACCEPTED"
    DENIED = "DENIED"
    BUSY = "BUSY"
    ERROR = "ERROR"


class Reason(Enum):
    NONE = "NONE"
    INVALID_FRAME = "INVALID_FRAME"
    PEER_DENIED = "PEER_DENIED"
    TIMEOUT = "TIMEOUT"
    NO_LEASE = "NO_LEASE"
    EXPIRED_OR_REVOKED = "EXPIRED_OR_REVOKED"
    EXHAUSTED = "EXHAUSTED"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"
    PRECONDITION = "PRECONDITION"
    DISPATCH_FAILED = "DISPATCH_FAILED"


@dataclass(frozen=True)
class Peer:
    pid: int
    uid: int
    gid: int


@dataclass(frozen=True)
class Reply:
    result: Result
    reason: Reason = Reason.NONE
    operation_id: str | None = None
    lease_remaining_s: int = 0
    audit_remaining: int = 0
    iris_remaining: int = 0
    thermal_remaining: int = 0
    recovery_pending: bool = False
    operation_phase: str | None = None
    operation_outcome: str | None = None

    def encode(self) -> bytes:
        if type(self.result) is not Result or type(self.reason) is not Reason:
            raise ValueError("invalid response enum")
        if self.operation_id is not None:
            if type(self.operation_id) is not str or re.fullmatch(
                r"[0-9a-f]{32}", self.operation_id
            ) is None:
                raise ValueError("invalid operation id")
        if self.result is Result.ACCEPTED and self.operation_id is None:
            raise ValueError("accepted without durable operation id")
        if self.result is not Result.ACCEPTED and self.result is not Result.STATUS:
            if self.operation_id is not None:
                raise ValueError("unexpected operation id")
        for value, maximum in (
            (self.lease_remaining_s, 1200),
            (self.audit_remaining, 5),
            (self.iris_remaining, 1),
            (self.thermal_remaining, 1),
        ):
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError("invalid response counter")
        if type(self.recovery_pending) is not bool:
            raise ValueError("invalid recovery flag")
        if self.operation_phase is not None and type(self.operation_phase) is not str:
            raise ValueError("invalid operation phase type")
        if self.operation_outcome is not None and type(self.operation_outcome) is not str:
            raise ValueError("invalid operation outcome type")
        if self.operation_phase not in (None, "admit", "commit", "result", "closed", "recovery_cleared", "recovery_reconciled", "owner_closed"):
            raise ValueError("invalid operation phase")
        if self.operation_outcome not in (None, "pass", "fail", "aborted", "unknown"):
            raise ValueError("invalid operation outcome")
        if (self.operation_phase is not None or self.operation_outcome is not None) and (
            self.operation_id is None or self.result not in (Result.STATUS, Result.ACCEPTED)
        ):
            raise ValueError("unexpected operation status")
        if self.result in (Result.STATUS, Result.ACCEPTED):
            if self.reason is not Reason.NONE:
                raise ValueError("successful response cannot have error reason")
        elif self.reason is Reason.NONE:
            raise ValueError("unsuccessful response needs a reason")
        if self.operation_outcome is not None and self.operation_phase not in (
            "result", "closed", "recovery_cleared", "recovery_reconciled", "owner_closed"
        ):
            raise ValueError("outcome requires terminal phase")
        if self.operation_phase in (
            "result", "closed", "recovery_cleared", "recovery_reconciled", "owner_closed"
        ) and self.operation_outcome is None:
            raise ValueError("terminal phase requires outcome")
        data = {
            "result": self.result.value,
            "reason": self.reason.value,
            "operation_id": self.operation_id,
            "operation_phase": self.operation_phase,
            "operation_outcome": self.operation_outcome,
            "lease_remaining_s": self.lease_remaining_s,
            "remaining": {
                "audit": self.audit_remaining,
                "iris-r0": self.iris_remaining,
                "thermal": self.thermal_remaining,
            },
            "recovery_pending": self.recovery_pending,
        }
        raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
        if len(raw) > MAX_REPLY:
            raise ValueError("response too large")
        return raw


_FRAMES = {request.value.encode("ascii") + b"\n": request for request in Request}


def parse_request(frame: bytes) -> Request:
    if type(frame) is not bytes or len(frame) > MAX_FRAME:
        raise ValueError("invalid frame")
    try:
        return _FRAMES[frame]
    except KeyError:
        raise ValueError("invalid frame") from None


def authenticated_peer(
    conn: socket.socket, expected_uid: int, expected_gid: int
) -> Peer:
    # No root or wildcard identity accepted. The expected IDs must come from
    # root-protected installation config, never from a client message or env.
    if (
        type(expected_uid) is not int
        or type(expected_gid) is not int
        or not 0 < expected_uid < 2**32 - 1
        or not 0 < expected_gid < 2**32 - 1
        or conn.family != socket.AF_UNIX
        or conn.type != socket.SOCK_STREAM
        or not hasattr(socket, "SO_PEERCRED")
    ):
        raise PermissionError("invalid peer configuration")
    raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, UCRED.size)
    if len(raw) != UCRED.size:
        raise PermissionError("invalid credentials")
    pid, uid, gid = UCRED.unpack(raw)
    if pid <= 0 or uid != expected_uid or gid != expected_gid:
        raise PermissionError("peer rejected")
    return Peer(pid, uid, gid)


def read_frame(conn: socket.socket) -> bytes:
    # Absolute deadline avoids slowloris reset by individual recv calls.
    # Require EOF after LF; a second command/trailing byte never dispatches.
    deadline = time.monotonic() + READ_TIMEOUT_S
    chunks = bytearray()
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("request deadline")
        conn.settimeout(left)
        chunk = conn.recv(MAX_FRAME + 1 - len(chunks))
        if not chunk:
            return bytes(chunks)
        chunks.extend(chunk)
        if len(chunks) > MAX_FRAME:
            raise ValueError("oversized frame")


Dispatch = Callable[[Request, Peer], Reply]


def handle_connection(
    conn: socket.socket, expected_uid: int, expected_gid: int, dispatch: Dispatch,
    *, status_provider: Callable[[Peer], Reply] | None = None,
) -> Reply:
    """Handle exactly one accepted Unix stream. Own and close the connection.

    The dispatch adapter must implement admission and durable receipts, and
    must not block indefinitely. A transport failure never retries a request.
    Status is routed only to its own read-only provider, never dispatch.
    Root/owner operations are deliberately not part of this protocol.
    """
    with conn:
        try:
            peer = authenticated_peer(conn, expected_uid, expected_gid)
        except (PermissionError, OSError, ValueError, struct.error):
            reply = Reply(Result.DENIED, Reason.PEER_DENIED)
            # Do not read attacker-controlled request bytes after peer failure.
        else:
            try:
                request = parse_request(read_frame(conn))
            except TimeoutError:
                reply = Reply(Result.DENIED, Reason.TIMEOUT)
            except (ValueError, OSError):
                reply = Reply(Result.DENIED, Reason.INVALID_FRAME)
            else:
                try:
                    if request is Request.STATUS:
                        if status_provider is None:
                            raise ValueError("status provider unavailable")
                        candidate = status_provider(peer)
                    else:
                        candidate = dispatch(request, peer)
                    if type(candidate) is not Reply:
                        raise ValueError("wrong dispatch response")
                    # Verify the shape before writing anything to the peer.
                    candidate.encode()
                    if request is Request.STATUS and candidate.result is Result.ACCEPTED:
                        raise ValueError("status cannot admit an action")
                    if request is not Request.STATUS and candidate.result is Result.STATUS:
                        raise ValueError("action cannot be acknowledged as status")
                    reply = candidate
                except Exception:
                    # No tracebacks, filenames or exception values in response.
                    LOG.error("XPS AUTHZ dispatch failed")
                    reply = Reply(Result.ERROR, Reason.DISPATCH_FAILED)
        try:
            conn.settimeout(WRITE_TIMEOUT_S)
            conn.sendall(reply.encode())
        except (OSError, ValueError):
            # The peer can query status later. A failed reply is not an action
            # failure and never triggers a replay; only the ledger decides.
            LOG.warning("XPS AUTHZ response delivery failed")
        return reply
