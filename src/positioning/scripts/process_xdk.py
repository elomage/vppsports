#!/usr/bin/env python3
"""Process one XDK log on its own: clean it, check its quality, and estimate what it can say about the sensor.

Usage:
  python scripts/process_xdk.py ../../../our_data/sinhron_test_2026_11_02/xdk/LOG_005.CSV [--out-dir DIR]

Writes <out-dir>/<log>_processed.csv (de-duplicated, SI units, one row per new sample) and
<log>_report.json, and prints a summary:

* sample rate, gaps, repeated or reset timestamps and stale rows that were dropped
* gravity (should be ~9.8 m/s2) and the sensor 'up' axis / tilt from the mean specific force
* standstill periods (quiet gyroscope and accelerometer) and, from them, the gyroscope bias and the noise
* whether the log contains motion at all (a log that is quiet throughout is a stationary recording)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from xdk_imu import G0, MIN_XDK_DURATION_S, _moving_mean, load_xdk

QUIET_GYRO_RPS = 0.05
QUIET_ACC_STD_MPS2 = 0.2
MIN_STATIC_S = 2.0


def raw_stats(path: Path) -> dict[str, object]:
    data = np.genfromtxt(path, delimiter=",", skip_header=1, dtype=float)
    data = data[np.all(np.isfinite(data[:, :7]), axis=1)]
    t = data[:, 0] / 1000.0
    dt = np.diff(t)
    values = data[:, 1:7]
    stale = int(np.sum(~np.any(np.diff(values, axis=0) != 0, axis=1)))
    return {
        "rows": int(len(data)),
        "duration_s": float(t[-1] - t[0]),
        "median_dt_ms": float(np.median(dt[dt > 0]) * 1000.0),
        "rate_hz": float(1.0 / np.median(dt[dt > 0])),
        "nonincreasing_timestamps": int(np.sum(dt <= 0)),
        "gaps_over_200ms": int(np.sum(dt > 0.2)),
        "largest_gap_s": float(dt.max()),
        "stale_rows": stale,
        "temperature_c": [float(data[:, 11].min() / 1000.0), float(data[:, 11].max() / 1000.0)] if data.shape[1] > 11 else None,
        "battery_mv": [float(data[:, 15].min()), float(data[:, 15].max())] if data.shape[1] > 15 else None,
    }


def static_segments(t: np.ndarray, quiet: np.ndarray, min_s: float) -> list[tuple[float, float]]:
    segments: list[tuple[float, float]] = []
    start = None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        if (not q or i == len(quiet) - 1) and start is not None:
            end = i if not q else i + 1
            if t[end - 1] - t[start] >= min_s:
                segments.append((float(t[start]), float(t[end - 1])))
            start = None
    return segments


def analyse(path: Path) -> tuple[dict[str, object], np.ndarray, np.ndarray, np.ndarray]:
    xdk = load_xdk(path)
    t, acc, gyro = xdk.t, xdk.acc, xdk.gyro
    rate = 1.0 / float(np.median(np.diff(t)))
    width = max(1, round(1.0 / (1.0 / rate)))
    gyro_norm = _moving_mean(np.linalg.norm(gyro, axis=1), max(1, round(0.5 * rate)))
    norm = np.linalg.norm(acc, axis=1)
    std = np.sqrt(np.maximum(_moving_mean(norm**2, width) - _moving_mean(norm, width) ** 2, 0.0))
    quiet = (gyro_norm <= QUIET_GYRO_RPS) & (std <= QUIET_ACC_STD_MPS2)
    segments = static_segments(t, quiet, MIN_STATIC_S)
    static_mask = np.zeros(len(t), dtype=bool)
    for a, b in segments:
        static_mask |= (t >= a) & (t <= b)

    mean_acc = acc.mean(axis=0)
    up = mean_acc / np.linalg.norm(mean_acc)
    tilt_x = math.degrees(math.atan2(up[0], math.hypot(up[1], up[2])))
    tilt_y = math.degrees(math.atan2(up[1], math.hypot(up[0], up[2])))
    result: dict[str, object] = {
        "file": str(path),
        "samples_after_cleaning": int(len(t)),
        "duration_s": xdk.duration_s,
        "usable": bool(xdk.duration_s >= MIN_XDK_DURATION_S),
        "mean_specific_force_mps2": float(np.linalg.norm(mean_acc)),
        "gravity_scale_error_pct": float(100.0 * (np.linalg.norm(mean_acc) / G0 - 1.0)),
        "up_axis": [float(x) for x in up],
        "tilt_deg": {"about_y_pitch": tilt_x, "about_x_roll": tilt_y},
        "quiet_fraction": float(quiet.mean()),
        "static_segments": [{"start_s": a, "end_s": b, "length_s": b - a} for a, b in segments],
        "moving": bool(quiet.mean() < 0.95),
    }
    if static_mask.sum() > 200:
        result["gyro_bias_dps_from_static"] = [float(x) for x in np.degrees(gyro[static_mask].mean(axis=0))]
        result["gyro_noise_dps_from_static"] = [float(x) for x in np.degrees(gyro[static_mask].std(axis=0))]
        result["accel_noise_mps2_from_static"] = [float(x) for x in acc[static_mask].std(axis=0)]
        result["static_specific_force_mps2"] = float(np.linalg.norm(acc[static_mask].mean(axis=0)))
    # orientation steadiness: the mean specific force per minute shows a sensor that is moved or re-seated
    minutes = []
    for k in range(0, int(t[-1] - t[0]) + 1, 60):
        sel = (t >= t[0] + k) & (t < t[0] + k + 60)
        if sel.sum() > 100:
            minutes.append({"minute_start_s": k, "mean_acc_mps2": [float(x) for x in acc[sel].mean(axis=0)], "gyro_std_dps": [float(x) for x in np.degrees(gyro[sel].std(axis=0))]})
    result["per_minute"] = minutes
    return result, t, acc, gyro


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean and analyse one XDK log.")
    parser.add_argument("xdk_log", type=Path)
    parser.add_argument("--out-dir", type=Path, help="Where to write the processed CSV and the report (default: next to the log)")
    parser.add_argument("--no-csv", action="store_true", help="Only analyse, do not write the processed CSV")
    args = parser.parse_args()

    raw = raw_stats(args.xdk_log)
    result, t, acc, gyro = analyse(args.xdk_log)
    result["raw"] = raw
    out_dir = args.out_dir or args.xdk_log.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.xdk_log.stem
    if not args.no_csv:
        table = np.column_stack([t, acc, gyro])
        np.savetxt(out_dir / f"{stem}_processed.csv", table, delimiter=",", header="t_s,ax_mps2,ay_mps2,az_mps2,gx_rps,gy_rps,gz_rps", comments="", fmt=["%.4f"] + ["%.5f"] * 6)
    (out_dir / f"{stem}_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"{args.xdk_log.name}: {raw['rows']} rows over {raw['duration_s']:.1f} s at {raw['rate_hz']:.0f} Hz")
    print(f"  cleaning: {raw['nonincreasing_timestamps']} repeated/reset timestamps, {raw['stale_rows']} stale rows dropped, "
          f"{raw['gaps_over_200ms']} gaps over 200 ms (largest {raw['largest_gap_s']:.2f} s) -> {result['samples_after_cleaning']} samples")
    print(f"  gravity {result['mean_specific_force_mps2']:.3f} m/s2 ({result['gravity_scale_error_pct']:+.1f} % vs 9.807); "
          f"up axis {np.round(result['up_axis'], 3).tolist()}, tilt {result['tilt_deg']['about_y_pitch']:.1f} / {result['tilt_deg']['about_x_roll']:.1f} deg")
    print(f"  quiet {100 * result['quiet_fraction']:.0f} % of the time -> {'MOVING' if result['moving'] else 'STATIONARY recording'}; "
          f"{len(result['static_segments'])} standstill segment(s) of at least {MIN_STATIC_S:.0f} s")
    if "gyro_bias_dps_from_static" in result:
        print(f"  gyro bias at rest {np.round(result['gyro_bias_dps_from_static'], 3).tolist()} deg/s, "
              f"noise {np.round(result['gyro_noise_dps_from_static'], 3).tolist()} deg/s, accel noise {np.round(result['accel_noise_mps2_from_static'], 3).tolist()} m/s2")
    swing = [m["mean_acc_mps2"] for m in result["per_minute"]]
    if len(swing) > 1:
        drift = float(np.max(np.ptp(np.array(swing), axis=0)))
        print(f"  orientation steadiness: the mean horizontal specific force varies by up to {drift:.2f} m/s2 between minutes"
              + (" (the sensor was probably moved or is loose)" if drift > 1.0 else ""))
    if not result["usable"]:
        print(f"  note: shorter than {MIN_XDK_DURATION_S:.0f} s, not a usable recording")
    print(f"  wrote {out_dir / (stem + '_report.json')}" + ("" if args.no_csv else f" and {stem}_processed.csv"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
