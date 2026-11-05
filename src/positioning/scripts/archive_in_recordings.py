#!/usr/bin/env python3
"""
Move raw recordings from in/ into timestamped out/ recording folders.

For each file in in/ this creates:

    out/<recording-time>_<input-name>/original/<input-file>

If an old out/<input-name>/ directory already exists, its contents are moved into
the new timestamped directory so previous CSV/RINEX/other outputs stay with the
recording they came from.

The script tries to read the first GPS timestamp from Unicore/NovAtel-style
binary packet headers. If that is not available, it uses the current local time.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "in"
OUT_DIR = ROOT / "out"
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
SYNC_OEM = b"\xAA\x44\x12"
SYNC_N4 = b"\xAA\x44\xB5"
WEEK_MIN = 1800
WEEK_MAX = 3000
WEEK_MS = 604_800_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_original_files() -> Iterable[Path]:
    if not OUT_DIR.exists():
        return []
    return (path for path in OUT_DIR.glob("*/original/*") if path.is_file())


def find_existing_original(path: Path) -> Path | None:
    size = path.stat().st_size
    path_hash: str | None = None

    for original in iter_original_files():
        if original.stat().st_size != size:
            continue
        if path_hash is None:
            path_hash = sha256_file(path)
        if sha256_file(original) == path_hash:
            return original
    return None


def gps_to_utc(week: int, millis: int) -> datetime:
    return GPS_EPOCH + timedelta(weeks=week, milliseconds=millis, seconds=-18)


def plausible_gps_time(week: int, millis: int) -> bool:
    return WEEK_MIN <= week <= WEEK_MAX and 0 <= millis < WEEK_MS


def first_packet_timestamp(path: Path) -> datetime | None:
    blob = path.read_bytes()
    index = 0
    while index < len(blob) - 20:
        n4_pos = blob.find(SYNC_N4, index)
        oem_pos = blob.find(SYNC_OEM, index)
        positions = [pos for pos in (n4_pos, oem_pos) if pos != -1]
        if not positions:
            return None

        pos = min(positions)
        sync = blob[pos:pos + 3]

        if sync == SYNC_N4 and pos + 16 <= len(blob):
            week = struct.unpack_from("<H", blob, pos + 10)[0]
            millis = struct.unpack_from("<I", blob, pos + 12)[0]
            if plausible_gps_time(week, millis):
                return gps_to_utc(week, millis)

        if sync == SYNC_OEM and pos + 20 <= len(blob):
            week = struct.unpack_from("<H", blob, pos + 14)[0]
            millis = struct.unpack_from("<I", blob, pos + 16)[0]
            if plausible_gps_time(week, millis):
                return gps_to_utc(week, millis)

        index = pos + 1
    return None


def timestamp_label(recording_time: datetime | None) -> str:
    if recording_time is None:
        return datetime.now().strftime("%Y%m%d_%H%M%S_local")
    return recording_time.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%SZ")


def unique_session_dir(stem: str, stamp: str) -> Path:
    base = OUT_DIR / f"{stamp}_{stem}"
    if not base.exists():
        return base

    counter = 2
    while True:
        candidate = OUT_DIR / f"{stamp}_{stem}_{counter:02d}"
        if not candidate.exists():
            return candidate
        counter += 1


def ensure_output_subdirs(session_dir: Path) -> dict[str, Path]:
    subdirs = {
        "original": session_dir / "original",
        "csv": session_dir / "csv",
        "rinex": session_dir / "rinex",
        "ppk": session_dir / "ppk",
        "other": session_dir / "other",
    }
    for path in subdirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return subdirs


def categorized_destination(child: Path, subdirs: dict[str, Path]) -> Path:
    suffix = child.suffix.lower()
    if child.is_dir():
        return subdirs["other"] / child.name
    if suffix == ".csv":
        return subdirs["csv"] / child.name
    if suffix in {".obs", ".nav", ".gnav", ".hnav", ".qnav", ".lnav", ".rnx", ".sp3", ".clk"}:
        return subdirs["rinex"] / child.name
    if len(child.suffix) == 4 and child.suffix[1:3].isdigit() and child.suffix[3].isalpha():
        return subdirs["rinex"] / child.name
    return subdirs["other"] / child.name


def move_legacy_output(stem: str, session_dir: Path) -> None:
    legacy_dir = OUT_DIR / stem
    if not legacy_dir.exists() or legacy_dir == session_dir:
        return

    subdirs = ensure_output_subdirs(session_dir)
    for child in legacy_dir.iterdir():
        target = categorized_destination(child, subdirs)
        if target.exists():
            target = target.with_name(f"legacy_{child.name}")
        shutil.move(str(child), str(target))
    legacy_dir.rmdir()


def archive_recording(path: Path) -> str:
    existing = find_existing_original(path)
    if existing:
        return f"Already archived: {path.name} matches {existing}"

    recording_time = first_packet_timestamp(path)
    stamp = timestamp_label(recording_time)
    session_dir = unique_session_dir(path.stem, stamp)
    subdirs = ensure_output_subdirs(session_dir)
    original_dir = subdirs["original"]

    move_legacy_output(path.stem, session_dir)
    shutil.move(str(path), str(original_dir / path.name))

    if recording_time is None:
        return f"Archived: {path.name} -> {session_dir.name} (used current time)"
    return f"Archived: {path.name} -> {session_dir.name}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive files from in/ into timestamped out/<time>_<recording>/original/ directories."
    )
    parser.add_argument(
        "--in-dir",
        type=Path,
        default=IN_DIR,
        help="Directory containing new recordings. Defaults to project in/.",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Archive every file in in/. By default only .BIN files are archived.",
    )
    args = parser.parse_args()

    in_dir = args.in_dir
    in_dir.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = [path for path in sorted(in_dir.iterdir()) if path.is_file()]
    if not args.all_files:
        files = [path for path in files if path.suffix.lower() == ".bin"]

    if not files:
        print(f"No recordings found in {in_dir}")
        return 0

    for path in files:
        print(archive_recording(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
