from __future__ import annotations

import csv
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "converting" / "to_csv"))

from gnss_to_csv import bearing_from_ecef, convert_pos_to_csv, llh_to_ecef

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_B = WGS84_A * (1 - WGS84_F)
WGS84_E2 = 1 - (WGS84_B * WGS84_B) / (WGS84_A * WGS84_A)
WGS84_EP2 = (WGS84_A * WGS84_A - WGS84_B * WGS84_B) / (WGS84_B * WGS84_B)
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)


@dataclass
class TrackPoint:
    label: str
    time: Optional[datetime]
    lat: float
    lon: float
    height: Optional[float]
    x: Optional[float]
    y: Optional[float]
    z: Optional[float]
    heading: Optional[float]
    speed_mps: Optional[float]
    raw: dict[str, str]


@dataclass
class Match:
    regular: TrackPoint
    ppk: TrackPoint
    time_delta_s: float
    east_m: float
    north_m: float
    up_m: float
    horizontal_m: float
    distance_3d_m: float


def safe_float(value: object) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def find_first_key(fieldnames: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    lookup = {name.lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def parse_time(value: object) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    p = math.hypot(x, y)
    if p == 0:
        lon = 0.0
        lat = 90.0 if z >= 0 else -90.0
        h = abs(z) - WGS84_B
        return lat, lon, h

    lon = math.atan2(y, x)
    theta = math.atan2(z * WGS84_A, p * WGS84_B)
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    lat = math.atan2(
        z + WGS84_EP2 * WGS84_B * sin_theta**3,
        p - WGS84_E2 * WGS84_A * cos_theta**3,
    )

    for _ in range(2):
        sin_lat = math.sin(lat)
        n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat * sin_lat)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - WGS84_E2 * n / (n + h)))

    sin_lat = math.sin(lat)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat * sin_lat)
    h = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), h


def heading_from_velocity(row: dict[str, str]) -> Optional[float]:
    vx = safe_float(row.get("vx_mps"))
    vy = safe_float(row.get("vy_mps"))
    if vx is None or vy is None or (vx == 0 and vy == 0):
        return None
    heading = math.degrees(math.atan2(vy, vx))
    return (heading + 360.0) % 360.0


def speed_from_velocity(row: dict[str, str]) -> Optional[float]:
    vx = safe_float(row.get("vx_mps"))
    vy = safe_float(row.get("vy_mps"))
    vz = safe_float(row.get("vz_mps"))
    if vx is None or vy is None or vz is None:
        return None
    return math.sqrt(vx * vx + vy * vy + vz * vz)


def point_xyz(point: TrackPoint) -> tuple[float, float, float]:
    if point.x is not None and point.y is not None and point.z is not None:
        return point.x, point.y, point.z
    return llh_to_ecef(point.lat, point.lon, point.height or 0.0)


def fill_missing_motion_headings(points: list[TrackPoint]) -> None:
    for index, point in enumerate(points):
        if point.heading is not None:
            continue

        point_xyz_value = point_xyz(point)
        heading = None
        if index > 0:
            heading = bearing_from_ecef(point_xyz(points[index - 1]), point_xyz_value)
        if heading is None and index + 1 < len(points):
            heading = bearing_from_ecef(point_xyz_value, point_xyz(points[index + 1]))
        point.heading = heading


