#!/usr/bin/env python3
"""The GNSS + XDK fusion methods that fusion_compare.py runs side by side.

Every 'ekf_*' method is the 16-state error-state Kalman filter of gnss_xdk_fusion.py: it integrates the XDK
gyroscope (attitude) and accelerometer (specific force) and corrects with the chosen GNSS curve. They differ
in which constraints are on, in smoothing and in how much the IMU is trusted. 'gnss_only' shows what the XDK
adds; 'accel2d_legacy' is the older accelerometer-only 2-D filter (gnss_imu_fusion.py) for contrast.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gnss_imu_fusion import FusionConfig, run_fusion
from gnss_xdk_fusion import XdkFusionConfig, run_xdk_fusion
from imu_kalman import ImuSample
from xdk_imu import XdkData


@dataclass(frozen=True)
class MethodSpec:
    key: str
    label: str
    description: str
    overrides: dict[str, Any] = field(default_factory=dict)  # XdkFusionConfig fields
    scale: dict[str, float] = field(default_factory=dict)  # XdkFusionConfig fields multiplied by these factors
    use_imu: bool = True
    smooth: bool = False
    legacy: bool = False


METHODS: dict[str, MethodSpec] = {m.key: m for m in [
    MethodSpec("gnss_only", "GNSS only", "Konstanta ātruma Kalmana filtrs tikai uz GNSS epohām. XDK netiek izmantots: atskaites punkts.", use_imu=False),
    MethodSpec("ekf_full", "EKF full", "Akselerometrs + žiroskops, GNSS pozīcija un Doppler, ZUPT+ZARU stāvot, nesānslīdes ierobežojums (NHC) braucot."),
    MethodSpec("ekf_rts", "EKF full + RTS", "Kā ekf_full, pēc tam RTS gājiens atpakaļ, lai katrs punkts izmantotu arī vēlākos mērījumus.", smooth=True),
    MethodSpec("ekf_zupt_only", "EKF, ZUPT only", "Kā ekf_full bez NHC (bez sānslīdes ierobežojuma).", overrides={"nhc": False}),
    MethodSpec("ekf_nhc_only", "EKF, NHC only", "Kā ekf_full bez nulles ātruma (ZUPT) un nulles griešanās (ZARU) korekcijām.", overrides={"zupt": False}),
    MethodSpec("ekf_nhc_forced", "EKF, NHC forced", "Kā ekf_full, bet NHC paliek ieslēgts arī tad, ja kustības ass novērtējums ir vājš (XDK varētu nebūt stingri nostiprināts).", overrides={"nhc_min_axis_r2": 0.0}),
    MethodSpec("ekf_free", "EKF, no constraints", "Strapdown INS, ko labo tikai GNSS: bez ZUPT, ZARU un NHC.", overrides={"zupt": False, "nhc": False}),
    MethodSpec("ekf_loose_imu", "EKF, IMU trusted less", "Kā ekf_full ar 4x lielāku akselerometra un žiroskopa troksni, tātad GNSS dominē.",
               scale={"accel_noise_mps2_sqrt_hz": 4.0, "gyro_noise_rps_sqrt_hz": 4.0}),
    MethodSpec("accel2d_legacy", "Accelerometer-only 2-D", "Vecais filtrs: tikai akselerometrs (bez žiroskopa), 2D, uz priekšu virziens no GNSS, ar savu RTS.", legacy=True),
]}


@dataclass
class FusedTrack:
    method: str
    curve: str
    times: np.ndarray  # epoch seconds
    east: np.ndarray  # metres in the ENU frame of the curve's first point
    north: np.ndarray
    up: np.ndarray
    ve: np.ndarray
    vn: np.ndarray
    vu: np.ndarray
    sigma_e: np.ndarray
    sigma_n: np.ndarray
    heading_deg: np.ndarray | None
    pitch_deg: np.ndarray | None
    roll_deg: np.ndarray | None
    gnss_status: list[str]
    zupt: np.ndarray
    ref: tuple[float, float, float]  # lat, lon, height of the ENU origin
    info: dict[str, Any]
    gnss_log: list[dict[str, Any]]


def build_config(spec: MethodSpec, base: XdkFusionConfig) -> XdkFusionConfig:
    values = {key: value for key, value in vars(base).items()}
    values.update(spec.overrides)
    for key, factor in spec.scale.items():
        values[key] = values[key] * factor
    return XdkFusionConfig(**values)


def _epoch(times: Sequence[datetime]) -> np.ndarray:
    return np.array([t.timestamp() for t in times])


def _run_legacy(points: Sequence[Any], xdk: XdkData, curve: str, base: XdkFusionConfig, offset_s: float,
                outages: Sequence[tuple[float, float]]) -> FusedTrack:
    t0 = points[0].time
    samples = [
        ImuSample(float(t), float(a[0]), float(a[1]), float(a[2]), t0 + timedelta(seconds=float(offset_s + t)))
        for t, a in zip(xdk.t, xdk.acc)
    ]
    cfg = FusionConfig.load(None, {
        "gnss_sigma_m": base.gnss_sigma_m,
        "gnss_update_period_s": base.gnss_update_period_s,
        "static_speed_mps": base.static_speed_mps,
    })
    first = max(0.0, offset_s + float(xdk.t[0]))  # outages are counted from the first IMU/GNSS overlap sample
    legacy_outages = [(a - first, b - first) for a, b in outages if b > first]
    result = run_fusion(points, samples, curve, cfg, 0.0, legacy_outages)
    n = len(result.times)
    zeros = np.zeros(n)
    info = dict(result.info)
    info["engine"] = "gnss_imu_fusion"
    # the legacy filter counts its GNSS-log times from the first IMU/GNSS overlap sample
    info["gnss_log_epoch0_utc"] = max(points[0].time.timestamp(), points[0].time.timestamp() + offset_s + float(xdk.t[0]))
    return FusedTrack(
        "accel2d_legacy", curve, _epoch(result.times), result.east, result.north,
        np.asarray(result.height) - points[0].height, result.ve, result.vn, zeros,
        result.sigma_e, result.sigma_n, None, None, None, list(result.gnss_status), np.asarray(result.zupt),
        (points[0].lat, points[0].lon, points[0].height), info, list(result.gnss_log),
    )


def run_method(
    spec: MethodSpec,
    points: Sequence[Any],
    xdk: XdkData,
    curve: str,
    base: XdkFusionConfig,
    offset_s: float,
    outages: Sequence[tuple[float, float]] = (),
) -> FusedTrack:
    if spec.legacy:
        return _run_legacy(points, xdk, curve, base, offset_s, outages)
    cfg = build_config(spec, base)
    result = run_xdk_fusion(points, xdk, curve, cfg, offset_s, outages, use_imu=spec.use_imu, smooth=spec.smooth)
    result.info["gnss_log_epoch0_utc"] = points[0].time.timestamp()
    return FusedTrack(
        spec.key, curve, _epoch(result.times), result.east, result.north, result.up,
        result.ve, result.vn, result.vu, result.sigma_e, result.sigma_n,
        result.heading_deg, result.pitch_deg, result.roll_deg, list(result.gnss_status), np.asarray(result.zupt),
        (points[0].lat, points[0].lon, points[0].height), dict(result.info), list(result.gnss_log),
    )
