#!/usr/bin/env python3
"""Read-only smoke test for Qualcomm msm fdinfo in the isolated Resources helper.

Only aggregate counts and GPU card identities are printed; process metadata
from the helper is never written to disk or echoed.
"""
import argparse
import pathlib
import re
import subprocess
import sys
import time

RE_MSM = re.compile(
    r"Enumerator\((\d+)\)\s*:\s*MsmStats\(\s*gfx_ns:\s*(\d+)\s*,\s*"
    r"client_fingerprint:\s*(\d+)\s*,\s*client_count:\s*(\d+)\s*,?\s*\)"
)
RE_RECORD = re.compile(r"(?m)^    \($")
RE_PID = re.compile(r"(?m)^        pid:\s*(\d+),")
RE_START = re.compile(r"(?m)^        starttime:\s*(\d+),")


def parse_msm_stats(payload: bytes) -> list[tuple[int, int]]:
    text = payload.decode("utf-8", errors="replace")
    return [(int(card), int(ns)) for card, ns, _fp, _count in RE_MSM.findall(text)]


def parse_msm_by_process(payload: bytes) -> dict[tuple[int, int, int], tuple[int, int, int]]:
    """Track process lifetime and GPU card without exposing identifying data."""
    text = payload.decode("utf-8", errors="replace")
    entries: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for record in RE_RECORD.split(text)[1:]:
        pid = RE_PID.search(record)
        started = RE_START.search(record)
        if not (pid and started):
            continue
        for card, nanoseconds, fingerprint, count in RE_MSM.findall(record):
            entries[(int(pid.group(1)), int(started.group(1)), int(card))] = (
                int(nanoseconds), int(fingerprint), int(count)
            )
    return entries


def check_driver(card: int, root: pathlib.Path) -> bool:
    try:
        driver = (root / f"card{card}" / "device/driver").resolve(strict=True).name
    except (OSError, RuntimeError):
        return False
    return driver in {"msm_dpu", "msm"}


def sample(helper: pathlib.Path, root: pathlib.Path) -> tuple[int, int, set[int], dict[tuple[int, int, int], tuple[int, int, int]]]:
    data = subprocess.run(
        [str(helper), "--once", "--ron"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=15,
    ).stdout
    entries = parse_msm_stats(data)
    if not entries:
        raise ValueError("No msm DRM client statistics available")
    cards = {card for card, _ in entries}
    unexpected = [card for card in sorted(cards) if not check_driver(card, root)]
    if unexpected:
        raise ValueError("An MSM client was attributed to a card without the msm driver")
    return len(entries), sum(ns for _, ns in entries), cards, parse_msm_by_process(data)


def stable_activity_ns(before: dict[tuple[int, int, int], tuple[int, int, int]],
                       after: dict[tuple[int, int, int], tuple[int, int, int]]) -> tuple[int, int]:
    shared = before.keys() & after.keys()
    comparable = [key for key in shared if before[key][1:] == after[key][1:]]
    return (len(comparable), sum(after[key][0] - before[key][0] for key in comparable
                                if after[key][0] > before[key][0]))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--helper",
        type=pathlib.Path,
        default=pathlib.Path.home() / ".local/opt/resources-qualcomm-51/resources-processes",
    )
    p.add_argument("--sysfs", type=pathlib.Path, default=pathlib.Path("/sys/class/drm"))
    p.add_argument("--interval", type=float, default=1.25)
    p.add_argument(
        "--expect-activity",
        action="store_true",
        help="Require positive cumulative engine-time change during a known graphics workload",
    )
    args = p.parse_args()
    if not args.helper.is_file() or not args.helper.stat().st_mode & 0o111:
        print("FAIL: isolated helper missing or not executable")
        return 2
    if not 0.1 <= args.interval <= 10:
        p.error("--interval must be between 0.1 and 10 seconds")

    try:
        before = sample(args.helper, args.sysfs)
        time.sleep(args.interval)
        after = sample(args.helper, args.sysfs)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"INCONCLUSIVE: {type(exc).__name__}: {exc}")
        return 2
    # A new process or a new DRM client changes the comparison denominator.
    # Match (pid, starttime, card, client fingerprint, client count) internally.
    stable_count, stable_ns = stable_activity_ns(before[3], after[3])
    positive_delta = stable_ns > 0
    print("MSM_FDINFO=VERIFIED")
    print(f"DRM_CARDS={','.join(str(x) for x in sorted(before[2] | after[2]))}")
    print(f"RECORDS_BEFORE={before[0]}")
    print(f"RECORDS_AFTER={after[0]}")
    print(f"CUMULATIVE_NS_DELTA={after[1] - before[1]}")
    print(f"STABLE_PROCESS_GROUPS={stable_count}")
    print(f"STABLE_PROCESS_ACTIVITY_NS={stable_ns}")
    print(f"ENGINE_ACTIVITY_OBSERVED={'YES' if positive_delta else 'NO'}")
    print("GLOBAL_GPU_UTILIZATION=NOT_INFERRED")
    if args.expect_activity and not positive_delta:
        print("FAIL: no positive delta during expected graphics workload")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