def load_track(
    path: Path,
    label: str,
    time_candidates: Iterable[str],
    heading_candidates: Iterable[str],
) -> list[TrackPoint]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit(f"CSV has no header: {path}")

        fields = reader.fieldnames
        time_key = find_first_key(fields, time_candidates)
        lat_key = find_first_key(fields, ["lat", "latitude", "lat_deg", "latitude_deg"])
        lon_key = find_first_key(fields, ["lon", "lng", "longitude", "lon_deg", "longitude_deg"])
        height_key = find_first_key(fields, ["height", "height_m", "alt", "alt_m", "z_ellipsoid_m"])
        x_key = find_first_key(fields, ["x_m", "x", "ecef_x", "ecef_x_m"])
        y_key = find_first_key(fields, ["y_m", "y", "ecef_y", "ecef_y_m"])
        z_key = find_first_key(fields, ["z_m", "z", "ecef_z", "ecef_z_m"])
        heading_key = find_first_key(fields, heading_candidates)

        points: list[TrackPoint] = []
        for row in reader:
            lat = safe_float(row.get(lat_key)) if lat_key else None
            lon = safe_float(row.get(lon_key)) if lon_key else None
            height = safe_float(row.get(height_key)) if height_key else None
            x = safe_float(row.get(x_key)) if x_key else None
            y = safe_float(row.get(y_key)) if y_key else None
            z = safe_float(row.get(z_key)) if z_key else None

            if lat is None or lon is None:
                if x is None or y is None or z is None:
                    continue
                lat, lon, ecef_height = ecef_to_geodetic(x, y, z)
                if height is None:
                    height = ecef_height

            if lat == 0.0 and lon == 0.0:
                continue
            if x == 0.0 and y == 0.0 and z == 0.0:
                continue

            heading = safe_float(row.get(heading_key)) if heading_key else None
            if heading is None and label == "Receiver":
                heading = heading_from_velocity(row)
            points.append(
                TrackPoint(
                    label=label,
                    time=parse_time(row.get(time_key)) if time_key else None,
                    lat=lat,
                    lon=lon,
                    height=height,
                    x=x,
                    y=y,
                    z=z,
                    heading=heading,
                    speed_mps=speed_from_velocity(row),
                    raw=row,
                )
            )

    if not points:
        raise SystemExit(f"No usable coordinates found in {path}")
    points = sorted(points, key=lambda point: point.time or datetime.min.replace(tzinfo=timezone.utc))
    fill_missing_motion_headings(points)
    return points


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def resolve_rnx2rtkp(explicit: Optional[Path]) -> Path:
    load_env_file(ROOT / ".env")
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    env_value = os.environ.get("RTKLIB_RNX2RTKP_EXE")
    if env_value:
        candidates.append(Path(os.path.expandvars(env_value)))
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else ROOT / candidate
        if path.is_file():
            return path
    raise SystemExit(
        "Could not find rnx2rtkp.exe. Pass --rnx2rtkp or set RTKLIB_RNX2RTKP_EXE in .env."
    )


def is_legacy_obs(path: Path) -> bool:
    suffix = path.suffix.lower()
    return len(suffix) == 4 and suffix[1:3].isdigit() and suffix[3] == "o"


def is_legacy_nav(path: Path) -> bool:
    suffix = path.suffix.lower()
    return len(suffix) == 4 and suffix[1:3].isdigit() and suffix[3] in {"c", "g", "l", "n", "p"}


def find_rover_obs(rinex_dir: Path) -> Path:
    candidates = [
        path for path in rinex_dir.iterdir()
        if path.is_file() and (path.suffix.lower() in {".obs", ".o"} or is_legacy_obs(path))
    ]
    if not candidates:
        raise SystemExit(f"No rover observation RINEX found in {rinex_dir}")
    return sorted(candidates, key=lambda path: (0 if is_legacy_obs(path) else 1, path.name.lower()))[0]


def find_rover_nav_files(rinex_dir: Path) -> list[Path]:
    suffixes = {".nav", ".gnav", ".hnav", ".qnav", ".lnav", ".sp3", ".clk"}
    navs = [
        path for path in rinex_dir.iterdir()
        if path.is_file() and (path.suffix.lower() in suffixes or is_legacy_nav(path))
    ]
    return sorted(navs, key=lambda path: path.name.lower())


