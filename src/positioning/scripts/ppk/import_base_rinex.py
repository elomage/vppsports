#!/usr/bin/env python3
"""
Import a downloaded public base-station RINEX package into this project's base layout.

Expected incoming shape:
  in_base/<package>/
    <station>.yyO / <station>.obs / observation .rnx
    *.lrx
    nav/
      navigation files

Output shape:
  base/rinex/<base_name>/
    observation and navigation files copied here
    import_report.txt
  base/notes/<base_name>/
    metadata/log files such as .lrx copied here
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IN_BASE = ROOT / "in_base"
BASE_RINEX = ROOT / "base" / "rinex"
BASE_NOTES = ROOT / "base" / "notes"

NAV_SUFFIX_LETTERS = {"p", "n", "g", "h", "q", "l", "f", "c"}


def resolve_source(value: str | Path) -> Path:
    path = Path(value)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(IN_BASE / path)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise SystemExit(f"Incoming base package not found: {value}")


def sanitize_name(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value.strip())
    return clean.strip("._") or "base_station"


def default_base_name(source_dir: Path) -> str:
    obs_files = find_obs_files(source_dir)
    if obs_files:
        stem = obs_files[0].stem
        station = stem[:4] if len(stem) >= 4 else stem
        return sanitize_name(f"{source_dir.name}_{station}")
    return sanitize_name(source_dir.name)


def read_header(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii", errors="ignore")[:240].upper()
    except OSError:
        return ""


def is_legacy_obs(path: Path) -> bool:
    suffix = path.suffix.lower()
    return len(suffix) == 4 and suffix[1:3].isdigit() and suffix[3] == "o"


def is_legacy_nav(path: Path) -> bool:
    suffix = path.suffix.lower()
    return len(suffix) == 4 and suffix[1:3].isdigit() and suffix[3] in NAV_SUFFIX_LETTERS


def is_obs_file(path: Path) -> bool:
    header = read_header(path)
    is_rinex_header = "RINEX VERSION / TYPE" in header
    return (
        path.suffix.lower() in {".obs", ".o"}
        or is_legacy_obs(path)
        or (is_rinex_header and ("OBSERVATION" in header or " O " in header[:80]))
    )


def is_nav_file(path: Path) -> bool:
    header = read_header(path)
    is_rinex_header = "RINEX VERSION / TYPE" in header
    return (
        path.suffix.lower() in {".nav", ".gnav", ".hnav", ".qnav", ".lnav"}
        or is_legacy_nav(path)
        or (is_rinex_header and ("NAVIGATION DATA" in header or "N: GNSS NAV DATA" in header))
    )


def find_obs_files(source_dir: Path) -> list[Path]:
    return sorted(path for path in source_dir.iterdir() if path.is_file() and is_obs_file(path))


def find_nav_files(source_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    nav_dir = source_dir / "nav"
    search_dirs = [source_dir]
    if nav_dir.is_dir():
        search_dirs.append(nav_dir)
    for directory in search_dirs:
        for path in directory.iterdir():
            if path.is_file() and is_nav_file(path):
                candidates.append(path)
    return sorted(set(candidates), key=lambda path: path.name.lower())


def copy_file(src: Path, dst_dir: Path, overwrite: bool) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists() and not overwrite:
        raise SystemExit(f"Destination already exists: {dst}\nUse --overwrite to replace it.")
    shutil.copy2(src, dst)
    return dst


def write_report(path: Path, source: Path, base_name: str, copied_rinex: list[Path], copied_notes: list[Path]) -> None:
    lines = [
        f"Import time: {datetime.now().isoformat(timespec='seconds')}",
        f"Source: {source}",
        f"Base name: {base_name}",
        "",
        "RINEX files:",
    ]
    lines.extend(f"  - {item}" for item in copied_rinex)
    if not copied_rinex:
        lines.append("  none")
    lines.extend(["", "Notes/metadata files:"])
    lines.extend(f"  - {item}" for item in copied_notes)
    if not copied_notes:
        lines.append("  none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import public base-station RINEX data into base/rinex/<base_name>/.")
    parser.add_argument("source", help="Incoming package directory, e.g. 21_04_2026_JURM or in_base/21_04_2026_JURM")
    parser.add_argument("--name", help="Base name to create under base/rinex/. Default: <source>_<station>.")
    parser.add_argument("--overwrite", action="store_true", help="Replace files if destination exists.")
    args = parser.parse_args()

    source_dir = resolve_source(args.source)
    base_name = sanitize_name(args.name) if args.name else default_base_name(source_dir)
    rinex_out = BASE_RINEX / base_name
    notes_out = BASE_NOTES / base_name

    obs_files = find_obs_files(source_dir)
    nav_files = find_nav_files(source_dir)
    note_files = sorted(path for path in source_dir.iterdir() if path.is_file() and not is_obs_file(path) and not is_nav_file(path))

    if not obs_files:
        raise SystemExit(f"No observation RINEX file found in {source_dir}")
    if not nav_files:
        raise SystemExit(f"No navigation RINEX files found in {source_dir} or {source_dir / 'nav'}")

    copied_rinex: list[Path] = []
    copied_notes: list[Path] = []
    for src in [*obs_files, *nav_files]:
        copied_rinex.append(copy_file(src, rinex_out, overwrite=args.overwrite))
    for src in note_files:
        copied_notes.append(copy_file(src, notes_out, overwrite=args.overwrite))

    report_path = rinex_out / "import_report.txt"
    write_report(report_path, source_dir, base_name, copied_rinex, copied_notes)

    print(f"Imported base package: {source_dir}")
    print(f"Base name: {base_name}")
    print(f"RINEX directory: {rinex_out}")
    print(f"Notes directory: {notes_out}")
    print(f"Observation files: {len(obs_files)}")
    print(f"Navigation files: {len(nav_files)}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
