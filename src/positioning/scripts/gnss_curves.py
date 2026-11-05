#!/usr/bin/env python3
"""The GNSS trajectories ('curves') a recording offers, loaded for fusion.

Curves, if their CSV exists in out/<recording>/:
  bestnav      receiver solution (csv/location_heading_xyz*.csv), has Doppler velocity
  observation  rover-only single solution from the RINEX (ppk/observation_single.csv)
  fixed_ppk    RTKLIB fixed kinematic PPK   (needs a base station)
  float_ppk    RTKLIB float kinematic PPK   (needs a base station)
  dgps         RTKLIB DGPS fallback         (needs a base station)

RTKLIB curves (everything except bestnav) are in GPS time; 18 s are subtracted to get UTC like the receiver
curve has, and isolated position jumps are removed. A curve without Doppler velocity gets its speed and heading from a least-squares line through the positions
of +-1 s, because the neighbour difference load_gnss() gives is far too noisy at 20 Hz.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from imu_kalman import GNSS_SOURCES, GnssSample, load_gnss, source_csv
from session_paths import resolve_session_dir

CURVE_ORDER = ("bestnav", "fixed_ppk", "float_ppk", "dgps", "observation")
DEFAULT_SPACING_S = {"observation": 0.25}  # 20 Hz single solutions are thinned; the filter gains nothing from more
SPEED_WINDOW_S = 1.0
DERIVED_SPEED_SIGMA_MPS = 0.5  # velocity sigma for curves whose velocity was derived from positions
MIN_VALID_YEAR = 2020
RTKLIB_SOURCES = ("fixed_ppk", "float_ppk", "dgps", "observation")
GPS_UTC_LEAP_S = 18  # RTKLIB .pos files are in GPS time; the CSVs written from them carry that label as if it were UTC


def available_curves(session_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for source in CURVE_ORDER:
        try:
            path = source_csv(session_dir, source)
        except SystemExit:
            continue
        if path.is_file():
            found[source] = path
    return found


def smooth_speed_heading(points: list[GnssSample], window_s: float = SPEED_WINDOW_S) -> None:
    """Replace speed_mps/heading_deg by the slope of a line fitted to the positions within +-window_s."""
    t = np.array([(p.time - points[0].time).total_seconds() for p in points])
    east = np.array([p.east for p in points])
    north = np.array([p.north for p in points])
    height = np.array([p.height for p in points])
    lo = np.searchsorted(t, t - window_s, side="left")
    hi = np.searchsorted(t, t + window_s, side="right")
    previous_heading = points[0].heading_deg
    for i, p in enumerate(points):
        sl = slice(lo[i], hi[i])
        tt = t[sl] - t[sl].mean()
        denom = float(tt @ tt)
        if len(tt) < 3 or denom < 1e-9:
            p.speed_mps = 0.0
            p.heading_deg = previous_heading
            p.vu_mps = 0.0
            continue
        p.vu_mps = float(tt @ (height[sl] - height[sl].mean())) / denom
        ve = float(tt @ (east[sl] - east[sl].mean())) / denom
        vn = float(tt @ (north[sl] - north[sl].mean())) / denom
        p.speed_mps = math.hypot(ve, vn)
        if p.speed_mps > 0.5:
            previous_heading = math.degrees(math.atan2(ve, vn)) % 360.0
        p.heading_deg = previous_heading


def despike(points: list[GnssSample], window_s: float = 1.0, limit_m: float = 10.0) -> list[GnssSample]:
    """Drop points more than `limit_m` from the median position of the points within +-window_s.

    A rover-only RTKLIB solution has isolated jumps of tens to hundreds of metres; a filter that trusts them
    for even one epoch is pulled off the track. The median of a symmetric window follows a smooth path
    (a straight line or an arc) to well within the limit, so only the jumps are removed."""
    t = np.array([(p.time - points[0].time).total_seconds() for p in points])
    east = np.array([p.east for p in points])
    north = np.array([p.north for p in points])
    lo = np.searchsorted(t, t - window_s, side="left")
    hi = np.searchsorted(t, t + window_s, side="right")
    keep = []
    for i, p in enumerate(points):
        sl = slice(lo[i], hi[i])
        if math.hypot(east[i] - np.median(east[sl]), north[i] - np.median(north[sl])) <= limit_m:
            keep.append(p)
    return keep if len(keep) >= 2 else points


def thin(points: list[GnssSample], min_spacing_s: float) -> list[GnssSample]:
    if min_spacing_s <= 0:
        return points
    out = [points[0]]
    for p in points[1:]:
        if (p.time - out[-1].time).total_seconds() >= min_spacing_s - 1e-3:
            out.append(p)
    return out


def has_doppler(points: list[GnssSample]) -> bool:
    """True for a real receiver Doppler velocity (not one derived from the positions)."""
    return sum(p.ve_mps is not None and not getattr(p, "vel_derived", False) for p in points) >= 0.5 * len(points)


def derived_velocity(points: list[GnssSample]) -> bool:
    return bool(points) and bool(getattr(points[0], "vel_derived", False))


def add_derived_velocity(points: list[GnssSample]) -> None:
    """Give a curve without Doppler a velocity from its smoothed speed/heading, so the filter gets a velocity
    measurement (with a larger sigma, see DERIVED_SPEED_SIGMA_MPS) and not only positions."""
    for p in points:
        heading = math.radians(p.heading_deg)
        p.ve_mps = p.speed_mps * math.sin(heading)
        p.vn_mps = p.speed_mps * math.cos(heading)
        p.vel_derived = True  # type: ignore[attr-defined]


def load_curve(session_dir: Path, source: str, min_spacing_s: float | None = None) -> list[GnssSample]:
    points = load_gnss(source_csv(session_dir, source))
    # an epoch without a position solution (type NONE) only repeats an old position
    points = [p for p in points if p.time.year >= MIN_VALID_YEAR and (p.position_type or "").upper() != "NONE"]
    if len(points) < 2:
        raise SystemExit(f"{source}: fewer than two points with a valid time")
    if source in RTKLIB_SOURCES:
        for p in points:
            p.time -= timedelta(seconds=GPS_UTC_LEAP_S)
        points = despike(points)
    if not has_doppler(points):
        smooth_speed_heading(points)
        add_derived_velocity(points)
    spacing = DEFAULT_SPACING_S.get(source, 0.0) if min_spacing_s is None else min_spacing_s
    return thin(points, spacing)


def speed_series(points: list[GnssSample]) -> np.ndarray:
    if has_doppler(points):
        return np.array([math.hypot(p.ve_mps or 0.0, p.vn_mps or 0.0) for p in points])
    return np.array([p.speed_mps for p in points])


def is_stationary(points: list[GnssSample], limit_mps: float = 1.0) -> bool:
    """True when the GNSS speed (a 95th percentile, to ignore single glitches) stays below `limit_mps`."""
    return float(np.percentile(speed_series(points), 95)) < limit_mps


def describe_curve(source: str, points: list[GnssSample]) -> dict[str, object]:
    t = np.array([(p.time - points[0].time).total_seconds() for p in points])
    speed = speed_series(points)
    east = np.array([p.east for p in points])
    north = np.array([p.north for p in points])
    types: dict[str, int] = {}
    for p in points:
        key = p.position_type or "?"
        types[key] = types.get(key, 0) + 1
    return {
        "curve": source,
        "points": len(points),
        "start": points[0].time.isoformat(),
        "end": points[-1].time.isoformat(),
        "duration_s": float(t[-1]),
        "rate_hz": float((len(t) - 1) / max(t[-1], 1e-9)),
        "doppler": has_doppler(points),
        "velocity_derived": derived_velocity(points),
        "position_types": types,
        "speed_median_mps": float(np.median(speed)),
        "speed_p95_mps": float(np.percentile(speed, 95)),
        "speed_max_mps": float(speed.max()),
        "stationary": is_stationary(points),
        "extent_east_m": float(east.max() - east.min()),
        "extent_north_m": float(north.max() - north.min()),
        "rms_about_mean_m": float(np.sqrt(np.mean((east - east.mean()) ** 2 + (north - north.mean()) ** 2))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List and summarise the GNSS curves of a recording.")
    parser.add_argument("recording")
    parser.add_argument("--json", type=Path, help="Write the summary here")
    args = parser.parse_args()
    session_dir = resolve_session_dir(args.recording)
    paths = available_curves(session_dir)
    missing = [c for c in CURVE_ORDER if c not in paths]
    print(f"{session_dir.name}: curves {', '.join(paths) or 'none'}" + (f" (not available: {', '.join(missing)})" if missing else ""))
    summary = []
    for source in paths:
        info = describe_curve(source, load_curve(session_dir, source))
        summary.append(info)
        print(
            f"  {source:12} {info['points']:6d} pts {info['rate_hz']:5.1f} Hz  {info['duration_s']:6.0f} s  "
            f"Doppler {'yes' if info['doppler'] else 'no '}  speed p95 {info['speed_p95_mps']:5.2f} m/s  "
            f"{'STATIONARY' if info['stationary'] else 'moving'}  extent {info['extent_east_m']:.0f} x {info['extent_north_m']:.0f} m  "
            f"types {info['position_types']}"
        )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
