#!/usr/bin/env python3
"""Check the *rendered* GNOME Resources GPU process cells via AT-SPI.

Run while Resources (Qualcomm test) is open on its Processes page.
Never prints PIDs, process names, command lines, or raw accessibility trees.
"""
import argparse
import collections
import re
import sys

GPU_CELL = re.compile(r"^GPU:\s*(N/A|([0-9]+(?:[.,][0-9]+)?)\s*%)$", re.I)


def classify_gpu_cells(names: list[str]) -> tuple[int, int, int]:
    """Return numbers of unknown, measured-zero and measured-positive GPU cells."""
    unknown = zero = positive = 0
    for name in names:
        match = GPU_CELL.fullmatch(name.strip())
        if not match:
            continue
        if match.group(1).upper() == "N/A":
            unknown += 1
        else:
            fraction = float(match.group(2).replace(",", "."))
            if fraction == 0.0:
                zero += 1
            elif fraction > 0.0:
                positive += 1
    return unknown, zero, positive


def read_visible_gpu_cells(application_name: str, limit: int = 3000) -> list[str]:
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError) as exc:
        raise RuntimeError("AT-SPI Python bindings not available") from exc

    desktop = Atspi.get_desktop(0)
    app = None
    for i in range(desktop.get_child_count()):
        try:
            candidate = desktop.get_child_at_index(i)
            if candidate.get_name() == application_name:
                app = candidate
                break
        except Exception:
            continue
    if app is None:
        raise RuntimeError("Resources test application not found in accessible desktop")

    queue = collections.deque([(app, 0)])
    cells = []
    visited = 0
    while queue and visited < limit:
        node, depth = queue.popleft()
        visited += 1
        try:
            if node.get_role_name() == "table cell":
                name = node.get_name() or ""
                if GPU_CELL.fullmatch(name.strip()):
                    cells.append(name)
            if depth < 28:
                for i in range(min(node.get_child_count(), 150)):
                    queue.append((node.get_child_at_index(i), depth + 1))
        except Exception:
            continue
    return cells


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", default="resources-test", help="AT-SPI application name")
    parser.add_argument("--require-positive", action="store_true",
                        help="Require a visible positive GPU measurement during active workload")
    args = parser.parse_args()

    try:
        names = read_visible_gpu_cells(args.app)
    except RuntimeError as exc:
        print(f"INCONCLUSIVE: {exc}")
        return 2

    unknown, zero, positive = classify_gpu_cells(names)
    print(f"RENDERED_GPU_CELLS={unknown + zero + positive}")
    print(f"GPU_NA_CELLS={unknown}")
    print(f"GPU_VALID_ZERO_CELLS={zero}")
    print(f"GPU_POSITIVE_CELLS={positive}")
    print("NO_PROCESS_IDENTIFIERS_EMITTED=YES")
    if unknown == 0 or (zero + positive) == 0:
        print("INCONCLUSIVE: both N/A and measured values required")
        return 2
    if args.require_positive and positive == 0:
        print("FAIL: no positive GPU measurement visible")
        return 1
    print("RENDERED_GPU_SEMANTICS=VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
