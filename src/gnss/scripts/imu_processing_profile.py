#!/usr/bin/env python3
"""IMU post-processing profiles: calibrate from a static recording, reuse on moving rides."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from imu_kalman import G0, load_gnss, load_imu, source_csv
from session_paths import resolve_session_dir

DEFAULT_PROFILE_CSV = ROOT / "config" / "imu_processing_profiles.csv"
LEGACY_BIAS_CSV = ROOT / "config" / "imu_bias_profiles.csv"

FIELDNAMES = [
    "profile",
    "created_utc",
    "source_imu",
    "source_recording",
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
    "p95_residual_mps2",
    "drift_correct",
    "static_speed_mps",
    "accel_residual_gate_mps2",
    "accel_noise",
    "position_sigma_m",
    "gnss_update_period_s",
    "notes",
]

DEFAULTS = {
    "drift_correct": "1",
    "static_speed_mps": "0.200",
    "accel_residual_gate_mps2": "0.0500",
    "accel_noise": "2.000",
    "position_sigma_m": "0.600",
    "gnss_update_period_s": "0.050",
}


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def estimate_gnss_static_speed(session_dir: Path | None) -> float | None:
    if session_dir is None:
        return None
    try:
        points = load_gnss(source_csv(session_dir, "bestnav"))
    except SystemExit:
        return None
    if len(points) < 20:
        return None
    speeds = [max(0.0, point.speed_mps) for point in points]
    # Cover nearly all stationary GNSS speed noise, then add margin.
    return max(0.15, percentile(speeds, 0.98) * 1.5 + 0.05)


def estimate_processing_profile(
    imu_path: Path,
    profile: str,
    start_s: float | None,
    end_s: float | None,
    session_dir: Path | None = None,
) -> dict[str, str]:
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

    abs_residuals: list[float] = []
    for sample in samples:
        ax = sample.ax_mps2 - bias_ax
        ay = sample.ay_mps2 - bias_ay
        az = sample.az_mps2 - bias_az
        abs_residuals.append(abs(math.sqrt(ax * ax + ay * ay + az * az) - G0))

    rms = math.sqrt(sum(value * value for value in abs_residuals) / len(abs_residuals))
    p95 = percentile(abs_residuals, 0.95)
    # Gate covers static residual noise so stationary segments integrate to ~0.
    residual_gate = max(0.03, p95 * 1.15, rms * 2.5)
    static_speed = estimate_gnss_static_speed(session_dir)
    if static_speed is None:
        static_speed = 0.2

    return {
        "profile": profile,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_imu": str(imu_path),
        "source_recording": "" if session_dir is None else str(session_dir),
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
        "p95_residual_mps2": f"{p95:.8f}",
        "drift_correct": "1",
        "static_speed_mps": f"{static_speed:.3f}",
        "accel_residual_gate_mps2": f"{residual_gate:.4f}",
        "accel_noise": DEFAULTS["accel_noise"],
        "position_sigma_m": DEFAULTS["position_sigma_m"],
        "gnss_update_period_s": DEFAULTS["gnss_update_period_s"],
        "notes": "auto-calibrated from static IMU (bias + ZUPT gate)",
    }


def upsert_profile(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    if path.is_file():
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = [item for item in reader if item.get("profile") != row["profile"]]
    normalized = {key: str(row.get(key, DEFAULTS.get(key, ""))) for key in FIELDNAMES}
    rows.append(normalized)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _row_to_profile(row: dict[str, str]) -> dict[str, object]:
    profile = str(row.get("profile") or "").strip()
    if not profile:
        raise ValueError("Profile row missing name")

    def number(key: str, default: float) -> float:
        raw = row.get(key)
        if raw is None or str(raw).strip() == "":
            return default
        return float(raw)

    drift_raw = str(row.get("drift_correct", DEFAULTS["drift_correct"])).strip().lower()
    drift_correct = drift_raw not in {"0", "false", "no", "off"}
    return {
        "profile": profile,
        "created_utc": row.get("created_utc") or "",
        "source_imu": row.get("source_imu") or "",
        "source_recording": row.get("source_recording") or "",
        "sample_count": number("sample_count", 0.0),
        "mean_norm_mps2": number("mean_norm_mps2", 0.0),
        "rms_residual_mps2": number("rms_residual_mps2", 0.0),
        "p95_residual_mps2": number("p95_residual_mps2", 0.0),
        "bias_ax_mps2": number("bias_ax_mps2", 0.0),
        "bias_ay_mps2": number("bias_ay_mps2", 0.0),
        "bias_az_mps2": number("bias_az_mps2", 0.0),
        "drift_correct": drift_correct,
        "static_speed_mps": number("static_speed_mps", float(DEFAULTS["static_speed_mps"])),
        "accel_residual_gate_mps2": number("accel_residual_gate_mps2", float(DEFAULTS["accel_residual_gate_mps2"])),
        "accel_noise": number("accel_noise", float(DEFAULTS["accel_noise"])),
        "position_sigma_m": number("position_sigma_m", float(DEFAULTS["position_sigma_m"])),
        "gnss_update_period_s": number("gnss_update_period_s", float(DEFAULTS["gnss_update_period_s"])),
        "notes": row.get("notes") or "",
    }


def migrate_legacy_bias_profiles(destination: Path = DEFAULT_PROFILE_CSV) -> None:
    if destination.is_file() or not LEGACY_BIAS_CSV.is_file():
        return
    with LEGACY_BIAS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            profile = str(row.get("profile") or "").strip()
            if not profile:
                continue
            merged = {key: DEFAULTS.get(key, "") for key in FIELDNAMES}
            for key in FIELDNAMES:
                if key in row and row[key] not in (None, ""):
                    merged[key] = str(row[key])
            rms = float(merged.get("rms_residual_mps2") or 0.05)
            if not merged.get("p95_residual_mps2"):
                merged["p95_residual_mps2"] = f"{max(rms, 0.05):.8f}"
            if not merged.get("accel_residual_gate_mps2") or merged["accel_residual_gate_mps2"] == DEFAULTS["accel_residual_gate_mps2"]:
                merged["accel_residual_gate_mps2"] = f"{max(0.03, rms * 2.5):.4f}"
            merged["notes"] = merged.get("notes") or "migrated from imu_bias_profiles.csv"
            upsert_profile(destination, merged)


def list_profiles(path: Path = DEFAULT_PROFILE_CSV) -> list[dict[str, object]]:
    migrate_legacy_bias_profiles(path)
    if not path.is_file():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append(_row_to_profile(row))
            except ValueError:
                continue
    return rows


def load_profile(path: Path, profile_name: str | None = None) -> dict[str, object]:
    migrate_legacy_bias_profiles(path)
    if not path.is_file():
        raise SystemExit(f"IMU processing profile not found: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise SystemExit(f"No IMU processing profiles in {path}")
    if profile_name:
        for row in rows:
            if row.get("profile") == profile_name:
                return _row_to_profile(row)
        raise SystemExit(f"Unknown IMU processing profile: {profile_name}")
    if len(rows) == 1:
        return _row_to_profile(rows[0])
    raise SystemExit("Multiple IMU processing profiles found; pass --imu-profile-name")


def append_profile_cli_args(command: list[str], profile: dict[str, object]) -> None:
    """Append bias + drift CLI flags from a processing profile (not Kalman noise knobs)."""
    # Use --accel-bias=... so a leading negative ax is not parsed as a new flag.
    bias = (
        f"{float(profile['bias_ax_mps2']):.8f},"
        f"{float(profile['bias_ay_mps2']):.8f},"
        f"{float(profile['bias_az_mps2']):.8f}"
    )
    command.append(f"--accel-bias={bias}")
    if profile.get("drift_correct"):
        command.append("--drift-correct")
    else:
        command.append("--no-drift-correct")
    command.extend(["--static-speed-mps", str(float(profile["static_speed_mps"]))])
    command.extend(["--accel-residual-gate-mps2", str(float(profile["accel_residual_gate_mps2"]))])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate a full IMU processing profile (bias + drift settings) from a static recording."
    )
    parser.add_argument("imu", type=Path, help="Static IMU .BIN or CSV file")
    parser.add_argument("--profile", required=True, help="Profile name, for example from_static_brauciens_5")
    parser.add_argument("--recording", help="Optional GNSS session used to tune static-speed ZUPT threshold")
    parser.add_argument("--start-s", type=float, help="Use samples at or after this IMU second")
    parser.add_argument("--end-s", type=float, help="Use samples at or before this IMU second")
    parser.add_argument("--output", type=Path, default=DEFAULT_PROFILE_CSV, help="Profile CSV path")
    args = parser.parse_args()

    session_dir = resolve_session_dir(args.recording) if args.recording else None
    row = estimate_processing_profile(
        args.imu.resolve(),
        args.profile,
        args.start_s,
        args.end_s,
        session_dir,
    )
    upsert_profile(args.output.resolve(), row)
    print(f"Wrote IMU processing profile: {args.output.resolve()}")
    print(f"Profile: {row['profile']}")
    print(f"Bias m/s^2: {row['bias_ax_mps2']},{row['bias_ay_mps2']},{row['bias_az_mps2']}")
    print(f"Residual RMS: {row['rms_residual_mps2']}  P95: {row['p95_residual_mps2']}")
    print(f"Drift correct: on")
    print(f"Static speed ZUPT: {row['static_speed_mps']} m/s")
    print(f"Residual gate: {row['accel_residual_gate_mps2']} m/s^2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