def ensure_observation_single_solution(
    session_dir: Path,
    rnx2rtkp: Path,
    single_pos: Path,
    single_csv: Path,
    force: bool,
) -> None:
    if single_csv.is_file() and not force:
        return

    rinex_dir = session_dir / "rinex"
    rover_obs = find_rover_obs(rinex_dir)
    nav_files = find_rover_nav_files(rinex_dir)
    if not nav_files:
        raise SystemExit(f"No rover navigation RINEX files found in {rinex_dir}")

    single_pos.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(rnx2rtkp),
        "-p", "0",
        "-f", "1",
        "-m", "5",
        "-sys", "G,R,E,C",
        "-o", str(single_pos),
        str(rover_obs),
        *(str(path) for path in nav_files),
    ]
    print("Running rover-only observation solution:")
    print(subprocess.list2cmdline(command) if os.name == "nt" else " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)
    try:
        convert_pos_to_csv(single_pos, single_csv)
    except ValueError:
        convert_rtklib_pos_any_time_to_csv(single_pos, single_csv)


def convert_rtklib_pos_any_time_to_csv(pos_path: Path, csv_path: Path) -> None:
    rows: list[dict[str, str]] = []
    last_xyz: Optional[tuple[float, float, float]] = None
    mode: Optional[str] = None

    for raw_line in pos_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("%"):
            lower = line.lower()
            if "latitude" in lower or "lat/lon/height" in lower:
                mode = "llh"
            elif "x-ecef" in lower or "x/y/z" in lower:
                mode = "xyz"
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        coord_start = 2
        try:
            if "/" in parts[0] and ":" in parts[1]:
                dt = datetime.strptime(f"{parts[0]} {parts[1]}", "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
            else:
                gps_week = int(parts[0])
                tow_s = float(parts[1])
                dt = GPS_EPOCH + timedelta(weeks=gps_week, seconds=tow_s)
        except ValueError:
            try:
                dt = datetime.fromisoformat(f"{parts[0]}T{parts[1]}").replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        try:
            c1 = float(parts[coord_start])
            c2 = float(parts[coord_start + 1])
            c3 = float(parts[coord_start + 2])
        except ValueError:
            continue

        local_mode = mode
        if local_mode is None:
            local_mode = "llh" if abs(c1) <= 90.0 and abs(c2) <= 180.0 else "xyz"
        xyz = llh_to_ecef(c1, c2, c3) if local_mode == "llh" else (c1, c2, c3)
        direction = bearing_from_ecef(last_xyz, xyz) if last_xyz is not None else None
        rows.append({
            "time": dt.isoformat(),
            "x": f"{xyz[0]:.4f}",
            "y": f"{xyz[1]:.4f}",
            "z": f"{xyz[2]:.4f}",
            "direction": "" if direction is None else f"{direction:.3f}",
        })
        last_xyz = xyz

    if not rows:
        raise ValueError(f"No solution rows could be parsed from {pos_path}")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["time", "x", "y", "z", "direction"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {csv_path}")


def load_ppk_quality(solution_pos: Path) -> dict[str, dict[str, str]]:
    if not solution_pos.is_file():
        return {}
    qualities: dict[str, dict[str, str]] = {}
    for raw in solution_pos.read_text(encoding="ascii", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("%"):
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        try:
            dt = datetime.fromisoformat(f"{parts[0]}T{parts[1]}").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        key = dt.isoformat(timespec="milliseconds")
        qualities[key] = {"Q": parts[5], "ns": parts[6], "ratio": parts[-1]}
    return qualities


def attach_ppk_quality(ppk_points: list[TrackPoint], qualities: dict[str, dict[str, str]]) -> None:
    if not qualities:
        return
    for point in ppk_points:
        if point.time is None:
            continue
        key = point.time.isoformat(timespec="milliseconds")
        if key in qualities:
            point.raw.update(qualities[key])


def ecef_delta_to_enu(reference: TrackPoint, dx: float, dy: float, dz: float) -> tuple[float, float, float]:
    if reference.x is None or reference.y is None or reference.z is None:
        return dx, dy, dz
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


def nearest_point(points: list[TrackPoint], target: datetime, start_index: int) -> tuple[TrackPoint, int, float]:
    best_index = min(start_index, len(points) - 1)
    best_delta = abs(((points[best_index].time or target) - target).total_seconds())

    i = best_index
    while i + 1 < len(points):
        next_time = points[i + 1].time
        if next_time is None:
            break
        delta = abs((next_time - target).total_seconds())
        if delta > best_delta:
            break
        i += 1
        best_index = i
        best_delta = delta
    return points[best_index], best_index, best_delta


def match_tracks(
    regular: list[TrackPoint],
    ppk: list[TrackPoint],
    ppk_time_offset_s: float,
    max_time_delta_s: float,
) -> list[Match]:
    regular_with_time = [point for point in regular if point.time is not None and point.x is not None and point.y is not None and point.z is not None]
    ppk_with_time = [point for point in ppk if point.time is not None and point.x is not None and point.y is not None and point.z is not None]
    matches: list[Match] = []
    if not regular_with_time or not ppk_with_time:
        return matches

    offset = timedelta(seconds=ppk_time_offset_s)
    regular_index = 0
    for ppk_point in ppk_with_time:
        match_time = ppk_point.time + offset
        regular_point, regular_index, time_delta = nearest_point(regular_with_time, match_time, regular_index)
        if time_delta > max_time_delta_s:
            continue

        dx = ppk_point.x - regular_point.x
        dy = ppk_point.y - regular_point.y
        dz = ppk_point.z - regular_point.z
        east, north, up = ecef_delta_to_enu(regular_point, dx, dy, dz)
        horizontal = math.hypot(east, north)
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        matches.append(Match(regular_point, ppk_point, time_delta, east, north, up, horizontal, distance))
    return matches


def pct(values: list[float], fraction: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]
