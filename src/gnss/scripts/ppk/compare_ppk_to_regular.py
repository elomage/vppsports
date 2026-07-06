#!/usr/bin/env python3
"""Compare receiver-reported positions against PPK positions for one recording."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from session_paths import output_subdir, resolve_session_dir


@dataclass
class Point:
    time: datetime
    x: float
    y: float
    z: float
    extra: dict[str, str]


def parse_time(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def read_points(path: Path, time_column: str, x_column: str, y_column: str, z_column: str) -> list[Point]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit(f"CSV has no header: {path}")
        required = {time_column, x_column, y_column, z_column}
        missing = required - set(reader.fieldnames)
        if missing:
            raise SystemExit(f"CSV is missing columns {sorted(missing)}: {path}")

        rows: list[Point] = []
        for row in reader:
            try:
                rows.append(Point(
                    time=parse_time(row[time_column]),
                    x=float(row[x_column]),
                    y=float(row[y_column]),
                    z=float(row[z_column]),
                    extra=row,
                ))
            except (TypeError, ValueError):
                continue
    if not rows:
        raise SystemExit(f"No usable coordinate rows found in {path}")
    return sorted(rows, key=lambda point: point.time)


def nearest_point(points: list[Point], target: datetime, start_index: int) -> tuple[Point, int, float]:
    best_index = min(start_index, len(points) - 1)
    best_delta = abs((points[best_index].time - target).total_seconds())

    i = best_index
    while i + 1 < len(points):
        delta = abs((points[i + 1].time - target).total_seconds())
        if delta > best_delta:
            break
        i += 1
        best_index = i
        best_delta = delta

    return points[best_index], best_index, best_delta


def ecef_delta_to_enu(reference: Point, dx: float, dy: float, dz: float) -> tuple[float, float, float]:
    lon = math.atan2(reference.y, reference.x)
    p = math.hypot(reference.x, reference.y)
    lat = math.atan2(reference.z, p)

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)

    east = -sin_lon * dx + cos_lon * dy
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    up = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz
    return east, north, up


def pct(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def write_outputs(out_csv: Path, report: Path, rows: list[dict[str, str]], distances: list[float], horizontals: list[float]) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "regular_time_utc",
        "ppk_time_utc",
        "time_delta_s",
        "regular_x_m",
        "regular_y_m",
        "regular_z_m",
        "ppk_x_m",
        "ppk_y_m",
        "ppk_z_m",
        "east_m",
        "north_m",
        "up_m",
        "horizontal_m",
        "distance_3d_m",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        f"Matches: {len(rows)}",
        f"Output CSV: {out_csv}",
    ]
    if rows:
        lines.extend([
            "",
            f"3D mean m: {statistics.fmean(distances):.4f}",
            f"3D median m: {statistics.median(distances):.4f}",
            f"3D p95 m: {pct(distances, 0.95):.4f}",
            f"3D max m: {max(distances):.4f}",
            f"Horizontal mean m: {statistics.fmean(horizontals):.4f}",
            f"Horizontal median m: {statistics.median(horizontals):.4f}",
            f"Horizontal p95 m: {pct(horizontals, 0.95):.4f}",
            f"Horizontal max m: {max(horizontals):.4f}",
        ])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare regular receiver positions with PPK positions.")
    parser.add_argument("recording", help="Recording output directory, e.g. 20260421_212949Z_LOG00001")
    parser.add_argument("--regular-csv", type=Path, help="Default: out/<recording>/csv/location_heading_xyz_filtered.csv")
    parser.add_argument("--ppk-csv", type=Path, help="Default: out/<recording>/ppk/solution.csv")
    parser.add_argument("--out-csv", type=Path, help="Default: out/<recording>/ppk/regular_vs_ppk.csv")
    parser.add_argument("--report", type=Path, help="Default: out/<recording>/ppk/regular_vs_ppk_report.txt")
    parser.add_argument("--max-time-delta-s", type=float, default=0.15, help="Maximum nearest timestamp gap after offset.")
    parser.add_argument(
        "--ppk-time-offset-s",
        type=float,
        default=-18.0,
        help="Offset applied to PPK timestamps before matching. RTKLIB is GPST, regular CSV is UTC, so default is -18.",
    )
    args = parser.parse_args()

    session_dir = resolve_session_dir(args.recording)
    ppk_dir = output_subdir(session_dir, "ppk")
    regular_csv = args.regular_csv or session_dir / "csv" / "location_heading_xyz_filtered.csv"
    ppk_csv = args.ppk_csv or ppk_dir / "solution.csv"
    out_csv = args.out_csv or ppk_dir / "regular_vs_ppk.csv"
    report = args.report or ppk_dir / "regular_vs_ppk_report.txt"

    if not regular_csv.is_file():
        raise SystemExit(f"Regular position CSV not found: {regular_csv}")
    if not ppk_csv.is_file():
        raise SystemExit(f"PPK CSV not found: {ppk_csv}\nRun PPK first and make sure solution.csv was created.")

    regular = read_points(regular_csv, "utc", "x_m", "y_m", "z_m")
    ppk = read_points(ppk_csv, "time", "x", "y", "z")

    rows: list[dict[str, str]] = []
    distances: list[float] = []
    horizontals: list[float] = []
    regular_index = 0
    offset = timedelta(seconds=args.ppk_time_offset_s)

    for ppk_point in ppk:
        ppk_match_time = ppk_point.time + offset
        regular_point, regular_index, time_delta = nearest_point(regular, ppk_match_time, regular_index)
        if time_delta > args.max_time_delta_s:
            continue

        dx = ppk_point.x - regular_point.x
        dy = ppk_point.y - regular_point.y
        dz = ppk_point.z - regular_point.z
        east, north, up = ecef_delta_to_enu(regular_point, dx, dy, dz)
        horizontal = math.hypot(east, north)
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        distances.append(distance)
        horizontals.append(horizontal)
        rows.append({
            "regular_time_utc": regular_point.time.isoformat(),
            "ppk_time_utc": ppk_match_time.isoformat(),
            "time_delta_s": f"{time_delta:.3f}",
            "regular_x_m": f"{regular_point.x:.4f}",
            "regular_y_m": f"{regular_point.y:.4f}",
            "regular_z_m": f"{regular_point.z:.4f}",
            "ppk_x_m": f"{ppk_point.x:.4f}",
            "ppk_y_m": f"{ppk_point.y:.4f}",
            "ppk_z_m": f"{ppk_point.z:.4f}",
            "east_m": f"{east:.4f}",
            "north_m": f"{north:.4f}",
            "up_m": f"{up:.4f}",
            "horizontal_m": f"{horizontal:.4f}",
            "distance_3d_m": f"{distance:.4f}",
        })

    if not rows:
        raise SystemExit(
            "No matching timestamps found. Check that PPK has solution rows and adjust "
            "--ppk-time-offset-s or --max-time-delta-s if needed."
        )

    write_outputs(out_csv, report, rows, distances, horizontals)
    print(f"Compared rows: {len(rows)}")
    print(f"3D median difference: {statistics.median(distances):.4f} m")
    print(f"Horizontal median difference: {statistics.median(horizontals):.4f} m")
    print(f"CSV: {out_csv}")
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
