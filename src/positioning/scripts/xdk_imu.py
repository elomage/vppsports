#!/usr/bin/env python3
"""Bosch XDK (accelerometer + gyroscope) log loader and GNSS time alignment.

The XDK SD card logs have no absolute clock: ``t_ms`` is milliseconds since the logger started, so a
log has to be paired with a GNSS recording and shifted in time before the two can be fused. The pairing
and the shift are both found from the yaw rate: the gyroscope rotation about the vertical axis must
match the heading change of the GNSS velocity vector, whatever way up or around the XDK is mounted.

CSV columns: t_ms, ax, ay, az (mg), gx, gy, gz (mdps), mx, my, mz, mag_r, temp_mC, press_Pa, ...
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

G0 = 9.80665
MIN_XDK_DURATION_S = 10.0  # shorter logs (e.g. a start-up stub) are not usable recordings


@dataclass
class XdkData:
    name: str
    t: np.ndarray  # seconds since logger start
    acc: np.ndarray  # specific force, m/s^2, shape (n, 3)
    gyro: np.ndarray  # angular rate, rad/s, shape (n, 3)
    pressure_pa: np.ndarray

    @property
    def duration_s(self) -> float:
        return float(self.t[-1] - self.t[0])


def load_xdk(path: Path) -> XdkData:
    path = Path(path)
    data = np.genfromtxt(path, delimiter=",", skip_header=1, dtype=float)
    if data.ndim != 2 or data.shape[1] < 7 or len(data) < 2:
        raise SystemExit(f"XDK CSV needs t_ms,ax,ay,az,gx,gy,gz columns and at least two rows: {path}")
    data = data[np.all(np.isfinite(data[:, :7]), axis=1)]
    keep = np.r_[True, np.diff(data[:, 0]) > 0]  # a repeated or reset timestamp is not a new sample
    data = data[keep]
    values = data[:, 1:7]
    keep = np.r_[True, np.any(np.diff(values, axis=0) != 0, axis=1)]  # stale rows repeated at logger start-up
    data = data[keep]
    pressure = data[:, 12] if data.shape[1] > 12 else np.zeros(len(data))
    return XdkData(
        name=path.stem,
        t=data[:, 0] / 1000.0,
        acc=data[:, 1:4] * G0 / 1000.0,
        gyro=np.radians(data[:, 4:7] / 1000.0),
        pressure_pa=pressure,
    )


def _moving_mean(values: np.ndarray, width: int) -> np.ndarray:
    width = max(1, int(width))
    if width == 1:
        return values.astype(float, copy=True)
    kernel = np.ones(width) / width
    if values.ndim == 1:
        return np.convolve(values, kernel, "same")
    return np.column_stack([np.convolve(values[:, i], kernel, "same") for i in range(values.shape[1])])


def resample_mean(t: np.ndarray, values: np.ndarray, rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Average irregular samples into fixed bins; returns bin-centre times and means."""
    bins = np.floor((t - t[0]) * rate_hz).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, np.diff(bins) != 0])
    counts = np.diff(np.r_[starts, len(t)])
    t_out = np.add.reduceat(t, starts) / counts
    v_out = np.add.reduceat(values, starts, axis=0) / (counts[:, None] if values.ndim > 1 else counts)
    return t_out, v_out


def up_axis(acc: np.ndarray) -> np.ndarray:
    """Sensor-frame 'up' (specific force points up at rest); the long-run mean of a ride is gravity."""
    mean = acc.mean(axis=0)
    return mean / max(float(np.linalg.norm(mean)), 1e-9)


