#!/usr/bin/env python3
"""Fuse a selected GNSS trajectory with one IMU recording using a small Kalman filter."""

from __future__ import annotations

import argparse
import csv
import math
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from session_paths import find_receiver_csv, output_subdir, resolve_session_dir
from gnss_track_utils import ecef_to_geodetic, safe_float

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
G0 = 9.80665
IMU_RECORD_STRUCT = struct.Struct("<Iiii")


@dataclass
class ImuSample:
    seconds: float
    ax_mps2: float
    ay_mps2: float
    az_mps2: float
    time: datetime | None = None


@dataclass
class GnssSample:
    time: datetime
    lat: float
    lon: float
    height: float
    east: float
    north: float
    speed_mps: float
    heading_deg: float


def parse_time(value: object) -> datetime | None:
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


def llh_to_ecef(lat_deg: float, lon_deg: float, height_m: float) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + height_m) * cos_lat * math.cos(lon)
    y = (n + height_m) * cos_lat * math.sin(lon)
    z = (n * (1 - WGS84_E2) + height_m) * sin_lat
    return x, y, z


def enu_basis(ref_lat: float, ref_lon: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    lat = math.radians(ref_lat)
    lon = math.radians(ref_lon)
    east = (-math.sin(lon), math.cos(lon), 0.0)
    north = (-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat))
    return east, north


