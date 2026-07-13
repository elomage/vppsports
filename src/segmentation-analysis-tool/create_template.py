from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from segment_template import build_track_template
from ANALYSIS_TOOL.analyze_single_ride import TEMPLATES_DIR
from analyze_single_ride import load_rides, DATASETS, EXPECTED_CURVES_PER_TRACK


MIN_REFS = 3
DEFAULT_MAX_REFS = 5


def build_one(dataset_name: str, dataset_path: Path,
              expected_n_curves: int, max_refs: int,
              force: bool) -> tuple[str, str]:

    out_path = TEMPLATES_DIR / f"{dataset_name}.pkl"

    if out_path.exists() and not force:
        return "skip", f"cached -> {out_path.name}"

    rides = load_rides(dataset_path)
    if len(rides) < MIN_REFS:
        return "fail", f"only {len(rides)} rides (need >={MIN_REFS})"

    ride_items = list(rides.items())[:max_refs]
    refs = [(data["accel"], data.get("gyro")) for _, data in ride_items]

    t0 = time.perf_counter()
    template = build_track_template(
        rides=refs,
        track_name=dataset_name,
        expected_n_curves=expected_n_curves,
    )
    elapsed = time.perf_counter() - t0

    template.save(out_path)

    n_curves = sum(1 for k in template.kinds if k.startswith("curve"))
    n_straights = sum(1 for k in template.kinds if k == "straight")
    msg = (f"{len(refs)} refs | {n_curves}C/{n_straights}S "
           f"(target={expected_n_curves}) | {elapsed:.1f}s -> {out_path.name}")
    return "ok", msg


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--track", default=None,
                        help="Only build tracks whose name contains this substring "
                             "(case-insensitive). Default: build all.")
    parser.add_argument("--max-refs", type=int, default=DEFAULT_MAX_REFS,
                        help=f"Max reference rides per template (default {DEFAULT_MAX_REFS}).")
    parser.add_argument("--force", action="store_true",
                        help="Rebuild templates even if a cached .pkl exists.")
    args = parser.parse_args()

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Templates directory: {TEMPLATES_DIR}")
    print(f"Datasets configured:  {len(DATASETS)}")
    print()

    selected = {
        name: path for name, path in DATASETS.items()
        if args.track is None or args.track.lower() in name.lower()
    }
    if not selected:
        print(f"No datasets match --track={args.track!r}.")
        return 1

    results: list[tuple[str, str, str]] = []
    for name, path in selected.items():
        print(f"[{name}]")
        if name not in EXPECTED_CURVES_PER_TRACK:
            print(f"  X no expected curve count configured; skipping")
            results.append((name, "fail", "no expected count"))
            continue
        try:
            status, msg = build_one(
                name, path,
                EXPECTED_CURVES_PER_TRACK[name],
                args.max_refs,
                args.force,
            )
        except Exception as exc:  # noqa: BLE001
            status, msg = "fail", f"{type(exc).__name__}: {exc}"

        glyph = {"ok": "OK ", "skip": "-- ", "fail": "ERR"}[status]
        print(f"  {glyph} {msg}")
        results.append((name, status, msg))

    # Summary
    print()
    print("=" * 70)
    ok = sum(1 for _, s, _ in results if s == "ok")
    skip = sum(1 for _, s, _ in results if s == "skip")
    fail = sum(1 for _, s, _ in results if s == "fail")
    print(f"Built: {ok}   Skipped: {skip}   Failed: {fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())