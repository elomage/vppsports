from __future__ import annotations

from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "out"


def resolve_session_dir(value: str | Path) -> Path:
    path = Path(value)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(OUT_DIR / path)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()

    raise SystemExit(
        f"Recording output directory not found: {value}\n"
        f"Pass either a full path or a directory name inside {OUT_DIR}"
    )


def output_subdir(session_dir: Path, name: str) -> Path:
    path = session_dir / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_original_bin(session_dir: Path) -> Path:
    original_dir = session_dir / "original"
    bins = sorted({path.resolve() for pattern in ("*.BIN", "*.bin") for path in original_dir.glob(pattern)})
    if not bins:
        raise SystemExit(f"No .BIN file found in {original_dir}")
    if len(bins) > 1:
        names = ", ".join(path.name for path in bins)
        raise SystemExit(f"More than one .BIN file found in {original_dir}: {names}")
    return bins[0]


def find_first_existing(paths: Iterable[Path], description: str) -> Path:
    for path in paths:
        if path.is_file():
            return path
    raise SystemExit(f"Could not find {description}.")


def find_receiver_csv(session_dir: Path) -> Path:
    csv_dir = session_dir / "csv"
    preferred = [
        csv_dir / "location_heading_xyz_filtered.csv",
        csv_dir / "location_heading_xyz.csv",
        csv_dir / "bestnavxyz_filtered.csv",
        csv_dir / "bestnavxyz.csv",
        session_dir / "location_heading_xyz_filtered.csv",
        session_dir / "location_heading_xyz.csv",
        session_dir / "bestnavxyz_filtered.csv",
        session_dir / "bestnavxyz.csv",
    ]
    return find_first_existing(preferred, f"a receiver CSV in {csv_dir}")


def find_csv_to_filter(session_dir: Path) -> Path:
    csv_dir = session_dir / "csv"
    preferred = [
        csv_dir / "location_heading_xyz.csv",
        csv_dir / "bestnavxyz.csv",
        session_dir / "location_heading_xyz.csv",
        session_dir / "bestnavxyz.csv",
    ]
    return find_first_existing(preferred, f"a CSV to filter in {csv_dir}")