def ecef_to_enu(
    x: float,
    y: float,
    z: float,
    ref_xyz: tuple[float, float, float],
    basis: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> tuple[float, float]:
    dx = x - ref_xyz[0]
    dy = y - ref_xyz[1]
    dz = z - ref_xyz[2]
    east_axis, north_axis = basis
    return (
        dx * east_axis[0] + dy * east_axis[1] + dz * east_axis[2],
        dx * north_axis[0] + dy * north_axis[1] + dz * north_axis[2],
    )


def enu_to_llh(east: float, north: float, ref_lat: float, ref_lon: float, height: float) -> tuple[float, float, float]:
    lat = ref_lat + math.degrees(north / 6378137.0)
    lon = ref_lon + math.degrees(east / (6378137.0 * max(0.1, math.cos(math.radians(ref_lat)))))
    return lat, lon, height


def find_first_key(fieldnames: Iterable[str], candidates: Iterable[str]) -> str | None:
    lookup = {field.lower(): field for field in fieldnames}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def convert_imu_bin(bin_path: Path, csv_path: Path, sens_ug_per_lsb: float = 19.5) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with bin_path.open("rb") as src, csv_path.open("w", newline="", encoding="utf-8") as dst:
        writer = csv.writer(dst)
        writer.writerow(["seconds", "x_g", "y_g", "z_g"])
        while True:
            chunk = src.read(IMU_RECORD_STRUCT.size)
            if not chunk:
                break
            if len(chunk) != IMU_RECORD_STRUCT.size:
                raise ValueError(f"Trailing {len(chunk)} bytes in {bin_path}")
            ts_us, x, y, z = IMU_RECORD_STRUCT.unpack(chunk)
            writer.writerow([
                f"{ts_us / 1_000_000.0:.6f}",
                f"{x * sens_ug_per_lsb / 1_000_000.0:.6f}",
                f"{y * sens_ug_per_lsb / 1_000_000.0:.6f}",
                f"{z * sens_ug_per_lsb / 1_000_000.0:.6f}",
            ])


def load_imu(path: Path) -> list[ImuSample]:
    csv_path = path
    if path.suffix.lower() == ".bin":
        csv_path = path.with_suffix(".csv")
        convert_imu_bin(path, csv_path)

    samples: list[ImuSample] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit(f"IMU CSV has no header: {csv_path}")
        seconds_key = find_first_key(reader.fieldnames, ["seconds", "time_s", "t", "timestamp_s"])
        x_key = find_first_key(reader.fieldnames, ["ax_mps2", "x_mps2", "x_accel_mps2", "x_g"])
        y_key = find_first_key(reader.fieldnames, ["ay_mps2", "y_mps2", "y_accel_mps2", "y_g"])
        z_key = find_first_key(reader.fieldnames, ["az_mps2", "z_mps2", "z_accel_mps2", "z_g"])
        if not seconds_key or not x_key or not y_key or not z_key:
            raise SystemExit(f"IMU CSV needs seconds,x_g,y_g,z_g or *_mps2 columns: {csv_path}")
        uses_g = x_key.lower().endswith("_g") or y_key.lower().endswith("_g") or z_key.lower().endswith("_g")
        scale = G0 if uses_g else 1.0
        for row in reader:
            seconds = safe_float(row.get(seconds_key))
            ax = safe_float(row.get(x_key))
            ay = safe_float(row.get(y_key))
            az = safe_float(row.get(z_key))
            if seconds is None or ax is None or ay is None or az is None:
                continue
            samples.append(ImuSample(seconds, ax * scale, ay * scale, az * scale))
    if not samples:
        raise SystemExit(f"No usable IMU rows found in {csv_path}")
    return sorted(samples, key=lambda sample: sample.seconds)


def source_csv(session_dir: Path, source: str) -> Path:
    if source == "bestnav":
        return find_receiver_csv(session_dir)
    if source == "fixed_ppk":
        return session_dir / "ppk" / "solution.csv"
    if source == "dgps":
        return session_dir / "ppk" / "solution_dgps.csv"
    raise SystemExit(f"Unsupported source: {source}")


def load_gnss(path: Path) -> list[GnssSample]:
    if not path.is_file():
        raise SystemExit(f"GNSS source CSV not found: {path}")
    raw: list[tuple[datetime, float, float, float, float, float, float]] = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit(f"GNSS CSV has no header: {path}")
        time_key = find_first_key(reader.fieldnames, ["utc", "time", "timestamp", "datetime", "date_time"])
        lat_key = find_first_key(reader.fieldnames, ["lat", "latitude", "lat_deg", "latitude_deg"])
        lon_key = find_first_key(reader.fieldnames, ["lon", "lng", "longitude", "lon_deg", "longitude_deg"])
        height_key = find_first_key(reader.fieldnames, ["height", "height_m", "alt", "alt_m"])
        x_key = find_first_key(reader.fieldnames, ["x_m", "x", "ecef_x", "ecef_x_m"])
        y_key = find_first_key(reader.fieldnames, ["y_m", "y", "ecef_y", "ecef_y_m"])
        z_key = find_first_key(reader.fieldnames, ["z_m", "z", "ecef_z", "ecef_z_m"])
        if not time_key:
            raise SystemExit(f"GNSS CSV needs a time column: {path}")
        for row in reader:
            time = parse_time(row.get(time_key))
            lat = safe_float(row.get(lat_key)) if lat_key else None
            lon = safe_float(row.get(lon_key)) if lon_key else None
            height = safe_float(row.get(height_key)) if height_key else None
            x = safe_float(row.get(x_key)) if x_key else None
            y = safe_float(row.get(y_key)) if y_key else None
            z = safe_float(row.get(z_key)) if z_key else None
            if time is None:
                continue
            if lat is None or lon is None:
                if x is None or y is None or z is None:
                    continue
                lat, lon, ecef_height = ecef_to_geodetic(x, y, z)
                height = height if height is not None else ecef_height
            elif x is None or y is None or z is None:
                x, y, z = llh_to_ecef(lat, lon, height or 0.0)
            if (lat == 0.0 and lon == 0.0) or (x == 0.0 and y == 0.0 and z == 0.0):
                continue
            raw.append((time, lat, lon, height or 0.0, x, y, z))
    if len(raw) < 2:
        raise SystemExit(f"Need at least two usable GNSS rows in {path}")
    raw.sort(key=lambda item: item[0])
    ref_lat, ref_lon, ref_height = raw[0][1], raw[0][2], raw[0][3]
    ref_xyz = llh_to_ecef(ref_lat, ref_lon, ref_height)
    basis = enu_basis(ref_lat, ref_lon)
    enu_rows = [(item[0], item[1], item[2], item[3], *ecef_to_enu(item[4], item[5], item[6], ref_xyz, basis)) for item in raw]
    result: list[GnssSample] = []
    for index, row in enumerate(enu_rows):
        prev = enu_rows[max(0, index - 1)]
        nxt = enu_rows[min(len(enu_rows) - 1, index + 1)]
        dt = max(1e-6, (nxt[0] - prev[0]).total_seconds())
        de = nxt[4] - prev[4]
        dn = nxt[5] - prev[5]
        speed = math.hypot(de, dn) / dt
        heading = math.degrees(math.atan2(de, dn)) % 360.0 if speed > 1e-4 else (result[-1].heading_deg if result else 0.0)
        result.append(GnssSample(row[0], row[1], row[2], row[3], row[4], row[5], speed, heading))
    return result


def interp_gnss(points: list[GnssSample], time: datetime) -> GnssSample | None:
    if time < points[0].time or time > points[-1].time:
        return None
    lo = 0
    hi = len(points) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if points[mid].time <= time:
            lo = mid
        else:
            hi = mid
    a = points[lo]
    b = points[hi]
    span = max(1e-6, (b.time - a.time).total_seconds())
    frac = (time - a.time).total_seconds() / span
    return GnssSample(
        time,
        a.lat + (b.lat - a.lat) * frac,
        a.lon + (b.lon - a.lon) * frac,
        a.height + (b.height - a.height) * frac,
        a.east + (b.east - a.east) * frac,
        a.north + (b.north - a.north) * frac,
        a.speed_mps + (b.speed_mps - a.speed_mps) * frac,
        a.heading_deg + ((((b.heading_deg - a.heading_deg) + 180.0) % 360.0) - 180.0) * frac,
    )


def acceleration_norm(samples: list[ImuSample]) -> list[float]:
    norms = [math.sqrt(s.ax_mps2 * s.ax_mps2 + s.ay_mps2 * s.ay_mps2 + s.az_mps2 * s.az_mps2) for s in samples]
    ordered = sorted(norms)
    gravity = ordered[len(ordered) // 2]
    return [abs(value - gravity) for value in norms]


def gnss_accel_series(points: list[GnssSample], sample_seconds: list[float], start_time: datetime) -> list[float]:
    values: list[float] = []
    previous_speed: float | None = None
    previous_time: datetime | None = None
    for seconds in sample_seconds:
        time = start_time + timedelta(seconds=seconds)
        point = interp_gnss(points, time)
        if point is None:
            values.append(0.0)
            continue
        if previous_speed is None or previous_time is None:
            values.append(0.0)
        else:
            dt = max(1e-6, (time - previous_time).total_seconds())
            values.append(abs((point.speed_mps - previous_speed) / dt))
        previous_speed = point.speed_mps
        previous_time = time
    return values


def correlation(a: list[float], b: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(a, b) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 20:
        return -1.0
    ma = sum(x for x, _ in pairs) / len(pairs)
    mb = sum(y for _, y in pairs) / len(pairs)
    va = sum((x - ma) ** 2 for x, _ in pairs)
    vb = sum((y - mb) ** 2 for _, y in pairs)
    if va <= 0 or vb <= 0:
        return -1.0
    return sum((x - ma) * (y - mb) for x, y in pairs) / math.sqrt(va * vb)


def estimate_offset(points: list[GnssSample], samples: list[ImuSample], step_s: float, search_padding_s: float) -> tuple[float, float]:
    imu_duration = samples[-1].seconds - samples[0].seconds
    gnss_duration = (points[-1].time - points[0].time).total_seconds()
    start = -imu_duration - search_padding_s
    end = gnss_duration + search_padding_s
    imu_signal = acceleration_norm(samples)
    stride = max(1, len(samples) // 3000)
    sample_seconds = [samples[i].seconds for i in range(0, len(samples), stride)]
    imu_sparse = [imu_signal[i] for i in range(0, len(imu_signal), stride)]
    best_offset = 0.0
    best_score = -1.0
    offset = start
    while offset <= end:
        series_start = points[0].time + timedelta(seconds=offset)
        gnss_sparse = gnss_accel_series(points, sample_seconds, series_start)
        score = correlation(imu_sparse, gnss_sparse)
        if score > best_score:
            best_score = score
            best_offset = offset
        offset += step_s
    return best_offset, best_score


def assign_times(
    points: list[GnssSample],
    samples: list[ImuSample],
    imu_start_utc: str | None,
    time_offset_s: float | None,
    auto_align: bool,
    align_step_s: float,
    align_padding_s: float,
) -> tuple[float, float | None]:
    if imu_start_utc:
        start = parse_time(imu_start_utc)
        if start is None:
            raise SystemExit(f"Could not parse --imu-start-utc: {imu_start_utc}")
        offset = (start - points[0].time).total_seconds()
        score = None
    elif time_offset_s is not None:
        offset = time_offset_s
        score = None
    elif auto_align:
        offset, score = estimate_offset(points, samples, align_step_s, align_padding_s)
    else:
        offset = 0.0
        score = None
    for sample in samples:
        sample.time = points[0].time + timedelta(seconds=offset + sample.seconds)
    return offset, score


def signed_forward_accel(sample: ImuSample, point: GnssSample | None, previous_point: GnssSample | None) -> float:
    raw = math.sqrt(sample.ax_mps2 * sample.ax_mps2 + sample.ay_mps2 * sample.ay_mps2 + sample.az_mps2 * sample.az_mps2)
    magnitude = max(-6.0, min(6.0, raw - G0))
    if point is None or previous_point is None:
        return magnitude
    dt = max(1e-6, (point.time - previous_point.time).total_seconds())
    sign = 1.0 if (point.speed_mps - previous_point.speed_mps) / dt >= 0.0 else -1.0
    return abs(magnitude) * sign


def kalman_update(
    state: list[float],
    covariance: list[list[float]],
    meas_e: float,
    meas_n: float,
    measurement_var: float,
) -> tuple[list[float], list[list[float]]]:
    h = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
    residual = [meas_e - state[0], meas_n - state[1]]
    s00 = covariance[0][0] + measurement_var
    s01 = covariance[0][1]
    s10 = covariance[1][0]
    s11 = covariance[1][1] + measurement_var
    det = s00 * s11 - s01 * s10
    if abs(det) < 1e-12:
        return state, covariance
    inv_s = [[s11 / det, -s01 / det], [-s10 / det, s00 / det]]
    k = [
        [covariance[i][0] * inv_s[0][0] + covariance[i][1] * inv_s[1][0],
         covariance[i][0] * inv_s[0][1] + covariance[i][1] * inv_s[1][1]]
        for i in range(4)
    ]
    next_state = [state[i] + k[i][0] * residual[0] + k[i][1] * residual[1] for i in range(4)]
    i_kh = [[(1.0 if r == c else 0.0) - k[r][c] if c < 2 else (1.0 if r == c else 0.0) for c in range(4)] for r in range(4)]
    next_cov = [[sum(i_kh[r][m] * covariance[m][c] for m in range(4)) for c in range(4)] for r in range(4)]
    return next_state, next_cov


def run_filter(
    points: list[GnssSample],
    samples: list[ImuSample],
    source: str,
    position_sigma_m: float,
    accel_noise: float,
    gnss_update_period_s: float,
    imu_start_delay_s: float = 0.0,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    start_second = samples[0].seconds + max(0.0, imu_start_delay_s)
    overlap = [
        sample for sample in samples
        if sample.time and sample.seconds >= start_second and points[0].time <= sample.time <= points[-1].time
    ]
    if len(overlap) < 2:
        raise SystemExit("No IMU/GNSS overlap after alignment. Try --auto-align or --time-offset-s.")

    first_gnss = interp_gnss(points, overlap[0].time)
    if first_gnss is None:
        raise SystemExit("Could not initialize from GNSS at first overlap sample.")
    state = [first_gnss.east, first_gnss.north, 0.0, 0.0]
    covariance = [[0.0 for _ in range(4)] for _ in range(4)]
    for i in range(4):
        covariance[i][i] = 10.0

    ref_lat, ref_lon, ref_height = points[0].lat, points[0].lon, points[0].height
    rows: list[dict[str, object]] = []
    dead_rows: list[dict[str, object]] = []
    dead_e, dead_n = first_gnss.east, first_gnss.north
    dead_ve, dead_vn = 0.0, 0.0
    previous_time = overlap[0].time
    previous_gnss = first_gnss
    last_update_time = datetime.min.replace(tzinfo=timezone.utc)

    for sample in overlap:
        assert sample.time is not None
        dt = max(1e-4, min(1.0, (sample.time - previous_time).total_seconds()))
        gnss = interp_gnss(points, sample.time)
        accel = signed_forward_accel(sample, gnss, previous_gnss)
        heading = math.radians((gnss.heading_deg if gnss else previous_gnss.heading_deg) if previous_gnss else 0.0)
        ae = accel * math.sin(heading)
        an = accel * math.cos(heading)

        state[0] += state[2] * dt + 0.5 * ae * dt * dt
        state[1] += state[3] * dt + 0.5 * an * dt * dt
        state[2] += ae * dt
        state[3] += an * dt

        f = [[1.0, 0.0, dt, 0.0], [0.0, 1.0, 0.0, dt], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        covariance = [[sum(f[r][m] * covariance[m][n] for m in range(4)) for n in range(4)] for r in range(4)]
        covariance = [[sum(covariance[r][m] * f[c][m] for m in range(4)) for c in range(4)] for r in range(4)]
        q_pos = 0.25 * accel_noise * dt ** 4
        q_vel = accel_noise * dt * dt
        covariance[0][0] += q_pos
        covariance[1][1] += q_pos
        covariance[2][2] += q_vel
        covariance[3][3] += q_vel

        dead_e += dead_ve * dt + 0.5 * ae * dt * dt
        dead_n += dead_vn * dt + 0.5 * an * dt * dt
        dead_ve += ae * dt
        dead_vn += an * dt

        gnss_used = False
        if gnss and (sample.time - last_update_time).total_seconds() >= gnss_update_period_s:
            state, covariance = kalman_update(state, covariance, gnss.east, gnss.north, position_sigma_m * position_sigma_m)
            last_update_time = sample.time
            gnss_used = True
            previous_gnss = gnss

        lat, lon, height = enu_to_llh(state[0], state[1], ref_lat, ref_lon, ref_height)
        dead_lat, dead_lon, dead_height = enu_to_llh(dead_e, dead_n, ref_lat, ref_lon, ref_height)
        rows.append({
            "time": sample.time.isoformat(),
            "source": source,
            "lat": f"{lat:.10f}",
            "lon": f"{lon:.10f}",
            "height_m": f"{height:.3f}",
            "east_m": f"{state[0]:.3f}",
            "north_m": f"{state[1]:.3f}",
            "ve_mps": f"{state[2]:.4f}",
            "vn_mps": f"{state[3]:.4f}",
            "gnss_used": "1" if gnss_used else "0",
        })
        dead_rows.append({
            "time": sample.time.isoformat(),
            "lat": f"{dead_lat:.10f}",
            "lon": f"{dead_lon:.10f}",
            "height_m": f"{dead_height:.3f}",
            "east_m": f"{dead_e:.3f}",
            "north_m": f"{dead_n:.3f}",
        })
        previous_time = sample.time
    return rows, dead_rows


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise SystemExit(f"No rows to write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def copy_or_convert_imu(input_path: Path, imu_dir: Path) -> Path:
    imu_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = imu_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if input_path.suffix.lower() == ".bin":
        raw_copy = raw_dir / input_path.name
        if input_path.resolve() != raw_copy.resolve():
            shutil.copy2(input_path, raw_copy)
        csv_path = imu_dir / f"{input_path.stem}.csv"
        convert_imu_bin(raw_copy, csv_path)
        return csv_path
    csv_copy = imu_dir / input_path.name
    if input_path.resolve() != csv_copy.resolve():
        shutil.copy2(input_path, csv_copy)
    return csv_copy


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate a GNSS+IMU Kalman trajectory.")
    parser.add_argument("recording", help="GNSS recording output directory or name inside out/")
    parser.add_argument("--imu", required=True, type=Path, help="IMU .BIN or CSV file")
    parser.add_argument("--source", choices=["bestnav", "fixed_ppk", "dgps"], default="fixed_ppk")
    parser.add_argument("--time-offset-s", type=float, help="IMU seconds are placed at GNSS start + offset + imu seconds")
    parser.add_argument("--imu-start-utc", help="Absolute UTC time for IMU second zero, e.g. 2026-05-10T10:56:07Z")
    parser.add_argument("--auto-align", action="store_true", help="Estimate IMU/GNSS time offset from motion correlation")
    parser.add_argument("--align-step-s", type=float, default=0.5)
    parser.add_argument("--align-padding-s", type=float, default=30.0)
    parser.add_argument("--position-sigma-m", type=float, default=0.6)
    parser.add_argument("--accel-noise", type=float, default=2.0)
    parser.add_argument("--gnss-update-period-s", type=float, default=0.05)
    parser.add_argument("--imu-start-delay-s", type=float, default=0.0, help="Skip this many seconds from IMU start before starting the trajectory")
    parser.add_argument("--dead-only", action="store_true", help="Write only the IMU dead-reckoning trajectory, not the fused Kalman CSV")
    parser.add_argument("--output", type=Path, help="Output fused CSV path")
    parser.add_argument("--dead-output", type=Path, help="Output IMU diagnostic trajectory CSV path")
    parser.add_argument("--update-viewer", action="store_true", help="Rebuild viewer/ after writing outputs")
    args = parser.parse_args()

    session_dir = resolve_session_dir(args.recording)
    imu_dir = output_subdir(session_dir, "imu")
    imu_csv = copy_or_convert_imu(args.imu.resolve(), imu_dir)
    gnss = load_gnss(source_csv(session_dir, args.source))
    imu = load_imu(imu_csv)
    offset, score = assign_times(
        gnss,
        imu,
        args.imu_start_utc,
        args.time_offset_s,
        args.auto_align,
        args.align_step_s,
        args.align_padding_s,
    )
    rows, dead_rows = run_filter(
        gnss,
        imu,
        args.source,
        args.position_sigma_m,
        args.accel_noise,
        args.gnss_update_period_s,
        args.imu_start_delay_s,
    )
    output = args.output or imu_dir / f"kalman_{args.source}_{imu_csv.stem}.csv"
    dead_output = args.dead_output or imu_dir / f"imu_dead_reckoning_{args.source}_{imu_csv.stem}.csv"
    if not args.dead_only:
        write_rows(output, rows)
    write_rows(dead_output, dead_rows)
    report_prefix = "imu_dead_reckoning" if args.dead_only else "kalman"
    report = imu_dir / f"{report_prefix}_{args.source}_{imu_csv.stem}_report.txt"
    report.write_text(
        "\n".join([
            f"recording={session_dir}",
            f"imu_csv={imu_csv}",
            f"gnss_source={args.source}",
            f"time_offset_s={offset:.3f}",
            f"imu_start_delay_s={args.imu_start_delay_s:.3f}",
            f"auto_align_score={'' if score is None else f'{score:.4f}'}",
            f"overlap_rows={len(rows)}",
            f"kalman_csv={'' if args.dead_only else output}",
            f"imu_dead_reckoning_csv={dead_output}",
        ]),
        encoding="utf-8",
    )
    if not args.dead_only:
        print(f"Wrote Kalman trajectory: {output}")
    print(f"Wrote IMU diagnostic trajectory: {dead_output}")
    print(f"Time offset: {offset:.3f} s" + (f" (correlation {score:.4f})" if score is not None else ""))
    print(f"IMU start delay: {args.imu_start_delay_s:.3f} s")
    if score is not None and score < 0.20:
        print("Warning: auto alignment confidence is low; compare with --time-offset-s 0 or set --imu-start-utc manually.")
    print(f"Report: {report}")
    if args.update_viewer:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "maps" / "build_recording_viewer.py")], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
