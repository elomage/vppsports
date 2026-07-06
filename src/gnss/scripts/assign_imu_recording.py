#!/usr/bin/env python3
"""Assign an IMU recording from in_imu/ to an archived GNSS recording."""

from __future__ import annotations

import argparse
import csv
import shutil
import struct
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from imu_kalman import convert_imu_bin, load_imu, load_gnss, source_csv
from session_paths import OUT_DIR, output_subdir, resolve_session_dir

IN_IMU = ROOT / "in_imu"
IMU_RECORD_STRUCT = struct.Struct("<Iiii")


def imu_duration(path: Path) -> float | None:
    if path.suffix.lower() == ".bin":
        size = path.stat().st_size
        if size < IMU_RECORD_STRUCT.size or size % IMU_RECORD_STRUCT.size:
            return None
        with path.open("rb") as f:
            first = f.read(IMU_RECORD_STRUCT.size)
            f.seek(size - IMU_RECORD_STRUCT.size)
            last = f.read(IMU_RECORD_STRUCT.size)
        first_ts = IMU_RECORD_STRUCT.unpack(first)[0]
        last_ts = IMU_RECORD_STRUCT.unpack(last)[0]
        return max(0.0, (last_ts - first_ts) / 1_000_000.0)
    try:
        samples = load_imu(path)
    except Exception:
        return None
    if len(samples) < 2:
        return None
    return samples[-1].seconds - samples[0].seconds


def gnss_duration(session_dir: Path, source: str) -> float | None:
    try:
        points = load_gnss(source_csv(session_dir, source))
    except BaseException:
        return None
    return (points[-1].time - points[0].time).total_seconds()


def list_candidates(source: str) -> int:
    all_imu_files = {path.resolve() for pattern in ("*.BIN", "*.bin", "*.csv") for path in IN_IMU.glob(pattern)}
    bin_stems = {path.stem.lower() for path in all_imu_files if path.suffix.lower() == ".bin"}
    imu_files = sorted(
        [path for path in all_imu_files if not (path.suffix.lower() == ".csv" and path.stem.lower() in bin_stems)],
        key=lambda p: p.name.lower(),
    )
    sessions = sorted((path for path in OUT_DIR.iterdir() if path.is_dir()), key=lambda p: p.name.lower()) if OUT_DIR.is_dir() else []
    print("IMU recordings:")
    imu_rows: list[tuple[Path, float | None]] = []
    for imu in imu_files:
        duration = imu_duration(imu)
        imu_rows.append((imu, duration))
        print(f"  {imu.name:24} duration={duration:.1f}s" if duration is not None else f"  {imu.name:24} duration=?")
    print()
    print(f"GNSS recordings ({source}):")
    gnss_rows: list[tuple[Path, float | None]] = []
    for session in sessions:
        duration = gnss_duration(session, source)
        gnss_rows.append((session, duration))
        print(f"  {session.name:32} duration={duration:.1f}s" if duration is not None else f"  {session.name:32} duration=?")
    print()
    print("Closest duration suggestions:")
    for imu, imu_len in imu_rows:
        if imu_len is None:
            continue
        scored = [(abs(imu_len - gnss_len), session, gnss_len) for session, gnss_len in gnss_rows if gnss_len is not None]
        for delta, session, gnss_len in sorted(scored)[:3]:
            print(f"  {imu.name} -> {session.name}  delta={delta:.1f}s  imu={imu_len:.1f}s gnss={gnss_len:.1f}s")
    return 0


def write_assignment(imu_dir: Path, recording: Path, imu_input: Path, imu_csv: Path, note: str) -> Path:
    assignment = imu_dir / "assignment.csv"
    with assignment.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["created_at", "recording", "imu_input", "imu_csv", "note"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), str(recording), str(imu_input), str(imu_csv), note])
    return assignment


def assign(recording: str, imu_value: str, note: str) -> int:
    session_dir = resolve_session_dir(recording)
    imu_path = Path(imu_value)
    if not imu_path.is_absolute():
        candidates = [Path.cwd() / imu_path, IN_IMU / imu_path]
        imu_path = next((candidate for candidate in candidates if candidate.is_file()), candidates[-1])
    if not imu_path.is_file():
        raise SystemExit(f"IMU input not found: {imu_value}")

    imu_dir = output_subdir(session_dir, "imu")
    raw_dir = imu_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if imu_path.suffix.lower() == ".bin":
        raw_copy = raw_dir / imu_path.name
        shutil.copy2(imu_path, raw_copy)
        csv_path = imu_dir / f"{imu_path.stem}.csv"
        convert_imu_bin(raw_copy, csv_path)
    else:
        csv_path = imu_dir / imu_path.name
        shutil.copy2(imu_path, csv_path)
    assignment = write_assignment(imu_dir, session_dir, imu_path, csv_path, note)
    print(f"Assigned IMU recording: {imu_path.name}")
    print(f"GNSS recording: {session_dir.name}")
    print(f"IMU CSV: {csv_path}")
    print(f"Assignment: {assignment}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Assign/convert an in_imu recording to a GNSS recording.")
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list", help="List IMU/GNSS durations and likely matches")
    list_parser.add_argument("--source", choices=["bestnav", "fixed_ppk", "dgps"], default="bestnav")
    assign_parser = sub.add_parser("assign", help="Copy and convert one IMU recording into out/<recording>/imu/")
    assign_parser.add_argument("recording", help="GNSS recording output directory or name inside out/")
    assign_parser.add_argument("imu", help="IMU file path or file name inside in_imu/")
    assign_parser.add_argument("--note", default="", help="Optional note stored with assignment")
    args = parser.parse_args()

    if args.command == "list":
        return list_candidates(args.source)
    if args.command == "assign":
        return assign(args.recording, args.imu, args.note)
    raise SystemExit("Unknown command")


if __name__ == "__main__":
    raise SystemExit(main())
