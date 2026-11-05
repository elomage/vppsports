#!/usr/bin/env python3
"""Estimate an accelerometer bias profile from a static IMU recording."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from imu_kalman import G0, load_imu

DEFAULT_PROFILE_CSV = ROOT / "config" / "imu_bias_profiles.csv"
FIELDNAMES = [
    "profile",
    "created_utc",
    "source_imu",
    "start_s",
    "end_s",
    "sample_count",
    "mean_ax_mps2",
    "mean_ay_mps2",
    "mean_az_mps2",
    "mean_norm_mps2",
    "expected_norm_mps2",
    "bias_ax_mps2",
    "bias_ay_mps2",
    "bias_az_mps2",
    "rms_residual_mps2",
]


def estimate_bias(imu_path: Path, profile: str, start_s: float | None, end_s: float | None) -> dict[str, str]:
    samples = [
        sample for sample in load_imu(imu_path)
        if (start_s is None or sample.seconds >= start_s) and (end_s is None or sample.seconds <= end_s)
    ]
    if len(samples) < 10:
        raise SystemExit("Need at least 10 static IMU samples for calibration.")

    mean_ax = sum(sample.ax_mps2 for sample in samples) / len(samples)
    mean_ay = sum(sample.ay_mps2 for sample in samples) / len(samples)
    mean_az = sum(sample.az_mps2 for sample in samples) / len(samples)
    mean_norm = math.sqrt(mean_ax * mean_ax + mean_ay * mean_ay + mean_az * mean_az)
    if mean_norm <= 1e-9:
        raise SystemExit("Static IMU mean vector is zero; cannot estimate gravity-preserving bias.")

    keep_scale = G0 / mean_norm
    bias_ax = mean_ax * (1.0 - keep_scale)
    bias_ay = mean_ay * (1.0 - keep_scale)
    bias_az = mean_az * (1.0 - keep_scale)
    residuals = []
    for sample in samples:
        ax = sample.ax_mps2 - bias_ax
        ay = sample.ay_mps2 - bias_ay
        az = sample.az_mps2 - bias_az
        residuals.append(math.sqrt(ax * ax + ay * ay + az * az) - G0)
    rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))

    return {
        "profile": profile,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_imu": str(imu_path),
        "start_s": "" if start_s is None else f"{start_s:.6f}",
        "end_s": "" if end_s is None else f"{end_s:.6f}",
        "sample_count": str(len(samples)),
        "mean_ax_mps2": f"{mean_ax:.8f}",
        "mean_ay_mps2": f"{mean_ay:.8f}",
        "mean_az_mps2": f"{mean_az:.8f}",
        "mean_norm_mps2": f"{mean_norm:.8f}",
        "expected_norm_mps2": f"{G0:.8f}",
        "bias_ax_mps2": f"{bias_ax:.8f}",
        "bias_ay_mps2": f"{bias_ay:.8f}",
        "bias_az_mps2": f"{bias_az:.8f}",
        "rms_residual_mps2": f"{rms:.8f}",
    }


def upsert_profile(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    if path.is_file():
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = [item for item in reader if item.get("profile") != row["profile"]]
    rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update an accelerometer bias profile from a static IMU recording.")
    parser.add_argument("imu", type=Path, help="Static IMU .BIN or CSV file")
    parser.add_argument("--profile", required=True, help="Profile name, for example static_table_2026_07_09")
    parser.add_argument("--start-s", type=float, help="Use samples at or after this IMU second")
    parser.add_argument("--end-s", type=float, help="Use samples at or before this IMU second")
    parser.add_argument("--output", type=Path, default=DEFAULT_PROFILE_CSV, help="Profile CSV path")
    args = parser.parse_args()

    row = estimate_bias(args.imu.resolve(), args.profile, args.start_s, args.end_s)
    upsert_profile(args.output.resolve(), row)
    print(f"Wrote accelerometer bias profile: {args.output.resolve()}")
    print(f"Profile: {row['profile']}")
    print(f"Bias m/s^2: {row['bias_ax_mps2']},{row['bias_ay_mps2']},{row['bias_az_mps2']}")
    print(f"Static norm before: {row['mean_norm_mps2']} m/s^2, residual RMS after: {row['rms_residual_mps2']} m/s^2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
