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
    r"Enumerator\((\d+)\)\s*:\s*MsmStats\(\s*gfx_ns:\s*(\d+)\s*,?\s*\)"
)


def parse_msm_stats(payload: bytes) -> list[tuple[int, int]]:
    text = payload.decode("utf-8", errors="replace")
    return [(int(card), int(ns)) for card, ns in RE_MSM.findall(text)]


def check_driver(card: int, root: pathlib.Path) -> bool:
    try:
        driver = (root / f"card{card}" / "device/driver").resolve(strict=True).name
    except (OSError, RuntimeError):
        return False
    return driver in {"msm_dpu", "msm"}


def sample(helper: pathlib.Path, root: pathlib.Path) -> tuple[int, int, set[int]]:
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
    return len(entries), sum(ns for _, ns in entries), cards


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
    positive_delta = after[1] > before[1]
    print("MSM_FDINFO=VERIFIED")
    print(f"DRM_CARDS={','.join(str(x) for x in sorted(before[2] | after[2]))}")
    print(f"RECORDS_BEFORE={before[0]}")
    print(f"RECORDS_AFTER={after[0]}")
    print(f"CUMULATIVE_NS_DELTA={after[1] - before[1]}")
    print(f"ENGINE_ACTIVITY_OBSERVED={'YES' if positive_delta else 'NO'}")
    print("GLOBAL_GPU_UTILIZATION=NOT_INFERRED")
    if args.expect_activity and not positive_delta:
        print("FAIL: no positive delta during expected graphics workload")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
