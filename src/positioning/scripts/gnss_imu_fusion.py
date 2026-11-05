#!/usr/bin/env python3
"""GNSS + accelerometer fusion: Kalman filter with bias state, outlier gating, ZUPT and RTS smoothing.

The IMU in this project is a 3-axis accelerometer only (no gyroscope), so it cannot give
orientation. The filter therefore works in a local ENU plane:

* state  x = [E, N, vE, vN, b]  (b = along-track accelerometer bias, m/s^2)
* IMU    drives the prediction with the along-track acceleration, projected on the travel
         direction taken from the filter's own velocity (not from raw GNSS heading). Without
         a gyroscope gravity cannot be separated from acceleration by orientation, so the
         slope term g*sin(pitch) is taken from the GNSS height profile and subtracted,
* GNSS   position (and Doppler velocity when available) corrects it at the real GNSS epochs,
* gating Mahalanobis innovation gate + Huber down-weighting reject wrong GNSS points,
* ZUPT   zero-velocity pseudo-measurement when the vehicle is standing still,
* RTS    a backward pass refines every point using the later measurements as well.

The module is duck-typed on purpose: it only reads attributes of the GNSS points and IMU
samples, so it does not import imu_kalman (which imports this module).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

import numpy as np

G0 = 9.80665
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "fusion_defaults.json"

STATUS_NONE = "none"
STATUS_USED = "used"
STATUS_DOWNWEIGHTED = "downweighted"
STATUS_REJECTED = "rejected"
STATUS_REACQUIRED = "reacquired"
STATUS_OUTAGE = "outage"
_STATUS_RANK = {
    STATUS_NONE: 0,
    STATUS_OUTAGE: 1,
    STATUS_REJECTED: 2,
    STATUS_DOWNWEIGHTED: 3,
    STATUS_REACQUIRED: 4,
    STATUS_USED: 5,
}


@dataclass
class FusionConfig:
    fusion_rate_hz: float = 100.0
    gnss_sigma_m: float | None = None
    gnss_sigma_by_source: dict[str, float] = field(default_factory=lambda: {
        "fixed_ppk": 0.05, "float_ppk": 0.3, "dgps": 0.8, "bestnav": 1.0, "observation": 2.5,
    })
    gnss_sigma_by_position_type: dict[str, float] = field(default_factory=dict)
    gnss_sigma_scale: float = 1.0
    gnss_update_period_s: float = 0.0
    use_doppler_velocity: bool = True
    gnss_speed_sigma_mps: float = 0.1
    accel_noise_along_mps2: float = 0.2
    accel_noise_lateral_mps2: float = 2.0
    bias_random_walk_mps2: float = 0.005
    initial_bias_sigma_mps2: float = 0.5
    outlier_gate_sigma: float = 3.5
    huber_sigma: float = 2.0
    max_reject_duration_s: float = 3.0
    doppler_gate_sigma: float = 10.0
    reacquire_sigma_scale: float = 10.0
    zupt: bool = True
    static_speed_mps: float = 0.2
    zupt_accel_std_mps2: float = 0.1
    zupt_window_s: float = 0.5
    zupt_sigma_mps: float = 0.02
    min_heading_speed_mps: float = 0.5
    min_axis_r2: float = 0.05
    max_bias_mps2: float = 2.0
    slope_compensation: bool = True
    slope_window_s: float = 3.0
    forward_axis: list[float] | None = None
    smooth: bool = True

    @classmethod
    def load(cls, path: Path | None = None, overrides: dict[str, Any] | None = None) -> "FusionConfig":
        """Dataclass defaults < JSON file < explicit overrides (None overrides are ignored)."""
        values: dict[str, Any] = {}
        config_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if config_path.is_file():
            values.update(json.loads(config_path.read_text(encoding="utf-8")))
        elif path:
            raise FileNotFoundError(f"Fusion config not found: {config_path}")
        for key, value in (overrides or {}).items():
            if value is not None:
                values[key] = value
        known = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in known})

    def sigma_for(self, source: str, position_type: str | None, row_sigma: float | None) -> float:
        if self.gnss_sigma_m is not None:
            sigma = self.gnss_sigma_m
        elif row_sigma is not None:
            sigma = row_sigma
        elif position_type and position_type.upper() in self.gnss_sigma_by_position_type:
            sigma = self.gnss_sigma_by_position_type[position_type.upper()]
        else:
            sigma = self.gnss_sigma_by_source.get(source, 1.0)
        return max(1e-3, sigma * self.gnss_sigma_scale)


@dataclass
class FusionResult:
    times: list[datetime]
    east: np.ndarray
    north: np.ndarray
    height: np.ndarray
    ve: np.ndarray
    vn: np.ndarray
    bias: np.ndarray
    sigma_e: np.ndarray
    sigma_n: np.ndarray
    zupt: np.ndarray
    gnss_status: list[str]
    innovation: np.ndarray
    gnss_log: list[dict[str, object]]
    info: dict[str, object]


def parse_outages(values: Sequence[str] | None) -> list[tuple[float, float]]:
    """'10:15' -> (10.0, 15.0); seconds from the first IMU/GNSS overlap sample."""
    windows: list[tuple[float, float]] = []
    for value in values or []:
        try:
            start_text, end_text = str(value).split(":", 1)
            start, end = float(start_text), float(end_text)
        except ValueError as exc:
            raise SystemExit(f"Invalid --gnss-outage {value!r}; use START:END in seconds.") from exc
        if end <= start:
            raise SystemExit(f"Invalid --gnss-outage {value!r}: END must be greater than START.")
        windows.append((start, end))
    return windows


def _moving_mean(values: np.ndarray, width: int) -> np.ndarray:
    width = max(1, int(width))
    if width == 1 or len(values) == 0:
        return values.astype(float, copy=True)
    kernel = np.ones(width)
    counts = np.convolve(np.ones(len(values)), kernel, "same")
    if values.ndim == 1:
        return np.convolve(values, kernel, "same") / counts
    return np.column_stack([np.convolve(values[:, i], kernel, "same") / counts for i in range(values.shape[1])])


def _moving_std(values: np.ndarray, width: int) -> np.ndarray:
    mean = _moving_mean(values, width)
    return np.sqrt(np.maximum(0.0, _moving_mean(values * values, width) - mean * mean))


def _bin_imu(t: np.ndarray, acc: np.ndarray, rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Average IMU samples into fixed bins (noise reduction + speed). No-op for slow IMUs."""
    if rate_hz <= 0 or len(t) < 2:
        return t, acc
    bins = np.floor((t - t[0]) * rate_hz).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, np.diff(bins) != 0])
    counts = np.diff(np.r_[starts, len(t)])
    t_out = np.add.reduceat(t, starts) / counts
    acc_out = np.add.reduceat(acc, starts, axis=0) / counts[:, None]
    return t_out, acc_out


