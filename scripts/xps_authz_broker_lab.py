"""Unprivileged integration boundary, not a deployable broker or daemon.

No socket listener, privilege activation, grant, revoke, module command,
worker creation, or shell is included. Only trusted in-process laboratory
objects may be supplied. Production identity isolation is a separate gate.
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from xps_authz_ipc import Peer, Reply, Request, Result, Reason, handle_connection

_PHASES = ("admit", "commit", "result", "closed", "recovery_cleared",
           "recovery_reconciled", "owner_closed")
_TERMINAL = ("result", "closed", "recovery_cleared", "recovery_reconciled",
             "owner_closed")


def _reply_from_status(status: object, *, result: Result = Result.STATUS,
                       expected_op: str | None = None,
                       expected_action: str | None = None,
                       after_seq: int | None = None) -> Reply:
    """Expose only bounded, typed data from the trusted policy snapshot."""
    if (type(status) is not dict or status.get("state") != "ok"
            or status.get("reason") == "ledger_fault"):
        # Visible bytes are not evidence of durable acceptance when the
        # policy's storage gate reports uncertainty. Never ACK or expose an
        # operation outcome from this snapshot; the owner must reconcile.
        return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
    remaining = status.get("uses_left")
    recovery = status.get("recovery_required")
    if type(remaining) is not dict or set(remaining) != {"audit", "iris-r0", "thermal"}:
        return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
    if type(recovery) is not bool:
        return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
    seq = status.get("ledger_seq")
    if type(seq) is not int or seq < 0 or "last_operation" not in status:
        return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
    last = status["last_operation"]
    op = phase = outcome = None
    if last is not None:
        if type(last) is not dict or type(last.get("event")) is not str or last["event"] not in _PHASES:
            return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
        op, phase = last.get("op_id"), last["event"]
        last_seq = last.get("seq")
        if type(last_seq) is not int or not 0 < last_seq <= seq or type(last.get("action")) is not str or last["action"] not in (
            "audit", "iris-r0", "thermal"
        ):
            return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
        if type(op) is not str:
            return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
        if phase in _TERMINAL:
            value = last.get("outcome")
            outcome = value if type(value) is str and value in ("pass", "fail", "aborted") else "unknown"
    if expected_op is not None and (
        op != expected_op or last is None or last.get("action") != expected_action
        or type(after_seq) is not int or last["seq"] <= after_seq
    ):
        return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
    reply = Reply(
        result, operation_id=op, operation_phase=phase, operation_outcome=outcome,
        lease_remaining_s=status.get("remaining_seconds"),
        audit_remaining=remaining["audit"], iris_remaining=remaining["iris-r0"],
        thermal_remaining=remaining["thermal"], recovery_pending=recovery,
    )
    try:
        reply.encode()
    except (ValueError, TypeError):
        return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
    return reply


class LabBroker:
    """Serial laboratory dispatcher; never retries a failed/dropped response.

    'ACCEPTED' means the operation ID was durably recorded by the policy;
    its phase/outcome is the ledger result, not an assertion of success.
    A real worker supervisor and production service timeout are NOT provided.
    """

    def __init__(self, expected_uid: int, expected_gid: int,
                 status_reader: Callable[[], dict], action_runner: Callable[[dict], object]):
        if type(expected_uid) is not int or type(expected_gid) is not int or min(expected_uid, expected_gid) <= 0:
            raise ValueError("dedicated non-root peer identity required")
        self._uid, self._gid = expected_uid, expected_gid
        self._status, self._run = status_reader, action_runner
        self._serial = threading.Lock()

    def _peer_ok(self, peer: Peer) -> bool:
        return type(peer) is Peer and peer.uid == self._uid and peer.gid == self._gid

    def status(self, peer: Peer) -> Reply:
        if not self._peer_ok(peer):
            return Reply(Result.DENIED, Reason.PEER_DENIED)
        try:
            return _reply_from_status(self._status())
        except Exception:
            return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)

    def dispatch(self, request: Request, peer: Peer) -> Reply:
        if not self._peer_ok(peer):
            return Reply(Result.DENIED, Reason.PEER_DENIED)
        if type(request) is not Request or request is Request.STATUS:
            return Reply(Result.DENIED, Reason.INVALID_FRAME)
        if not self._serial.acquire(blocking=False):
            return Reply(Result.BUSY, Reason.PRECONDITION)
        try:
            # No user-controlled argv, uid, paths, tokens or operation IDs.
            before = self._status()
            if _reply_from_status(before).result is not Result.STATUS:
                return Reply(Result.ERROR, Reason.POLICY_UNAVAILABLE, recovery_pending=True)
            before_seq = before["ledger_seq"]
            previous_op = (before["last_operation"] or {}).get("op_id")
            result = self._run({"action": request.value})
            op_id = getattr(result, "op_id", None)
            if op_id == "-":
                if getattr(getattr(result, "outcome", None), "value", None) == "DENIED":
                    return Reply(Result.DENIED, Reason.PRECONDITION)
                return Reply(Result.ERROR, Reason.DISPATCH_FAILED, recovery_pending=True)
            if type(op_id) is not str or op_id == previous_op:
                return Reply(Result.ERROR, Reason.DISPATCH_FAILED, recovery_pending=True)
            return _reply_from_status(self._status(), result=Result.ACCEPTED, expected_op=op_id,
                                      expected_action=request.value, after_seq=before_seq)
        except Exception:
            return Reply(Result.ERROR, Reason.DISPATCH_FAILED, recovery_pending=True)
        finally:
            self._serial.release()

    def handle(self, conn) -> Reply:
        return handle_connection(conn, self._uid, self._gid, self.dispatch,
                                 status_provider=self.status)
