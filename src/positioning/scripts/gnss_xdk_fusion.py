#!/usr/bin/env python3
"""GNSS + XDK (3-axis accelerometer + 3-axis gyroscope) fusion with an error-state Kalman filter.

Unlike gnss_imu_fusion.py, which only has an accelerometer and has to work in a 2-D plane, the gyroscope
lets this filter carry the full attitude and run a strapdown INS in a local ENU frame:

* nominal state  R (body -> ENU), v, p, accelerometer bias ba, gyroscope bias bg
* error state    dx = [dp, dv, dtheta, dba, dbg, dk]  (16), dtheta is expressed in the ENU frame;
                 k is the accelerometer sensitivity error, f_true = (f_measured - ba) / (1 + k)
* prediction     every XDK sample: integrate the gyro into R, the specific force into v and p
* GNSS           position and Doppler velocity at the real GNSS epochs, with the Mahalanobis gate and
                 Huber down-weighting of gnss_imu_fusion
* ZUPT           zero velocity when GNSS shows the vehicle standing and the gyro is quiet, together
                 with a zero-angular-rate update (ZARU) that reads the gyro bias straight off the
                 stationary gyro. Without it the filter blames the gyro bias for the body rocking
                 at a standstill and carries a wrong pitch into the next acceleration.
* NHC            non-holonomic constraint: a car does not slide sideways or jump (lateral and vertical
                 body velocity ~ 0). It is what keeps heading and gyro bias observable between GNSS epochs.

The XDK mounting is not known, so the sensor 'up' axis comes from gravity and the forward axis from
the same GNSS-acceleration fit the accelerometer-only filter uses. Both are only used to start the
filter and to define the NHC axes; the attitude itself is then estimated.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gnss_imu_fusion import (
    STATUS_DOWNWEIGHTED,
    STATUS_NONE,
    STATUS_OUTAGE,
    STATUS_REACQUIRED,
    STATUS_REJECTED,
    STATUS_USED,
    FusionConfig,
    _STATUS_RANK,
    _gnss_update,
    _moving_mean,
    estimate_forward_axis,
    parse_outages,
    slope_sine,
)
from imu_kalman import enu_to_llh, load_gnss, source_csv, GNSS_SOURCES
import imu_links
from session_paths import find_original_bin, output_subdir, resolve_session_dir
from xdk_imu import XdkData, find_offset, load_xdk, resample_mean, up_axis

DEFAULT_CONFIG_PATH = ROOT / "config" / "xdk_fusion_defaults.json"
NSTATE = 16
EYEN = np.eye(NSTATE)


@dataclass
class XdkFusionConfig:
    gnss_sigma_m: float | None = None
    gnss_sigma_scale: float = 1.0
    vertical_sigma_factor: float = 2.0
    gnss_speed_sigma_mps: float = 0.1
    use_doppler_velocity: bool = True
    gnss_update_period_s: float = 0.0
    accel_noise_mps2_sqrt_hz: float = 0.1
    gyro_noise_rps_sqrt_hz: float = 0.002
    accel_bias_walk: float = 0.003
    gyro_bias_walk: float = 0.0001
    initial_accel_bias_sigma_mps2: float = 0.3
    initial_gyro_bias_sigma_rps: float = 0.01
    initial_tilt_sigma_deg: float = 3.0
    initial_yaw_sigma_deg: float = 10.0
    initial_velocity_sigma_mps: float = 0.3
    outlier_gate_sigma: float = 4.0
    huber_sigma: float = 2.5
    max_reject_duration_s: float = 3.0
    reacquire_sigma_scale: float = 10.0
    zupt: bool = True
    static_speed_mps: float = 0.2
    zupt_gyro_rps: float = 0.05
    zupt_sigma_mps: float = 0.05
    zaru_sigma_rps: float = 0.003
    zupt_guard_s: float = 1.0
    accel_scale_from_gravity: bool = True
    initial_scale_sigma: float = 0.03
    scale_walk: float = 1e-5
    nhc: bool = True
    nhc_min_speed_mps: float = 2.0
    nhc_sigma_lateral_mps: float = 0.4
    nhc_sigma_vertical_mps: float = 0.4
    nhc_period_s: float = 0.1
    nhc_min_axis_r2: float = 0.10  # NHC needs the travel axis; a fit with a lower R2 means the XDK is not rigidly mounted
    forward_axis: list[float] | None = None
    output_rate_hz: float = 20.0
    max_imu_gap_s: float = 0.2
    assume_stationary: bool | None = None  # None: stationary when the GNSS speed never reaches nhc_min_speed_mps
    static_acc_std_mps2: float = 0.2  # |a| standard deviation over 1 s below this counts as quiet
    static_speed_unreliable_mps: float = 1.0  # GNSS speed limit for 'static' when there is no Doppler speed

    @classmethod
    def load(cls, path: Path | None = None, overrides: dict[str, Any] | None = None) -> "XdkFusionConfig":
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


@dataclass
class XdkFusionResult:
    times: list[datetime]
    east: np.ndarray
    north: np.ndarray
    up: np.ndarray
    ve: np.ndarray
    vn: np.ndarray
    vu: np.ndarray
    heading_deg: np.ndarray  # direction of the vehicle's forward axis, clockwise from north
    pitch_deg: np.ndarray
    roll_deg: np.ndarray
    accel_bias: np.ndarray  # (n, 3) sensor frame, m/s^2
    gyro_bias: np.ndarray  # (n, 3) sensor frame, deg/s
    sigma_e: np.ndarray
    sigma_n: np.ndarray
    gnss_status: list[str]
    innovation: np.ndarray
    zupt: np.ndarray
    gnss_log: list[dict[str, object]]
    info: dict[str, object] = field(default_factory=dict)


def skew(v: np.ndarray) -> np.ndarray:
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def exp_so3(w: np.ndarray) -> np.ndarray:
    theta = math.sqrt(float(w @ w))
    k = skew(w)
    if theta < 1e-9:
        return np.eye(3) + k
    return np.eye(3) + (math.sin(theta) / theta) * k + ((1.0 - math.cos(theta)) / (theta * theta)) * (k @ k)


def orthonormalise(r: np.ndarray) -> np.ndarray:
    u, _, vt = np.linalg.svd(r)
    return u @ vt


def local_gravity(lat_deg: float, height_m: float) -> float:
    """WGS84 normal gravity (Somigliana) with the free-air correction."""
    s = math.sin(math.radians(lat_deg)) ** 2
    return 9.7803253359 * (1 + 0.00193185265241 * s) / math.sqrt(1 - 0.00669437999013 * s) - 3.086e-6 * height_m


def level_rotation(up_b: np.ndarray, fwd_b: np.ndarray, heading_rad: float) -> np.ndarray:
    """Body -> ENU rotation for a vehicle whose forward axis (sensor frame) points along `heading_rad`."""
    left_b = np.cross(up_b, fwd_b)
    f_n = np.array([math.sin(heading_rad), math.cos(heading_rad), 0.0])
    u_n = np.array([0.0, 0.0, 1.0])
    l_n = np.cross(u_n, f_n)
    return np.outer(f_n, fwd_b) + np.outer(l_n, left_b) + np.outer(u_n, up_b)


def attitude_angles(r: np.ndarray, fwd_b: np.ndarray, up_b: np.ndarray) -> tuple[float, float, float]:
    """(heading, pitch, roll) in degrees of the vehicle axes: forward = fwd_b, left = up x fwd, up = up_b."""
    f = r @ fwd_b
    left = r @ np.cross(up_b, fwd_b)
    heading = math.degrees(math.atan2(f[0], f[1])) % 360.0
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, f[2]))))
    roll = math.degrees(math.asin(max(-1.0, min(1.0, left[2]))))
    return heading, pitch, roll


class _GnssTrack:
    """GNSS points as arrays on the time base of the fusion (seconds after the first GNSS point)."""

    def __init__(self, points: Sequence[Any], cfg: XdkFusionConfig, source: str):
        base = FusionConfig.load(None, {"gnss_sigma_m": cfg.gnss_sigma_m, "gnss_sigma_scale": cfg.gnss_sigma_scale})
        t0 = points[0].time
        self.t0 = t0
        self.t = np.array([(p.time - t0).total_seconds() for p in points])
        self.e = np.array([p.east for p in points])
        self.n = np.array([p.north for p in points])
        self.u = np.array([p.height - points[0].height for p in points])
        self.sigma = np.array([base.sigma_for(source, getattr(p, "position_type", None), getattr(p, "sigma_m", None)) for p in points])
        nan = math.nan
        self.vel = np.array([
            [p.ve_mps, p.vn_mps, p.vu_mps if getattr(p, "vu_mps", None) is not None else nan]
            if getattr(p, "ve_mps", None) is not None else [nan, nan, nan]
            for p in points
        ])
        self.has_vel = np.isfinite(self.vel[:, :2]).all(axis=1)
        speed = np.hypot(np.nan_to_num(self.vel[:, 0]), np.nan_to_num(self.vel[:, 1]))
        pos_speed = np.array([max(0.0, p.speed_mps) for p in points])
        # The receiver's first Doppler velocities after a start are unreliable (e.g. 10 m/s while the position
        # moves 24 m/s); a velocity that disagrees with the position-derived speed is not used.
        self.has_vel &= np.abs(speed - pos_speed) <= np.maximum(2.0, 0.2 * pos_speed)
        self.speed = np.where(self.has_vel, speed, pos_speed)
        self.heading = np.unwrap(np.radians([p.heading_deg for p in points]))
        self.lat0, self.lon0, self.h0 = points[0].lat, points[0].lon, points[0].height

    def interp(self, values: np.ndarray, t: float) -> float:
        return float(np.interp(t, self.t, values))

    def velocity_at(self, t: float) -> np.ndarray:
        ok = self.has_vel
        if ok.any():
            ve = np.interp(t, self.t[ok], self.vel[ok, 0])
            vn = np.interp(t, self.t[ok], self.vel[ok, 1])
            vu = np.interp(t, self.t[ok], np.nan_to_num(self.vel[ok, 2]))
            return np.array([ve, vn, vu])
        h = self.interp(self.heading, t)
        s = self.interp(self.speed, t)
        return np.array([s * math.sin(h), s * math.cos(h), 0.0])


def _static_mask(xdk: XdkData, gnss: _GnssTrack, offset: float, cfg: XdkFusionConfig, imu_only: bool = False) -> np.ndarray:
    tg = xdk.t + offset
    speed = np.interp(tg, gnss.t, gnss.speed)
    rate = np.median(np.diff(xdk.t))
    gyro_norm = _moving_mean(np.linalg.norm(xdk.gyro, axis=1), max(1, round(0.5 / rate)))
    inside = (tg >= gnss.t[0]) & (tg <= gnss.t[-1])
    if imu_only:  # the sensor is known not to move (assume_stationary): only the IMU decides when it is quiet
        width = max(1, round(1.0 / rate))
        norm = np.linalg.norm(xdk.acc, axis=1)
        var = _moving_mean(norm**2, width) - _moving_mean(norm, width) ** 2
        quiet = np.sqrt(np.maximum(var, 0.0)) <= cfg.static_acc_std_mps2
        raw = inside & (gyro_norm <= cfg.zupt_gyro_rps) & quiet
    elif gnss.has_vel.mean() >= 0.5:  # Doppler speed: precise enough for the strict limit
        raw = inside & (speed <= cfg.static_speed_mps) & (gyro_norm <= cfg.zupt_gyro_rps)
    else:  # speed from positions is noisy: also require a quiet accelerometer
        width = max(1, round(1.0 / rate))
        norm = np.linalg.norm(xdk.acc, axis=1)
        var = _moving_mean(norm**2, width) - _moving_mean(norm, width) ** 2
        quiet = np.sqrt(np.maximum(var, 0.0)) <= cfg.static_acc_std_mps2
        raw = inside & (speed <= cfg.static_speed_unreliable_mps) & (gyro_norm <= cfg.zupt_gyro_rps) & quiet
    # Doppler speed lags the real start of motion; zero-velocity updates during the first moments of a launch
    # would be read as tilt and bias. Only trust samples that stay static for the guard time on both sides.
    width = max(1, 2 * round(cfg.zupt_guard_s / rate) + 1)
    return np.convolve(raw.astype(float), np.ones(width), "same") >= width - 0.5


def estimate_mounting(xdk: XdkData, gnss: _GnssTrack, offset: float, cfg: XdkFusionConfig) -> tuple[np.ndarray, np.ndarray, float | None]:
    """(up_b, fwd_b, fit R2): sensor-frame vertical and travel axes."""
    up_b = up_axis(xdk.acc)
    if cfg.forward_axis is not None:
        fwd = np.asarray(cfg.forward_axis, dtype=float)
        if fwd.shape != (3,) or np.linalg.norm(fwd) < 1e-9:
            raise SystemExit("forward_axis must be three non-zero numbers.")
        fwd = fwd - up_b * float(fwd @ up_b)
        return up_b, fwd / np.linalg.norm(fwd), None
    rate = 20.0
    t_b, acc_b = resample_mean(xdk.t, xdk.acc, rate)
    tg = t_b + offset
    mask = (tg >= gnss.t[0]) & (tg <= gnss.t[-1])
    tg, acc_b = tg[mask], acc_b[mask]
    speed = np.interp(tg, gnss.t, gnss.speed)
    slope = slope_sine(np.interp(tg, gnss.t, gnss.u), speed, 1.0 / rate, 3.0)
    axis, r2 = estimate_forward_axis(acc_b, speed, slope, 1.0 / rate, 1.0)
    axis = axis - up_b * float(axis @ up_b)
    norm = float(np.linalg.norm(axis))
    if norm < 1e-6:
        raise SystemExit("Could not estimate the XDK forward axis (too little motion); pass --forward-axis.")
    return up_b, axis / norm, r2


def run_xdk_fusion(
    points: Sequence[Any],
    xdk: XdkData,
    source: str,
    cfg: XdkFusionConfig,
    offset_s: float,
    outages: Sequence[tuple[float, float]] = (),
    use_imu: bool = True,
    smooth: bool = False,
) -> XdkFusionResult:
    """Fuse `points` (GNSS) with the XDK log; `offset_s` is the GNSS time at which the XDK clock reads 0.

    use_imu=False skips the XDK prediction model entirely (white-noise-acceleration constant-velocity
    filter on the same GNSS epochs), as a baseline to show what the sensor adds.

    smooth=True follows the forward pass with a Rauch-Tung-Striebel backward pass over the error state
    (checkpoints at every update and output sample), so each output also uses the later measurements.
    """
    gnss = _GnssTrack(points, cfg, source)
    g = local_gravity(gnss.lat0, gnss.h0)
    grav = np.array([0.0, 0.0, -g])

    tg = xdk.t + offset_s
    valid = np.flatnonzero((tg >= gnss.t[0]) & (tg <= gnss.t[-1]))
    if len(valid) < 100:
        raise SystemExit("XDK and GNSS time ranges barely overlap; check the time offset.")
    i0, i1 = int(valid[0]), int(valid[-1])
    t_imu = tg[i0:i1 + 1]
    acc = xdk.acc[i0:i1 + 1]
    gyro = xdk.gyro[i0:i1 + 1]
    n = len(t_imu)

    moving_in_overlap = (gnss.t >= t_imu[0]) & (gnss.t <= t_imu[-1]) & (gnss.speed >= cfg.nhc_min_speed_mps)
    stationary = cfg.assume_stationary if cfg.assume_stationary is not None else not bool(moving_in_overlap.any())
    static = _static_mask(xdk, gnss, offset_s, cfg, imu_only=stationary)[i0:i1 + 1]
    if stationary:
        # nothing moves: there is no travel direction to find; any horizontal sensor axis serves as 'forward'
        up_b = up_axis(xdk.acc)
        helper = np.eye(3)[int(np.argmin(np.abs(up_b)))]
        fwd_b = helper - up_b * float(helper @ up_b)
        fwd_b /= np.linalg.norm(fwd_b)
        axis_r2 = None
    else:
        up_b, fwd_b, axis_r2 = estimate_mounting(xdk, gnss, offset_s, cfg)
    left_b = np.cross(up_b, fwd_b)
    r_vb = np.vstack([fwd_b, left_b, up_b])  # body -> vehicle (forward, left, up)
    nhc_on = cfg.nhc and (axis_r2 is None or axis_r2 >= cfg.nhc_min_axis_r2)

    # --- initial biases and attitude ---
    bg0 = gyro[static].mean(axis=0) if static.sum() > 200 else np.zeros(3)
    bg_sigma = cfg.initial_gyro_bias_sigma_rps if static.sum() <= 200 else cfg.initial_gyro_bias_sigma_rps / 3.0
    window = acc[: max(10, min(n, int(10.0 / max(np.median(np.diff(t_imu)), 1e-3))))]
    f_mean = window[static[: len(window)]].mean(axis=0) if static[: len(window)].sum() > 50 else window.mean(axis=0)
    up0 = f_mean / np.linalg.norm(f_mean)
    rest_norm = float(np.linalg.norm(acc[static].mean(axis=0))) if static.sum() > 200 else float(np.linalg.norm(f_mean))
    # The XDK reads ~3 % more than 1 g at rest. That is mostly a sensitivity error (it scales every axis, so it
    # also inflates the speed gained in each acceleration), so it is a filter state that starts at the rest value.
    ks = rest_norm / g - 1.0 if cfg.accel_scale_from_gravity else 0.0
    ba0 = np.zeros(3)
    up_b_run = up0
    fwd0 = fwd_b - up_b_run * float(fwd_b @ up_b_run)
    fwd0 /= np.linalg.norm(fwd0)

    t_start = float(t_imu[0])
    dpsi = 0.0
    if stationary:
        heading0 = 0.0  # arbitrary: the position does not depend on it when nothing moves
    else:
        moving = np.flatnonzero((gnss.t >= t_start) & (gnss.speed >= cfg.nhc_min_speed_mps))
        if len(moving) == 0:
            raise SystemExit("The vehicle never moves faster than the NHC speed in the overlap; nothing to align the heading with.")
        t_move = float(gnss.t[moving[0]])
        j_move = int(np.searchsorted(t_imu, t_move))
        if j_move > 0:  # heading at the first sample = course when it starts moving, minus the gyro yaw since
            yaw_rate = -((gyro[:j_move] - bg0) @ up_b_run)
            dpsi = float(np.sum(yaw_rate[:-1] * np.diff(t_imu[: j_move])))
        course = math.atan2(*gnss.velocity_at(t_move)[:2])
        heading0 = course - dpsi
    r = level_rotation(up_b_run, fwd0, heading0)

    v = gnss.velocity_at(t_start)
    p = np.array([gnss.interp(gnss.e, t_start), gnss.interp(gnss.n, t_start), gnss.interp(gnss.u, t_start)])
    ba, bg = ba0.copy(), bg0.copy()
    sigma0 = gnss.interp(gnss.sigma, t_start)
    tilt = math.radians(cfg.initial_tilt_sigma_deg)
    yaw_s = math.radians(cfg.initial_yaw_sigma_deg if dpsi == 0.0 else cfg.initial_yaw_sigma_deg * 2.0)
    cov = np.diag(np.r_[
        np.full(2, sigma0**2), (cfg.vertical_sigma_factor * sigma0) ** 2,
        np.full(3, cfg.initial_velocity_sigma_mps**2),
        [tilt**2, tilt**2, yaw_s**2],
        np.full(3, cfg.initial_accel_bias_sigma_mps2**2),
        np.full(3, bg_sigma**2),
        [cfg.initial_scale_sigma**2],
    ])

    # --- GNSS epochs: (imu sample index at/after the epoch) ---
    epoch_idx: list[int] = []
    last = -1e18
    for k, tk in enumerate(gnss.t):
        if tk < t_start or tk > t_imu[-1] or tk - last < cfg.gnss_update_period_s:
            continue
        epoch_idx.append(k)
        last = tk
    epoch_sample = np.searchsorted(t_imu, gnss.t[epoch_idx])
    epoch_at: dict[int, int] = {}
    for k, s in zip(epoch_idx, epoch_sample):
        epoch_at.setdefault(int(min(s, n - 1)), k)

    out_stride = max(1, round(1.0 / (cfg.output_rate_hz * max(float(np.median(np.diff(t_imu))), 1e-3))))
    nhc_stride = max(1, round(cfg.nhc_period_s / max(float(np.median(np.diff(t_imu))), 1e-3)))
    q_a = cfg.accel_noise_mps2_sqrt_hz**2
    q_g = cfg.gyro_noise_rps_sqrt_hz**2
    q_ba = cfg.accel_bias_walk**2
    q_bg = cfg.gyro_bias_walk**2
    q_k = cfg.scale_walk**2
    gate, huber = cfg.outlier_gate_sigma, min(cfg.huber_sigma, cfg.outlier_gate_sigma)
    h_pos = np.zeros((3, NSTATE))
    h_pos[:, 0:3] = np.eye(3)
    h_vel = np.zeros((3, NSTATE))
    h_vel[:, 3:6] = np.eye(3)
    h_bg = np.zeros((3, NSTATE))
    h_bg[:, 12:15] = np.eye(3)
    stride_start = 0
    phi = EYEN.copy()
    phi[0:3, 3:6] = 0.0
    zero_state = np.zeros(NSTATE)

    step_cov_minus: np.ndarray | None = None  # covariance before the first update of this step (smoother)
    step_inj = np.zeros(NSTATE)  # total correction injected in this step (smoother)

    def inject(dx: np.ndarray) -> None:
        nonlocal p, v, r, ba, bg, ks
        ks = ks + dx[15]
        p = p + dx[0:3]
        v = v + dx[3:6]
        r = exp_so3(dx[6:9]) @ r
        ba = ba + dx[9:12]
        bg = bg + dx[12:15]

    def correct(z: np.ndarray, h: np.ndarray, rm: np.ndarray, gate_on: bool = True, gate_value: float = gate):
        nonlocal cov, step_cov_minus
        if smooth and step_cov_minus is None:
            step_cov_minus = cov.copy()
        dx, new_cov, status, d = _gnss_update(zero_state, cov, z, h, rm, gate_value, min(huber, gate_value), gate_enabled=gate_on)
        if status != STATUS_REJECTED:
            cov = new_cov
            inject(dx)
            if smooth:
                step_inj[:] += dx
        return status, d

    # --- smoother checkpoints: one per output sample and per step that applied an update ---
    cp_minus: list[np.ndarray] = []
    cp_plus: list[np.ndarray] = []
    cp_phi: list[np.ndarray] = []
    cp_inj: list[np.ndarray] = []
    cp_state: list[tuple] = []
    cp_is_output: list[bool] = []
    phi_acc = EYEN.copy()

    def record_checkpoint(is_output: bool) -> None:
        nonlocal phi_acc, step_cov_minus
        cp_minus.append(cov.copy() if step_cov_minus is None else step_cov_minus)
        cp_plus.append(cov.copy())
        cp_phi.append(phi_acc)
        cp_inj.append(step_inj.copy())
        cp_state.append((p.copy(), v.copy(), r.copy(), ba.copy(), bg.copy(), ks))
        cp_is_output.append(is_output)
        phi_acc = EYEN.copy()
        step_cov_minus = None
        step_inj[:] = 0.0

    out_rows: list[tuple] = []
    row_status: list[str] = []
    row_d: list[float] = []
    row_zupt: list[bool] = []
    pending_status, pending_d, pending_zupt = STATUS_NONE, 0.0, False
    gnss_log: list[dict[str, object]] = []
    reject_start: float | None = None
    reject_count = 0
    nhc_updates = zupt_updates = 0
    renorm = 0

    def snapshot(i: int) -> tuple:
        heading, pitch, roll = attitude_angles(r, fwd_b, up_b)
        return (t_imu[i], p.copy(), v.copy(), heading, pitch, roll, ba.copy(), np.degrees(bg), cov[0, 0], cov[1, 1])

    out_rows.append(snapshot(0))
    row_status.append(STATUS_NONE)
    row_d.append(0.0)
    row_zupt.append(False)
    if smooth:
        record_checkpoint(True)

    for i in range(1, n):
        dt = float(t_imu[i] - t_imu[i - 1])
        if dt <= 0.0:
            continue
        if use_imu and dt <= cfg.max_imu_gap_s:
            f = (acc[i] - ba) / (1.0 + ks)
            w = gyro[i] - bg
            a_n = r @ f + grav
            p = p + v * dt + 0.5 * a_n * dt * dt
            v = v + a_n * dt
            f_n = r @ f
            phi[3:6, 6:9] = -skew(f_n) * dt
            phi[3:6, 9:12] = -r * (dt / (1.0 + ks))
            phi[3:6, 15] = -f_n * (dt / (1.0 + ks))
            phi[6:9, 12:15] = -r * dt
            phi[0:3, 3:6] = np.eye(3) * dt
            r = r @ exp_so3(w * dt)
            qd = np.zeros(NSTATE)
            qd[3:6] = q_a * dt
            qd[6:9] = q_g * dt
            qd[9:12] = q_ba * dt
            qd[12:15] = q_bg * dt
            qd[15] = q_k * dt
            cov = phi @ cov @ phi.T
            cov[np.diag_indices(NSTATE)] += qd
            cov = 0.5 * (cov + cov.T)
            if smooth:
                phi_acc = phi @ phi_acc
            renorm += 1
            if renorm % 500 == 0:
                r = orthonormalise(r)
        else:
            # no usable XDK data in this step (or baseline run): constant velocity with acceleration noise
            p = p + v * dt
            step = EYEN.copy()
            step[0:3, 3:6] = np.eye(3) * dt
            cov = step @ cov @ step.T
            cov[3:6, 3:6] += np.eye(3) * dt  # 1 (m/s^2)^2/Hz of unmodelled acceleration
            cov[0:3, 0:3] += np.eye(3) * (dt**3 / 3.0)
            cov = 0.5 * (cov + cov.T)
            if smooth:
                phi_acc = step @ phi_acc

        tk = float(t_imu[i])
        if i in epoch_at:
            k = epoch_at[i]
            if any(a <= tk <= b for a, b in outages):
                status, d = STATUS_OUTAGE, 0.0
            else:
                sigma = float(gnss.sigma[k])
                r_pos = np.diag([sigma**2, sigma**2, (cfg.vertical_sigma_factor * sigma) ** 2])
                escape = reject_start is not None and reject_count >= 3 and tk - reject_start >= cfg.max_reject_duration_s
                if escape:  # lost track: let the next fix pull the position in instead of ignoring it
                    cov[0:3, 0:3] += np.eye(3) * (cfg.reacquire_sigma_scale * sigma) ** 2
                # horizontal and vertical are gated separately: the vertical GNSS error is the largest, and a vertical
                # outlier must not throw away a good horizontal fix
                status, d = correct(np.array([gnss.e[k], gnss.n[k]]) - p[0:2], h_pos[0:2], r_pos[0:2, 0:2], gate_on=not escape)
                if status != STATUS_REJECTED:
                    _, d_up = correct(np.array([gnss.u[k]]) - p[2:3], h_pos[2:3], r_pos[2:3, 2:3], gate_on=not escape)
                    d = max(d, d_up)
                if status == STATUS_REJECTED:
                    reject_count += 1
                    reject_start = tk if reject_start is None else reject_start
                else:
                    status = STATUS_REACQUIRED if escape else status
                    reject_start, reject_count = None, 0
                if cfg.use_doppler_velocity and gnss.has_vel[k]:
                    vel = gnss.vel[k]
                    vs = cfg.gnss_speed_sigma_mps
                    vu = vel[2] if math.isfinite(vel[2]) else v[2]
                    r_vel = np.diag([vs**2, vs**2, (1.5 * vs) ** 2 if math.isfinite(vel[2]) else 1.0])
                    correct(np.array([vel[0], vel[1], vu]) - v, h_vel, r_vel, gate_value=10.0)
            if _STATUS_RANK[status] > _STATUS_RANK[pending_status]:
                pending_status = status
            pending_d = max(pending_d, d)
            gnss_log.append({
                "time_s": tk, "status": status, "innovation_sigma": d, "sigma_m": float(gnss.sigma[k]),
                "east_m": float(gnss.e[k]), "north_m": float(gnss.n[k]),
                "filter_east_m": float(p[0]), "filter_north_m": float(p[1]),
                "velocity_error_mps": (
                    math.hypot(v[0] - gnss.vel[k, 0], v[1] - gnss.vel[k, 1]) if gnss.has_vel[k] else math.nan
                ),
            })
        if use_imu and i % nhc_stride == 0:
            window_start = stride_start
            stride_start = i
            speed = math.sqrt(float(v[0] ** 2 + v[1] ** 2))
            if cfg.zupt and static[i] and speed <= 2.0 * cfg.static_speed_mps + 0.3:
                correct(-v, h_vel, np.eye(3) * cfg.zupt_sigma_mps**2, gate_value=20.0)
                correct(gyro[window_start:i + 1].mean(axis=0) - bg, h_bg, np.eye(3) * cfg.zaru_sigma_rps**2, gate_value=20.0)
                zupt_updates += 1
                pending_zupt = True
            elif nhc_on and speed >= cfg.nhc_min_speed_mps:
                rbn = r_vb @ r.T  # ENU -> vehicle
                v_v = rbn @ v
                h = np.zeros((2, NSTATE))
                h[:, 3:6] = rbn[1:3]
                h[:, 6:9] = rbn[1:3] @ skew(v)
                rm = np.diag([cfg.nhc_sigma_lateral_mps**2, cfg.nhc_sigma_vertical_mps**2])
                correct(-v_v[1:3], h, rm, gate_value=6.0)
                nhc_updates += 1
        is_output = i % out_stride == 0 or i == n - 1
        if is_output:
            out_rows.append(snapshot(i))
            row_status.append(pending_status)
            row_d.append(pending_d)
            row_zupt.append(pending_zupt)
            pending_status, pending_d, pending_zupt = STATUS_NONE, 0.0, False
        if smooth and (is_output or step_cov_minus is not None or i in epoch_at):
            if i in epoch_at:
                gnss_log[-1]["checkpoint"] = len(cp_plus)
            record_checkpoint(is_output)

    smoothed_outage: list[float] = []
    if smooth and len(cp_plus) > 1:
        # Rauch-Tung-Striebel on the error state. Each checkpoint's nominal state already contains its own
        # injected correction, so the smoothed error of checkpoint k+1 relative to the *predicted* state is
        # (its smoothed error relative to the posterior) + (the correction that was injected there).
        m = len(cp_plus)
        smoothed: list[tuple[np.ndarray, np.ndarray]] = [(np.zeros(NSTATE), cp_plus[-1])] * m
        ds, ps = np.zeros(NSTATE), cp_plus[-1]
        for k in range(m - 2, -1, -1):
            pm = cp_minus[k + 1]
            gain = np.linalg.solve(pm + 1e-12 * EYEN, cp_phi[k + 1] @ cp_plus[k]).T
            ds = gain @ (ds + cp_inj[k + 1])
            ps = cp_plus[k] + gain @ (ps - pm) @ gain.T
            ps = 0.5 * (ps + ps.T)
            smoothed[k] = (ds, ps)
        output_checkpoints = [k for k in range(m) if cp_is_output[k]]
        if len(output_checkpoints) == len(out_rows):
            new_rows = []
            for row, k in zip(out_rows, output_checkpoints):
                ds_k, ps_k = smoothed[k]
                p_k, v_k, r_k, ba_k, bg_k, _ = cp_state[k]
                heading_s, pitch_s, roll_s = attitude_angles(exp_so3(ds_k[6:9]) @ r_k, fwd_b, up_b)
                new_rows.append((
                    row[0], p_k + ds_k[0:3], v_k + ds_k[3:6], heading_s, pitch_s, roll_s,
                    ba_k + ds_k[9:12], np.degrees(bg_k + ds_k[12:15]), ps_k[0, 0], ps_k[1, 1],
                ))
            out_rows = new_rows
        for entry in gnss_log:
            k = entry.get("checkpoint")
            if k is not None and entry["status"] == STATUS_OUTAGE:
                ds_k, _ = smoothed[int(k)]
                p_k = cp_state[int(k)][0] + ds_k[0:3]
                smoothed_outage.append(math.hypot(p_k[0] - entry["east_m"], p_k[1] - entry["north_m"]))

    t_arr = np.array([row[0] for row in out_rows])
    pos = np.array([row[1] for row in out_rows])
    vel_arr = np.array([row[2] for row in out_rows])
    t0_abs = gnss.t0
    info: dict[str, object] = {
        "imu_samples": n,
        "xdk_offset_s": offset_s,
        "forward_axis": ",".join(f"{x:.4f}" for x in fwd_b),
        "up_axis": ",".join(f"{x:.4f}" for x in up_b),
        "forward_axis_r2": "" if axis_r2 is None else f"{axis_r2:.4f}",
        "gravity_mps2": g,
        "initial_heading_deg": math.degrees(heading0) % 360.0,
        "initial_accel_bias_mps2": ",".join(f"{x:.4f}" for x in ba0),
        "initial_gyro_bias_dps": ",".join(f"{x:.4f}" for x in np.degrees(bg0)),
        "initial_accel_scale_error": ks,
        "static_samples": int(static.sum()),
        "gnss_epochs": len(gnss_log),
        "gnss_used": sum(1 for e in gnss_log if e["status"] in (STATUS_USED, STATUS_REACQUIRED)),
        "gnss_downweighted": sum(1 for e in gnss_log if e["status"] == STATUS_DOWNWEIGHTED),
        "gnss_rejected": sum(1 for e in gnss_log if e["status"] == STATUS_REJECTED),
        "gnss_outage": sum(1 for e in gnss_log if e["status"] == STATUS_OUTAGE),
        "zupt_updates": zupt_updates,
        "nhc_updates": nhc_updates,
        "nhc_active": bool(nhc_on),
        "final_accel_bias_mps2": ",".join(f"{x:.4f}" for x in ba),
        "final_accel_scale_error": ks,
        "final_gyro_bias_dps": ",".join(f"{x:.4f}" for x in np.degrees(bg)),
        "uses_imu": bool(use_imu),
    }
    if outages:
        # no update was applied at an outage epoch, so the filter position there is pure prediction
        errors = [
            math.hypot(e["filter_east_m"] - e["east_m"], e["filter_north_m"] - e["north_m"])
            for e in gnss_log if e["status"] == STATUS_OUTAGE
        ]
        if errors:
            arr = np.array(errors)
            info["outage_rmse_m"] = float(np.sqrt(np.mean(arr**2)))
            info["outage_max_m"] = float(arr.max())
            info["outage_points"] = len(errors)
            vel_err = np.array([e["velocity_error_mps"] for e in gnss_log if e["status"] == STATUS_OUTAGE])
            if np.isfinite(vel_err).any():
                info["outage_velocity_rmse_mps"] = float(np.sqrt(np.nanmean(vel_err**2)))
            info["outage_ref_sigma_m"] = float(np.median([e["sigma_m"] for e in gnss_log if e["status"] == STATUS_OUTAGE]))
            if smoothed_outage:
                sm = np.array(smoothed_outage)
                info["outage_smoothed_rmse_m"] = float(np.sqrt(np.mean(sm**2)))
                info["outage_smoothed_max_m"] = float(sm.max())
    info["smoothed"] = bool(smooth)
    info["stationary"] = bool(stationary)

    return XdkFusionResult(
        times=[t0_abs + timedelta(seconds=float(x)) for x in t_arr],
        east=pos[:, 0], north=pos[:, 1], up=pos[:, 2],
        ve=vel_arr[:, 0], vn=vel_arr[:, 1], vu=vel_arr[:, 2],
        heading_deg=np.array([row[3] for row in out_rows]),
        pitch_deg=np.array([row[4] for row in out_rows]),
        roll_deg=np.array([row[5] for row in out_rows]),
        accel_bias=np.array([row[6] for row in out_rows]),
        gyro_bias=np.array([row[7] for row in out_rows]),
        sigma_e=np.sqrt(np.maximum(0.0, [row[8] for row in out_rows])),
        sigma_n=np.sqrt(np.maximum(0.0, [row[9] for row in out_rows])),
        gnss_status=row_status,
        innovation=np.array(row_d),
        zupt=np.array(row_zupt),
        gnss_log=gnss_log,
        info=info,
    )


def result_rows(result: XdkFusionResult, source: str, ref_lat: float, ref_lon: float, ref_height: float) -> list[dict[str, object]]:
    rows = []
    for i, time in enumerate(result.times):
        lat, lon, _ = enu_to_llh(float(result.east[i]), float(result.north[i]), ref_lat, ref_lon, ref_height)
        status = result.gnss_status[i]
        rows.append({
            "time": time.isoformat(),
            "source": source,
            "lat": f"{lat:.10f}",
            "lon": f"{lon:.10f}",
            "height_m": f"{ref_height + result.up[i]:.3f}",
            "east_m": f"{result.east[i]:.3f}",
            "north_m": f"{result.north[i]:.3f}",
            "ve_mps": f"{result.ve[i]:.4f}",
            "vn_mps": f"{result.vn[i]:.4f}",
            "vu_mps": f"{result.vu[i]:.4f}",
            "heading_deg": f"{result.heading_deg[i]:.2f}",
            "pitch_deg": f"{result.pitch_deg[i]:.2f}",
            "roll_deg": f"{result.roll_deg[i]:.2f}",
            "gnss_used": "1" if status in (STATUS_USED, STATUS_DOWNWEIGHTED, STATUS_REACQUIRED) else "0",
            "zupt": "1" if result.zupt[i] else "0",
            "sigma_e_m": f"{result.sigma_e[i]:.4f}",
            "sigma_n_m": f"{result.sigma_n[i]:.4f}",
            "accel_bias_x": f"{result.accel_bias[i, 0]:.5f}",
            "accel_bias_y": f"{result.accel_bias[i, 1]:.5f}",
            "accel_bias_z": f"{result.accel_bias[i, 2]:.5f}",
            "gyro_bias_x_dps": f"{result.gyro_bias[i, 0]:.5f}",
            "gyro_bias_y_dps": f"{result.gyro_bias[i, 1]:.5f}",
            "gyro_bias_z_dps": f"{result.gyro_bias[i, 2]:.5f}",
            "gnss_status": status,
            "innovation_sigma": f"{result.innovation[i]:.2f}",
        })
    return rows


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise SystemExit(f"No rows to write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_config(args: argparse.Namespace) -> XdkFusionConfig:
    overrides: dict[str, Any] = {
        "gnss_sigma_m": args.position_sigma_m,
        "outlier_gate_sigma": args.outlier_gate_sigma,
        "nhc": args.nhc,
        "zupt": args.zupt,
        "assume_stationary": args.stationary,
    }
    if args.forward_axis:
        try:
            overrides["forward_axis"] = [float(part) for part in args.forward_axis.replace(";", ",").split(",")]
        except ValueError as exc:
            raise SystemExit("--forward-axis must be x,y,z numbers") from exc
    known = {item.name for item in fields(XdkFusionConfig)}
    for item in args.fusion_set:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"--fusion-set needs KEY=VALUE, got {item!r}")
        try:
            overrides[key.strip()] = json.loads(value)
        except json.JSONDecodeError:
            overrides[key.strip()] = value
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise SystemExit(f"Unknown fusion parameter(s): {', '.join(unknown)}. Known: {', '.join(sorted(known))}")
    return XdkFusionConfig.load(args.fusion_config, overrides)


def main() -> int:
    parser = argparse.ArgumentParser(description="GNSS + XDK (accelerometer + gyroscope) error-state Kalman fusion.")
    parser.add_argument("recording", help="GNSS recording output directory or name inside out/")
    parser.add_argument("--xdk", type=Path, help="XDK CSV log of the same ride (default: the XDK log linked to the recording, see attach_xdk.py)")
    parser.add_argument("--source", choices=list(GNSS_SOURCES), default="bestnav")
    parser.add_argument("--time-offset-s", type=float, help="GNSS time (s after the first GNSS point) at which the XDK clock reads 0; overrides --sync")
    parser.add_argument("--sync", choices=["auto", "button", "yaw"], default="auto", help="How to align the XDK clock: SYNC button presses (needs --gnss-sync and --xdk-sync), the yaw-rate correlation, or auto (button when both SYNC files are given)")
    parser.add_argument("--gnss-sync", type=Path, help="GNSS logger SYNCnnnnn.CSV (button presses)")
    parser.add_argument("--xdk-sync", type=Path, help="XDK SYNC_nnn.CSV (button presses)")
    parser.add_argument("--smooth", action="store_true", help="RTS backward smoothing after the forward pass")
    parser.add_argument("--stationary", action=argparse.BooleanOptionalAction, default=None, help="The sensor does not move (default: detected from the GNSS speed)")
    parser.add_argument("--fusion-config", type=Path, help=f"JSON parameters (default: {DEFAULT_CONFIG_PATH.relative_to(ROOT)})")
    parser.add_argument("--fusion-set", action="append", default=[], metavar="KEY=VALUE", help="Override a parameter, e.g. --fusion-set nhc_sigma_lateral_mps=0.2 (repeatable)")
    parser.add_argument("--position-sigma-m", type=float, help="GNSS position sigma for all points")
    parser.add_argument("--outlier-gate-sigma", type=float)
    parser.add_argument("--forward-axis", help="XDK travel axis x,y,z (default: estimated from GNSS)")
    parser.add_argument("--nhc", action=argparse.BooleanOptionalAction, default=None, help="Non-holonomic constraint (default on)")
    parser.add_argument("--zupt", action=argparse.BooleanOptionalAction, default=None, help="Zero-velocity updates (default on)")
    parser.add_argument("--gnss-outage", action="append", default=[], metavar="START:END", help="Withhold GNSS between START and END seconds after the first fused sample and report the drift against it; repeatable")
    parser.add_argument("--gnss-only", action="store_true", help="Baseline: ignore the XDK (constant-velocity GNSS filter)")
    parser.add_argument("--output", type=Path, help="Output CSV (default: out/<recording>/imu/kalman_<source>_<xdk>.csv)")
    args = parser.parse_args()

    session_dir = resolve_session_dir(args.recording)
    imu_dir = output_subdir(session_dir, "imu")
    points = load_gnss(source_csv(session_dir, args.source))
    link = imu_links.resolve_xdk(session_dir, args.xdk.name if args.xdk else None)
    if args.xdk is not None and not args.xdk.is_file() and link is not None:
        args.xdk = link.xdk
    if args.xdk is None:
        if link is None:
            raise SystemExit("No XDK log: give --xdk or attach one to the recording with scripts/attach_xdk.py")
        args.xdk = link.xdk
        print(f"Using the {'default ' if link.is_default else ''}XDK log linked to this recording: {link.name}")
    if link is not None and args.xdk.resolve() == link.xdk.resolve():
        args.gnss_sync = args.gnss_sync or link.gnss_sync
        args.xdk_sync = args.xdk_sync or link.xdk_sync
    xdk = load_xdk(args.xdk)
    use_button = args.sync == "button" or (args.sync == "auto" and args.gnss_sync and args.xdk_sync)
    if args.time_offset_s is not None:
        offset, score_text = args.time_offset_s, "manual"
    elif use_button:
        if not (args.gnss_sync and args.xdk_sync):
            raise SystemExit("--sync button needs --gnss-sync and --xdk-sync")
        from sync_button import compute_button_sync, describe
        button = compute_button_sync(args.gnss_sync, args.xdk_sync, find_original_bin(session_dir))
        offset = button.offset_s(points[0].time)
        score_text = f"SYNC button, {len(button.pairs)} press pairs, spread {button.spread_ms:.0f} ms, confidence {button.confidence}"
        print(describe(button))
    else:
        found = find_offset(xdk, points)
        offset, score_text = found.offset_s, f"yaw-rate correlation {found.correlation:.3f} (next best {found.second_correlation:.3f}, confidence {found.confidence})"
        if found.confidence == "low":
            print("Warning: the XDK log does not clearly match this GNSS recording; check the pairing or pass --time-offset-s.")
    cfg = build_config(args)
    outages: list[tuple[float, float]] = []
    if args.gnss_outage:
        first = max(0.0, offset)
        outages = [(first + a, first + b) for a, b in parse_outages(args.gnss_outage)]
    result = run_xdk_fusion(points, xdk, args.source, cfg, offset, outages, use_imu=not args.gnss_only, smooth=args.smooth)

    label = args.source.replace("_ppk", "")
    output = args.output or imu_dir / f"kalman_{label}_{xdk.name}.csv"
    ref = points[0]
    write_rows(output, result_rows(result, args.source, ref.lat, ref.lon, ref.height))
    log_rows = [{
        "time": (ref.time + timedelta(seconds=float(e["time_s"]))).isoformat(),
        "status": e["status"],
        "innovation_sigma": f"{float(e['innovation_sigma']):.2f}",
        "sigma_m": f"{float(e['sigma_m']):.3f}",
        "east_m": f"{float(e['east_m']):.3f}",
        "north_m": f"{float(e['north_m']):.3f}",
    } for e in result.gnss_log]
    write_rows(output.with_name(f"fusion_gnss_{output.stem}.csv"), log_rows)
    report = output.with_name(f"{output.stem}_report.txt")
    report.write_text("\n".join([
        f"recording={session_dir}",
        f"xdk_csv={args.xdk}",
        f"gnss_source={args.source}",
        f"time_offset_s={offset:.3f}",
        f"alignment={score_text}",
        f"kalman_csv={output}",
        *[f"fusion_{key}={value}" for key, value in result.info.items()],
        *[f"fusion_config_{item.name}={getattr(cfg, item.name)}" for item in fields(cfg)],
    ]), encoding="utf-8")

    info = result.info
    print(f"Wrote Kalman trajectory: {output}")
    print(f"XDK offset: {offset:.2f} s  [{score_text}]")
    print(f"GNSS epochs: {info['gnss_epochs']} (used {info['gnss_used']}, downweighted {info['gnss_downweighted']}, rejected {info['gnss_rejected']}, outage {info['gnss_outage']})")
    print(f"Forward axis {info['forward_axis']} (R2 {info['forward_axis_r2'] or 'manual'}); ZUPT {info['zupt_updates']}, NHC {info['nhc_updates']} updates")
    print(f"Final biases: accel {info['final_accel_bias_mps2']} m/s^2 (scale error {100 * info['final_accel_scale_error']:.2f} %), gyro {info['final_gyro_bias_dps']} deg/s")
    if "outage_rmse_m" in info:
        print(f"GNSS outage error: RMSE {info['outage_rmse_m']:.2f} m, max {info['outage_max_m']:.2f} m over {info['outage_points']} withheld points (reference sigma ~{info['outage_ref_sigma_m']:.1f} m)")
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