def slope_sine(height: np.ndarray, speed: np.ndarray, dt: float, window_s: float, min_speed_mps: float = 1.0) -> np.ndarray:
    """sin(pitch) of the path from the (smoothed) GNSS height profile; 0 when (almost) standing."""
    width = max(1, round(window_s / max(dt, 1e-6)))
    rate = np.gradient(_moving_mean(height, width), dt)
    horizontal = _moving_mean(speed, width)
    total = np.hypot(horizontal, rate)
    sine = np.where(horizontal > min_speed_mps, rate / np.maximum(total, 1e-6), 0.0)
    return np.clip(sine, -0.5, 0.5)


def estimate_forward_axis(
    acc: np.ndarray,
    gnss_speed: np.ndarray,
    slope_sin: np.ndarray,
    dt: float,
    window_s: float,
    min_speed_mps: float = 1.0,
) -> tuple[np.ndarray, float]:
    """Find the sensor-frame travel axis w with  w.acc = d(speed)/dt + g*sin(pitch)  (least squares)."""
    width = max(1, round(window_s / max(dt, 1e-6)))
    target = np.gradient(_moving_mean(gnss_speed, width), dt) + G0 * slope_sin
    features = _moving_mean(acc, max(1, width // 2))
    mask = gnss_speed > min_speed_mps
    if int(mask.sum()) < 50:
        return np.array([1.0, 0.0, 0.0]), 0.0
    # The travel axis is (nearly) perpendicular to gravity, so fit it inside that plane. A free 3-axis
    # fit lets the almost-constant gravity channel pick up random weight from GNSS speed noise.
    mean_acc = features[mask].mean(axis=0)
    down = mean_acc / max(float(np.linalg.norm(mean_acc)), 1e-9)
    helper = np.array([1.0, 0.0, 0.0]) if abs(down[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(down, helper)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(down, e1)
    basis = np.column_stack([e1, e2])
    f = (features[mask] - mean_acc) @ basis
    y = target[mask] - target[mask].mean()
    coeffs, *_ = np.linalg.lstsq(f, y, rcond=None)
    norm = float(np.linalg.norm(coeffs))
    if norm < 1e-9:
        return np.array([1.0, 0.0, 0.0]), 0.0
    sst = float(np.sum(y**2))
    r2 = 0.0 if sst <= 0 else max(0.0, 1.0 - float(np.sum((y - f @ coeffs) ** 2)) / sst)
    return (basis @ coeffs) / norm, r2


def gnss_speed_series(points: Sequence[Any]) -> np.ndarray:
    """Speed per GNSS point: Doppler where the source has it, otherwise from neighbouring positions."""
    speed = np.array([max(0.0, p.speed_mps) for p in points])
    for i, p in enumerate(points):
        if getattr(p, "ve_mps", None) is not None and getattr(p, "vn_mps", None) is not None:
            speed[i] = math.hypot(p.ve_mps, p.vn_mps)
    return speed


def scan_alignment(
    points: Sequence[Any],
    samples: Sequence[Any],
    lo_s: float | None = None,
    hi_s: float | None = None,
    coarse_step_s: float = 0.5,
    fine_step_s: float = 0.05,
    rate_hz: float = 20.0,
    min_overlap_s: float = 30.0,
) -> dict[str, Any]:
    """Score every IMU time offset by how well the IMU explains GNSS acceleration (forward-axis fit R2).

    The offset is the GNSS time (seconds after the first GNSS point) at which the IMU clock reads 0.
    """
    t0 = points[0].time
    gt = np.array([(p.time - t0).total_seconds() for p in points])
    speed = gnss_speed_series(points)
    height = np.array([p.height for p in points])
    imu_t = np.array([s.seconds for s in samples])
    imu_acc = np.array([[s.ax_mps2, s.ay_mps2, s.az_mps2] for s in samples])
    tb, ab = _bin_imu(imu_t - imu_t[0], imu_acc, rate_hz)
    tb = tb + imu_t[0]
    dt = 1.0 / rate_hz
    duration_gnss = float(gt[-1])
    duration_imu = float(imu_t[-1] - imu_t[0])
    lo = -duration_imu + min_overlap_s if lo_s is None else lo_s
    hi = duration_gnss - min_overlap_s if hi_s is None else hi_s

    shorter = max(1.0, min(duration_gnss, duration_imu))

    def score(offset: float) -> tuple[float, float, np.ndarray, float] | None:
        """(score, raw R2, axis, overlap seconds). Short overlaps are down-weighted: a lucky fit on a
        few seconds of strong acceleration must not beat a decent fit over the whole ride."""
        tg = tb + offset
        mask = (tg >= gt[0]) & (tg <= gt[-1])
        overlap = float(mask.sum() * dt)
        if overlap < min_overlap_s:
            return None
        speed_i = np.interp(tg[mask], gt, speed)
        slope = slope_sine(np.interp(tg[mask], gt, height), speed_i, dt, 3.0)
        axis, r2 = estimate_forward_axis(ab[mask], speed_i, slope, dt, 1.0)
        return r2 * math.sqrt(min(1.0, overlap / shorter)), r2, axis, overlap

    curve: list[list[float]] = []
    offset = lo
    while offset <= hi:
        result = score(offset)
        if result is not None:
            curve.append([round(offset, 3), round(result[0], 4)])  # weighted score
        offset += coarse_step_s
    if not curve:
        raise ValueError("IMU un GNSS pārklājas par īsu laiku, lai meklētu nobīdi.")

    # Local maxima at least 5 s apart, best first (ranked by the overlap-weighted score).
    ordered = sorted(curve, key=lambda item: -item[1])
    peaks: list[dict[str, Any]] = []
    for off, _ in ordered:
        if all(abs(off - peak["offset_s"]) >= 5.0 for peak in peaks):
            best_off, best = off, None
            fine = off - coarse_step_s
            while fine <= off + coarse_step_s:
                result = score(fine)
                if result is not None and (best is None or result[0] > best[0]):
                    best_off, best = fine, result
                fine += fine_step_s
            peaks.append({"offset_s": round(best_off, 3), "score": round(best[0], 4), "r2": round(best[1], 4),
                          "axis": [round(float(v), 4) for v in best[2]], "overlap_s": round(best[3], 1)})
        if len(peaks) == 3:
            break
    second = peaks[1]["score"] if len(peaks) > 1 else 0.0
    best = peaks[0]["score"]
    if best >= 0.3 and best >= 1.5 * second:
        confidence = "high"
    elif best >= 0.1:
        confidence = "medium"
    else:
        confidence = "low"
    return {"curve": curve, "peaks": peaks, "confidence": confidence,
            "has_doppler": bool(any(getattr(p, "ve_mps", None) is not None for p in points[:50]))}


def _gnss_update(
    x: np.ndarray,
    p: np.ndarray,
    z: np.ndarray,
    h: np.ndarray,
    r: np.ndarray,
    gate: float,
    huber: float,
    gate_enabled: bool = True,
) -> tuple[np.ndarray, np.ndarray, str, float]:
    nu = z - h @ x
    s = h @ p @ h.T + r
    d = float(math.sqrt(max(0.0, nu @ np.linalg.solve(s, nu))))
    status = STATUS_USED
    r_eff = r
    if gate_enabled and d > gate:
        return x, p, STATUS_REJECTED, d
    if d > huber:
        r_eff = r * (d / huber)
        s = h @ p @ h.T + r_eff
        status = STATUS_DOWNWEIGHTED
    k = p @ h.T @ np.linalg.inv(s)
    x = x + k @ nu
    i_kh = np.eye(len(x)) - k @ h
    p = i_kh @ p @ i_kh.T + k @ r_eff @ k.T
    return x, 0.5 * (p + p.T), status, d


def _zupt_update(x: np.ndarray, p: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    h = np.zeros((2, 5))
    h[0, 2] = h[1, 3] = 1.0
    r = np.eye(2) * sigma * sigma
    s = h @ p @ h.T + r
    k = p @ h.T @ np.linalg.inv(s)
    x = x + k @ (-(h @ x))
    i_kh = np.eye(5) - k @ h
    p = i_kh @ p @ i_kh.T + k @ r @ k.T
    return x, 0.5 * (p + p.T)


def run_fusion(
    points: Sequence[Any],
    samples: Sequence[Any],
    source: str,
    cfg: FusionConfig,
    imu_start_delay_s: float = 0.0,
    outages: Sequence[tuple[float, float]] = (),
) -> FusionResult:
    start_second = samples[0].seconds + max(0.0, imu_start_delay_s)
    overlap = [
        s for s in samples
        if s.time and s.seconds >= start_second and points[0].time <= s.time <= points[-1].time
    ]
    if len(overlap) < 2:
        raise SystemExit("No IMU/GNSS overlap after alignment. Try --auto-align or --time-offset-s.")

    t0 = overlap[0].time
    t_raw = np.array([(s.time - t0).total_seconds() for s in overlap])
    acc_raw = np.array([[s.ax_mps2, s.ay_mps2, s.az_mps2] for s in overlap])
    t_g, acc = _bin_imu(t_raw, acc_raw, cfg.fusion_rate_hz)
    if len(t_g) < 3:
        raise SystemExit("Too few IMU samples in the GNSS overlap for fusion.")
    dt_g = float(np.median(np.diff(t_g)))

    # --- GNSS arrays (seconds relative to t0) ---
    gt = np.array([(p.time - t0).total_seconds() for p in points])
    g_east = np.array([p.east for p in points])
    g_north = np.array([p.north for p in points])
    g_height = np.array([p.height for p in points])
    g_ve = np.array([getattr(p, "ve_mps", None) if getattr(p, "ve_mps", None) is not None else np.nan for p in points])
    g_vn = np.array([getattr(p, "vn_mps", None) if getattr(p, "vn_mps", None) is not None else np.nan for p in points])
    g_speed_pos = np.array([max(0.0, p.speed_mps) for p in points])
    g_heading = np.unwrap(np.radians([p.heading_deg for p in points]))
    has_dop = np.isfinite(g_ve) & np.isfinite(g_vn)
    g_speed = np.where(has_dop, np.hypot(np.nan_to_num(g_ve), np.nan_to_num(g_vn)), g_speed_pos)
    g_sigma = np.array([
        cfg.sigma_for(source, getattr(p, "position_type", None), getattr(p, "sigma_m", None)) for p in points
    ])

    speed_grid = np.interp(t_g, gt, g_speed)

    # --- IMU: slope compensation and forward axis ---
    height_grid = np.interp(t_g, gt, g_height)
    slope = slope_sine(height_grid, speed_grid, dt_g, cfg.slope_window_s) if cfg.slope_compensation else np.zeros(len(t_g))
    if cfg.forward_axis is not None:
        axis = np.asarray(cfg.forward_axis, dtype=float)
        norm = float(np.linalg.norm(axis))
        if axis.shape != (3,) or norm < 1e-9:
            raise SystemExit("forward_axis must be three non-zero numbers.")
        axis, axis_r2 = axis / norm, None
    else:
        axis, axis_r2 = estimate_forward_axis(acc, speed_grid, slope, dt_g, 1.0)
    # Specific force along the travel axis minus the gravity share of the slope = kinematic acceleration.
    along = acc @ axis - G0 * slope
    imu_used = axis_r2 is None or axis_r2 >= cfg.min_axis_r2
    if not imu_used:
        # The IMU does not explain the GNSS acceleration (wrong alignment/axis?): run as a GNSS-only
        # constant-velocity filter instead of integrating nonsense.
        along = np.zeros_like(along)

    # --- stationary detection (ZUPT) ---
    static = np.zeros(len(t_g), dtype=bool)
    if cfg.zupt:
        std_width = max(2, round(cfg.zupt_window_s / max(dt_g, 1e-6)))
        static = (speed_grid <= cfg.static_speed_mps) & (_moving_std(np.linalg.norm(acc, axis=1), std_width) <= cfg.zupt_accel_std_mps2)

    static_f = static.astype(float)

    # --- GNSS epochs used as measurements ---
    t_start, t_end = float(t_g[0]), float(t_g[-1])
    epoch_idx: list[int] = []
    last_t = -1e18
    for i, value in enumerate(gt):
        if value < t_start or value > t_end:
            continue
        if value - last_t < cfg.gnss_update_period_s:
            continue
        epoch_idx.append(i)
        last_t = value
    if not epoch_idx:
        raise SystemExit("No GNSS epochs inside the IMU overlap.")

    def in_outage(value: float) -> bool:
        return any(a <= value <= b for a, b in outages)

    # --- merged timeline: IMU grid nodes + real GNSS epochs ---
    node_t = np.concatenate([t_g, gt[epoch_idx]])
    node_kind = np.concatenate([np.zeros(len(t_g), dtype=int), np.ones(len(epoch_idx), dtype=int)])
    node_ref = np.concatenate([np.arange(len(t_g)), np.array(epoch_idx)])
    order = np.lexsort((node_kind, node_t))
    node_t, node_kind, node_ref = node_t[order], node_kind[order], node_ref[order]
    n_nodes = len(node_t)

    # --- initial state from GNSS at the first node ---
    e0 = float(np.interp(t_start, gt, g_east))
    n0 = float(np.interp(t_start, gt, g_north))
    h0 = float(np.interp(t_start, gt, g_heading))
    s0 = float(np.interp(t_start, gt, g_speed))
    u = np.array([math.sin(h0), math.cos(h0)])
    if has_dop.any() and cfg.use_doppler_velocity:
        ve0 = float(np.interp(t_start, gt[has_dop], g_ve[has_dop]))
        vn0 = float(np.interp(t_start, gt[has_dop], g_vn[has_dop]))
    else:
        ve0, vn0 = s0 * u[0], s0 * u[1]
    sigma0 = float(np.interp(t_start, gt, g_sigma))
    x = np.array([e0, n0, ve0, vn0, 0.0])
    p = np.diag([sigma0**2, sigma0**2, 1.0, 1.0, cfg.initial_bias_sigma_mps2**2])

    x_pred = np.zeros((n_nodes, 5))
    p_pred = np.zeros((n_nodes, 5, 5))
    f_all = np.tile(np.eye(5), (n_nodes, 1, 1))
    x_filt = np.zeros((n_nodes, 5))
    p_filt = np.zeros((n_nodes, 5, 5))
    x_pred[0], p_pred[0], x_filt[0], p_filt[0] = x, p, x, p

    n_grid = len(t_g)
    row_status = [STATUS_NONE] * n_grid
    row_d = np.zeros(n_grid)
    row_zupt = np.zeros(n_grid, dtype=bool)
    gnss_log: list[dict[str, object]] = []
    node_log_index: dict[int, int] = {}
    reject_start: float | None = None
    reject_count = 0
    gate = cfg.outlier_gate_sigma
    huber = min(cfg.huber_sigma, gate)
    sl2 = cfg.accel_noise_lateral_mps2**2
    sa2 = cfg.accel_noise_along_mps2**2 if imu_used else sl2
    qb = cfg.bias_random_walk_mps2**2
    eye2 = np.eye(2)
    pos_h = np.zeros((2, 5))
    pos_h[0, 0] = pos_h[1, 1] = 1.0
    vel_h = np.zeros((2, 5))
    vel_h[0, 2] = vel_h[1, 3] = 1.0

    for k in range(1, n_nodes):
        dt = float(node_t[k] - node_t[k - 1])
        speed = math.hypot(x[2], x[3])
        if speed > cfg.min_heading_speed_mps:
            u = np.array([x[2] / speed, x[3] / speed])
        if dt > 0:
            t_mid = 0.5 * (node_t[k] + node_t[k - 1])
            if np.interp(t_mid, t_g, static_f) > 0.5:
                a_mid = 0.0  # standing still: the accelerometer only shows gravity/bias, so do not integrate it
            else:
                a_mid = float(np.interp(t_mid, t_g, along)) - x[4]
            x = x.copy()
            x[0] += x[2] * dt + 0.5 * a_mid * u[0] * dt * dt
            x[1] += x[3] * dt + 0.5 * a_mid * u[1] * dt * dt
            x[2] += a_mid * u[0] * dt
            x[3] += a_mid * u[1] * dt
            f = np.eye(5)
            f[0, 2] = f[1, 3] = dt
            f[0, 4], f[1, 4] = -0.5 * u[0] * dt * dt, -0.5 * u[1] * dt * dt
            f[2, 4], f[3, 4] = -u[0] * dt, -u[1] * dt
            uu = np.outer(u, u)
            sigma_a = sa2 * uu + sl2 * (eye2 - uu)
            q = np.zeros((5, 5))
            q[:2, :2] = dt**3 / 3.0 * sigma_a
            q[:2, 2:4] = dt**2 / 2.0 * sigma_a
            q[2:4, :2] = dt**2 / 2.0 * sigma_a
            q[2:4, 2:4] = dt * sigma_a
            q[4, 4] = qb * dt
            p = f @ p @ f.T + q
            p = 0.5 * (p + p.T)
            f_all[k] = f
        x_pred[k], p_pred[k] = x, p

        if node_kind[k] == 0:
            gi = int(node_ref[k])
            if static[gi]:
                x, p = _zupt_update(x, p, cfg.zupt_sigma_mps)
                row_zupt[gi] = True
        else:
            pi = int(node_ref[k])
            row = int(np.searchsorted(t_g, node_t[k], side="left"))
            row = min(row, n_grid - 1)
            if in_outage(node_t[k]):
                status, d = STATUS_OUTAGE, 0.0
            else:
                sigma = float(g_sigma[pi])
                r_pos = np.eye(2) * sigma * sigma
                escape = reject_start is not None and reject_count >= 3 and node_t[k] - reject_start >= cfg.max_reject_duration_s
                if escape:
                    r_pos = r_pos * cfg.reacquire_sigma_scale**2
                x, p, status, d = _gnss_update(
                    x, p, np.array([g_east[pi], g_north[pi]]), pos_h, r_pos, gate, huber, gate_enabled=not escape
                )
                if status == STATUS_REJECTED:
                    reject_count += 1
                    if reject_start is None:
                        reject_start = float(node_t[k])
                else:
                    if escape:
                        status = STATUS_REACQUIRED
                    reject_start, reject_count = None, 0
                if cfg.use_doppler_velocity and has_dop[pi]:
                    # Doppler velocity is independent of the position error, so it is applied even when the
                    # position was rejected: it is what pulls a wrong velocity/heading back after a stop.
                    r_vel = np.eye(2) * cfg.gnss_speed_sigma_mps**2
                    x, p, _, _ = _gnss_update(
                        x, p, np.array([g_ve[pi], g_vn[pi]]), vel_h, r_vel, cfg.doppler_gate_sigma, min(huber, cfg.doppler_gate_sigma)
                    )
            if _STATUS_RANK[status] > _STATUS_RANK[row_status[row]]:
                row_status[row] = status
            row_d[row] = max(row_d[row], d)
            node_log_index[k] = len(gnss_log)
            gnss_log.append({
                "time_s": float(node_t[k]),
                "status": status,
                "innovation_sigma": d,
                "sigma_m": float(g_sigma[pi]),
                "east_m": float(g_east[pi]),
                "north_m": float(g_north[pi]),
            })
        x[4] = min(cfg.max_bias_mps2, max(-cfg.max_bias_mps2, x[4]))
        x_filt[k], p_filt[k] = x, p

    # --- RTS smoother ---
    x_s, p_s = x_filt.copy(), p_filt.copy()
    if cfg.smooth:
        for k in range(n_nodes - 2, -1, -1):
            f_next = f_all[k + 1]
            gain = p_filt[k] @ f_next.T @ np.linalg.pinv(p_pred[k + 1])
            x_s[k] = x_filt[k] + gain @ (x_s[k + 1] - x_pred[k + 1])
            p_s[k] = p_filt[k] + gain @ (p_s[k + 1] - p_pred[k + 1]) @ gain.T
            p_s[k] = 0.5 * (p_s[k] + p_s[k].T)

    grid_nodes = np.flatnonzero(node_kind == 0)
    sel_x = x_s[grid_nodes]
    sel_p = p_s[grid_nodes]
    # grid nodes appear in grid order because ties sort grid first and t_g is increasing
    info: dict[str, object] = {
        "fusion_rows": int(n_grid),
        "fusion_dt_s": dt_g,
        "forward_axis": ",".join(f"{v:.4f}" for v in axis),
        "imu_used": int(imu_used),
        "forward_axis_r2": "" if axis_r2 is None else f"{axis_r2:.4f}",
        "gnss_epochs": len(epoch_idx),
        "gnss_used": sum(1 for r in gnss_log if r["status"] in (STATUS_USED, STATUS_REACQUIRED)),
        "gnss_downweighted": sum(1 for r in gnss_log if r["status"] == STATUS_DOWNWEIGHTED),
        "gnss_rejected": sum(1 for r in gnss_log if r["status"] == STATUS_REJECTED),
        "gnss_outage": sum(1 for r in gnss_log if r["status"] == STATUS_OUTAGE),
        "zupt_rows": int(row_zupt.sum()),
        "final_bias_mps2": float(sel_x[-1, 4]),
        "smoothed": bool(cfg.smooth),
    }
    if outages:
        errors = []
        for k, log_index in node_log_index.items():
            entry = gnss_log[log_index]
            if entry["status"] != STATUS_OUTAGE:
                continue
            errors.append(math.hypot(x_s[k, 0] - entry["east_m"], x_s[k, 1] - entry["north_m"]))
        if errors:
            arr = np.array(errors)
            info["outage_rmse_m"] = float(np.sqrt(np.mean(arr**2)))
            info["outage_max_m"] = float(arr.max())
            info["outage_points"] = len(errors)
            info["outage_ref_sigma_m"] = float(np.median([e["sigma_m"] for e in gnss_log if e["status"] == STATUS_OUTAGE]))

    return FusionResult(
        times=[t0 + timedelta(seconds=float(v)) for v in t_g],
        east=sel_x[:, 0],
        north=sel_x[:, 1],
        height=height_grid,
        ve=sel_x[:, 2],
        vn=sel_x[:, 3],
        bias=sel_x[:, 4],
        sigma_e=np.sqrt(np.maximum(0.0, sel_p[:, 0, 0])),
        sigma_n=np.sqrt(np.maximum(0.0, sel_p[:, 1, 1])),
        zupt=row_zupt,
        gnss_status=row_status,
        innovation=row_d,
        gnss_log=gnss_log,
        info=info,
    )