def gnss_yaw_rate(points: Sequence[object], rate_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(time since first point, clockwise heading rate rad/s, speed) on a fixed grid; rate 0 below 2 m/s."""
    t0 = points[0].time
    gt = np.array([(p.time - t0).total_seconds() for p in points])
    ve = np.array([p.ve_mps if getattr(p, "ve_mps", None) is not None else math.nan for p in points])
    vn = np.array([p.vn_mps if getattr(p, "vn_mps", None) is not None else math.nan for p in points])
    if np.isfinite(ve).mean() < 0.5:  # no Doppler: use the position-derived heading and speed
        ve = np.array([p.speed_mps * math.sin(math.radians(p.heading_deg)) for p in points])
        vn = np.array([p.speed_mps * math.cos(math.radians(p.heading_deg)) for p in points])
    ve, vn = np.nan_to_num(ve), np.nan_to_num(vn)
    grid = np.arange(gt[0], gt[-1], 1.0 / rate_hz)
    ve_g, vn_g = np.interp(grid, gt, ve), np.interp(grid, gt, vn)
    speed = np.hypot(ve_g, vn_g)
    width = max(1, round(rate_hz * 0.5))
    heading = _moving_mean(np.unwrap(np.arctan2(ve_g, vn_g)), width)
    rate = np.gradient(heading, 1.0 / rate_hz)
    rate[speed < 2.0] = 0.0
    return grid, rate, speed


def _normalised_corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / denom) if denom > 1e-12 else 0.0


@dataclass
class OffsetResult:
    offset_s: float  # GNSS time (s after the first GNSS point) at which the XDK clock reads 0
    correlation: float
    second_correlation: float  # best peak at least 5 s away from the winner
    overlap_s: float

    @property
    def confidence(self) -> str:
        if self.correlation >= 0.7 and self.correlation - self.second_correlation >= 0.15:
            return "high"
        if self.correlation >= 0.4:
            return "medium"
        return "low"


def required_overlap_s(xdk: XdkData, points: Sequence[object], fraction: float = 0.85) -> float:
    """Two logs of the same ride overlap almost completely; a loose limit lets any long log fit by chance."""
    gnss_s = (points[-1].time - points[0].time).total_seconds()
    return max(30.0, fraction * min(gnss_s, xdk.duration_s))


def find_offset(
    xdk: XdkData,
    points: Sequence[object],
    min_overlap_s: float | None = None,
    coarse_rate_hz: float = 10.0,
    fine_rate_hz: float = 50.0,
) -> OffsetResult:
    """Offset that best matches the XDK yaw rate to the GNSS heading rate."""
    if min_overlap_s is None:
        min_overlap_s = required_overlap_s(xdk, points)
    up = up_axis(xdk.acc)
    t_xdk, yaw = resample_mean(xdk.t, -(xdk.gyro @ up), fine_rate_hz)  # clockwise-positive about the vertical
    g_t, g_rate, _ = gnss_yaw_rate(points, fine_rate_hz)
    if g_t[-1] < min_overlap_s or xdk.duration_s < min_overlap_s:
        raise ValueError("Recording too short to match.")
    step = int(round(fine_rate_hz / coarse_rate_hz))
    smooth = max(1, round(fine_rate_hz * 0.5))
    yaw_s = _moving_mean(yaw, smooth)

    def score(offset: float, stride: int) -> tuple[float, float]:
        tg = t_xdk[::stride] + offset
        mask = (tg >= g_t[0]) & (tg <= g_t[-1])
        overlap = float(mask.sum() * stride / fine_rate_hz)
        if overlap < min_overlap_s:
            return -1.0, overlap
        return _normalised_corr(yaw_s[::stride][mask], np.interp(tg[mask], g_t, g_rate)), overlap

    lo = g_t[0] - xdk.duration_s + min_overlap_s
    hi = g_t[-1] - min_overlap_s
    coarse = [(off, *score(off, step)) for off in np.arange(lo, hi, 1.0 / coarse_rate_hz)]
    coarse = [item for item in coarse if item[1] > -1.0]
    if not coarse:
        raise ValueError("XDK and GNSS recordings do not overlap enough to match.")
    ordered = sorted(coarse, key=lambda item: -item[1])
    best_off = ordered[0][0]
    second = next((item[1] for item in ordered if abs(item[0] - best_off) >= 5.0), 0.0)
    fine = [(off, *score(off, 1)) for off in np.arange(best_off - 0.3, best_off + 0.3, 0.01)]
    fine = [item for item in fine if item[1] > -1.0]
    off, corr, overlap = max(fine, key=lambda item: item[1])
    return OffsetResult(float(off), float(corr), float(second), float(overlap))


def offset_curve(
    xdk: XdkData,
    points: Sequence[object],
    min_overlap_s: float = 30.0,
    step_s: float = 0.25,
    rate_hz: float = 10.0,
) -> list[tuple[float, float, float]]:
    """(offset s, yaw-rate correlation, overlap s) for every candidate offset: what find_offset maximises."""
    up = up_axis(xdk.acc)
    t_xdk, yaw = resample_mean(xdk.t, -(xdk.gyro @ up), rate_hz)
    g_t, g_rate, _ = gnss_yaw_rate(points, rate_hz)
    yaw_s = _moving_mean(yaw, max(1, round(rate_hz * 0.5)))
    out: list[tuple[float, float, float]] = []
    for offset in np.arange(g_t[0] - xdk.duration_s + min_overlap_s, g_t[-1] - min_overlap_s, step_s):
        tg = t_xdk + offset
        mask = (tg >= g_t[0]) & (tg <= g_t[-1])
        overlap = float(mask.sum() / rate_hz)
        if overlap >= min_overlap_s:
            out.append((float(offset), _normalised_corr(yaw_s[mask], np.interp(tg[mask], g_t, g_rate)), overlap))
    return out


def correlation_at(xdk: XdkData, points: Sequence[object], offset: float, rate_hz: float = 20.0) -> tuple[float, float]:
    """(yaw-rate correlation, overlap s) for one given offset."""
    up = up_axis(xdk.acc)
    t_xdk, yaw = resample_mean(xdk.t, -(xdk.gyro @ up), rate_hz)
    g_t, g_rate, _ = gnss_yaw_rate(points, rate_hz)
    yaw_s = _moving_mean(yaw, max(1, round(rate_hz * 0.5)))
    tg = t_xdk + offset
    mask = (tg >= g_t[0]) & (tg <= g_t[-1])
    if mask.sum() < 3:
        return 0.0, 0.0
    return _normalised_corr(yaw_s[mask], np.interp(tg[mask], g_t, g_rate)), float(mask.sum() / rate_hz)


def main() -> int:
    from imu_kalman import load_gnss, source_csv
    from session_paths import resolve_session_dir

    parser = argparse.ArgumentParser(description="Pair XDK logs with GNSS recordings and find the time offset.")
    parser.add_argument("--xdk", nargs="+", type=Path, required=True, help="XDK CSV files")
    parser.add_argument("--recordings", nargs="+", required=True, help="GNSS recording folders (names inside out/)")
    parser.add_argument("--source", default="bestnav")
    args = parser.parse_args()

    xdks = [load_xdk(path) for path in args.xdk]
    usable = [x for x in xdks if x.duration_s >= MIN_XDK_DURATION_S]
    for x in xdks:
        if x not in usable:
            print(f"Skipping {x.name}: only {x.duration_s:.1f} s of data")
    sessions = [resolve_session_dir(name) for name in args.recordings]
    tracks = {s: load_gnss(source_csv(s, args.source)) for s in sessions}
    print(f"{'':32}" + "".join(f"{x.name:>14}" for x in usable))
    for session in sessions:
        cells = []
        for x in usable:
            try:
                cells.append(f"{find_offset(x, tracks[session]).correlation:14.2f}")
            except ValueError:
                cells.append(f"{'-':>14}")
        print(f"{session.name:32}" + "".join(cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
