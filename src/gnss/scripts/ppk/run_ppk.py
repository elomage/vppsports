#!/usr/bin/env python3
"""
Run PPK for one archived rover recording using RTKLIB rnx2rtkp.

Usage:
  python scripts/ppk/run_ppk.py 20260503_132939Z_test_log_1 --base local_base_20260503
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "converting" / "to_csv"))

from session_paths import output_subdir, resolve_session_dir
from gnss_to_csv import convert_pos_to_csv

EXPECTED_RTKLIB_VERSION = "2.4.3 b34"
DEFAULT_CONFIG = ROOT / "config" / "ppk.yaml"
DEFAULT_ENV = ROOT / ".env"
BASE_RINEX_ROOT = ROOT / "base" / "rinex"
GPS_TO_UTC_OFFSET_S = 18
MODE_CONFIGS = {
    "dgps": ROOT / "config" / "rtklib_ppk_dgps.conf",
    "float": ROOT / "config" / "rtklib_ppk_float.conf",
    "fixed": ROOT / "config" / "rtklib_ppk_fixed.conf",
}
RUNNABLE_MODES = {"dgps", "float", "fixed", "configured"}
DEFAULT_ALL_MODES = [("fixed", True), ("float", False), ("dgps", False)]
SANITY_MAX_STEP_M = 100.0
SANITY_SPAN_M = 500.0

OBS_SUFFIXES = {".obs", ".o"}
NAV_SUFFIXES = {".nav", ".gnav", ".hnav", ".qnav", ".lnav", ".sp3", ".clk"}
RINEX_NAV_KIND_SUFFIXES = {"p", "n", "g", "c", "l"}


@dataclass(frozen=True)
class PpkConfig:
    version: str
    rnx2rtkp_exe: Path
    rtklib_config: Path
    solution_pos: str
    solution_csv: str
    report: str
    command: str
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RinexInputs:
    rover_obs: Path
    base_dir: Path
    base_obs: Path
    nav_files: list[Path]
    base_approx_xyz: tuple[float, float, float] | None


@dataclass(frozen=True)
class RinexTimeSpan:
    first: datetime | None
    last: datetime | None
    time_system: str | None


@dataclass(frozen=True)
class SolutionStats:
    rows: int
    total_distance_m: float
    max_step_m: float
    span_m: float


@dataclass(frozen=True)
class FilterResult:
    input_rows: int
    output_rows: int
    removed_before_receiver: int
    removed_after_receiver: int
    removed_far_from_receiver: int
    receiver_csv: Path | None


@dataclass(frozen=True)
class PpkOutputPaths:
    solution_pos: Path
    solution_csv: Path
    raw_solution_csv: Path
    command: Path
    stdout: Path
    stderr: Path
    report: Path


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def expand_env(value: str, source: Path) -> str:
    expanded = os.path.expandvars(value)
    if "$" in expanded or "%" in expanded:
        raise SystemExit(
            f"Unresolved environment variable in {source}: {value}\n"
            "Set it in .env or in your shell environment."
        )
    return expanded


def load_config(path: Path) -> PpkConfig:
    if not path.is_file():
        raise SystemExit(f"PPK config not found: {path}")

    raw = parse_simple_yaml(path)
    rtklib = raw.get("rtklib", {})
    outputs = raw.get("outputs", {})

    try:
        return PpkConfig(
            version=expand_env(str(rtklib["version"]), path),
            rnx2rtkp_exe=resolve_project_path(expand_env(str(rtklib["rnx2rtkp_exe"]), path)),
            rtklib_config=resolve_project_path(expand_env(str(rtklib["config_file"]), path)),
            solution_pos=str(outputs.get("solution_pos", "solution.pos")),
            solution_csv=str(outputs.get("solution_csv", "solution.csv")),
            report=str(outputs.get("report", "ppk_report.txt")),
            command=str(outputs.get("command", "rnx2rtkp_command.txt")),
            stdout=str(outputs.get("stdout", "rnx2rtkp_stdout.txt")),
            stderr=str(outputs.get("stderr", "rnx2rtkp_stderr.txt")),
        )
    except KeyError as exc:
        raise SystemExit(f"Missing required config key in {path}: {exc}") from exc


def config_with_rtklib_config(config: PpkConfig, rtklib_config: Path) -> PpkConfig:
    return PpkConfig(
        version=config.version,
        rnx2rtkp_exe=config.rnx2rtkp_exe,
        rtklib_config=resolve_project_path(rtklib_config),
        solution_pos=config.solution_pos,
        solution_csv=config.solution_csv,
        report=config.report,
        command=config.command,
        stdout=config.stdout,
        stderr=config.stderr,
    )


def output_paths_for_mode(ppk_dir: Path, config: PpkConfig, mode: str, primary: bool) -> PpkOutputPaths:
    if primary:
        return PpkOutputPaths(
            solution_pos=ppk_dir / config.solution_pos,
            solution_csv=ppk_dir / config.solution_csv,
            raw_solution_csv=ppk_dir / "solution_raw.csv",
            command=ppk_dir / config.command,
            stdout=ppk_dir / config.stdout,
            stderr=ppk_dir / config.stderr,
            report=ppk_dir / config.report,
        )
    suffix = mode.lower()
    return PpkOutputPaths(
        solution_pos=ppk_dir / f"solution_{suffix}.pos",
        solution_csv=ppk_dir / f"solution_{suffix}.csv",
        raw_solution_csv=ppk_dir / f"solution_{suffix}_raw.csv",
        command=ppk_dir / f"rnx2rtkp_command_{suffix}.txt",
        stdout=ppk_dir / f"rnx2rtkp_stdout_{suffix}.txt",
        stderr=ppk_dir / f"rnx2rtkp_stderr_{suffix}.txt",
        report=ppk_dir / f"ppk_report_{suffix}.txt",
    )


def parse_simple_yaml(path: Path) -> dict[str, dict[str, str]]:
    """Parse the simple two-level key/value YAML used by config/ppk.yaml."""
    data: dict[str, dict[str, str]] = {}
    current_section: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")) and line.endswith(":"):
            current_section = line[:-1].strip()
            data.setdefault(current_section, {})
            continue
        if current_section is None or ":" not in line:
            raise SystemExit(f"Unsupported config line in {path}: {raw_line}")

        key, value = line.split(":", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        data[current_section][key.strip()] = value

    return data


def expected_executable_name() -> str:
    return "rnx2rtkp.exe" if platform.system().lower() == "windows" else "rnx2rtkp"


def validate_rtklib(config: PpkConfig) -> list[str]:
    warnings: list[str] = []
    exe = config.rnx2rtkp_exe

    if config.version != EXPECTED_RTKLIB_VERSION:
        warnings.append(
            f"Configured RTKLIB version is {config.version!r}; expected {EXPECTED_RTKLIB_VERSION!r}."
        )

    if not exe.is_file():
        raise SystemExit(
            "RTKLIB solver executable not found.\n"
            f"Configured path: {exe}\n"
            "Point config/ppk.yaml rtklib.rnx2rtkp_exe to RTKLIB 2.4.3 b34's bin/rnx2rtkp.exe."
        )

    expected_name = expected_executable_name()
    if exe.name.lower() != expected_name.lower():
        raise SystemExit(
            f"Wrong RTKLIB executable name: {exe.name}\n"
            f"Expected: {expected_name}\n"
            "Use RTKLIB 2.4.3 b34's rnx2rtkp command-line solver."
        )

    if not config.rtklib_config.is_file():
        raise SystemExit(f"RTKLIB config file not found: {config.rtklib_config}")

    help_text = ""
    attempts = [
        [str(exe), "-h"],
        [str(exe)],
    ]
    last_error = None
    for cmd in attempts:
        try:
            completed = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
            help_text = (completed.stdout or "") + "\n" + (completed.stderr or "")
            lower_help = help_text.lower()
            if "rnx2rtkp" in lower_help or "rtklib" in lower_help or "no input file" in lower_help:
                return warnings
        except Exception as exc:  # subprocess errors should become a readable validation failure.
            last_error = exc

    raise SystemExit(
        "Could not validate rnx2rtkp help output.\n"
        f"Executable: {exe}\n"
        f"Last error: {last_error}\n"
        "Expected recognizable RTKLIB/rnx2rtkp help text from RTKLIB 2.4.3 b34."
    )


def read_header(path: Path) -> str:
    try:
        with path.open("r", encoding="ascii", errors="ignore") as file:
            return file.readline().upper()
    except OSError:
        return ""


def read_header_lines(path: Path) -> list[str]:
    lines: list[str] = []
    try:
        with path.open("r", encoding="ascii", errors="ignore") as file:
            for line in file:
                lines.append(line.rstrip("\n"))
                if "END OF HEADER" in line:
                    break
    except OSError:
        return []
    return lines


def read_approx_position_xyz(path: Path) -> tuple[float, float, float] | None:
    for line in read_header_lines(path):
        if "APPROX POSITION XYZ" not in line:
            continue
        try:
            return tuple(float(value) for value in line[:60].split()[:3])  # type: ignore[return-value]
        except ValueError:
            return None
    return None


def read_marker_name(path: Path) -> str | None:
    for line in read_header_lines(path):
        if "MARKER NAME" in line:
            marker = line[:60].strip()
            return marker or None
    return None


def parse_rinex_header_time(line: str) -> tuple[datetime, str | None] | None:
    fields = line[:60].split()
    if len(fields) < 6:
        return None
    try:
        year, month, day, hour, minute = (int(value) for value in fields[:5])
        second = float(fields[5])
    except ValueError:
        return None

    whole_second = int(second)
    microsecond = int(round((second - whole_second) * 1_000_000))
    if microsecond >= 1_000_000:
        whole_second += 1
        microsecond -= 1_000_000
    try:
        timestamp = datetime(year, month, day, hour, minute, whole_second, microsecond, tzinfo=timezone.utc)
    except ValueError:
        return None
    time_system = fields[6].upper() if len(fields) >= 7 else None
    return timestamp, time_system


def read_obs_time_span(path: Path) -> RinexTimeSpan:
    first: datetime | None = None
    last: datetime | None = None
    time_system: str | None = None
    for line in read_header_lines(path):
        if "TIME OF FIRST OBS" in line:
            parsed = parse_rinex_header_time(line)
            if parsed:
                first, time_system = parsed
        elif "TIME OF LAST OBS" in line:
            parsed = parse_rinex_header_time(line)
            if parsed:
                last, last_system = parsed
                time_system = time_system or last_system
    if first is not None and last is not None:
        return RinexTimeSpan(first, last, time_system)

    # Some imported base files omit TIME OF LAST OBS; use the last epoch record
    # as a practical fallback without parsing the full observation payload.
    try:
        with path.open("r", encoding="ascii", errors="ignore") as file:
            in_body = False
            for line in file:
                if not in_body:
                    if "END OF HEADER" in line:
                        in_body = True
                    continue
                if not line.startswith(">"):
                    continue
                parsed = parse_rinex_header_time(line[1:])
                if not parsed:
                    continue
                epoch_time, epoch_system = parsed
                first = first or epoch_time
                last = epoch_time
                time_system = time_system or epoch_system
    except OSError:
        pass
    return RinexTimeSpan(first, last, time_system)


def is_legacy_obs_suffix(path: Path) -> bool:
    suffix = path.suffix.lower()
    return len(suffix) == 4 and suffix[1:3].isdigit() and suffix[3] == "o"


def is_legacy_nav_suffix(path: Path) -> bool:
    suffix = path.suffix.lower()
    return len(suffix) == 4 and suffix[1:3].isdigit() and suffix[3] in RINEX_NAV_KIND_SUFFIXES


def is_obs_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    header = read_header(path)
    return (
        "OBSERVATION DATA" in header
        or suffix in OBS_SUFFIXES
        or is_legacy_obs_suffix(path)
    )


def is_nav_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    header = read_header(path)
    return (
        "NAVIGATION DATA" in header
        or suffix in NAV_SUFFIXES
        or is_legacy_nav_suffix(path)
    )


def sort_obs_key(path: Path) -> tuple[int, str]:
    suffix = path.suffix.lower()
    if is_legacy_obs_suffix(path):
        rank = 0
    elif suffix == ".obs":
        rank = 1
    elif suffix == ".rnx":
        rank = 2
    else:
        rank = 3
    return rank, path.name.lower()


def find_one_obs(directory: Path, label: str) -> Path:
    if not directory.is_dir():
        raise SystemExit(f"{label} RINEX directory not found: {directory}")
    candidates = sorted((path for path in directory.iterdir() if path.is_file() and is_obs_file(path)), key=sort_obs_key)
    if not candidates:
        raise SystemExit(
            f"No {label} observation RINEX file found in {directory}\n"
            "Expected .yyO, .obs, or OBSERVATION DATA .rnx file."
        )
    return candidates[0]


def find_nav_files(*directories: Path) -> list[Path]:
    seen: set[Path] = set()
    nav_files: list[Path] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file() or not is_nav_file(path):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            nav_files.append(path)
    return nav_files


def resolve_base_dir(value: str | Path) -> Path:
    path = Path(value)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(BASE_RINEX_ROOT / path)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise SystemExit(
        f"Base RINEX directory not found for {value!r}.\n"
        f"Expected base files under {BASE_RINEX_ROOT / str(value)}"
    )


def parse_base_selector(value: str) -> tuple[bool, str | None]:
    if value.lower() == "auto":
        return True, None
    for separator in ("|", ":"):
        prefix, found, station = value.partition(separator)
        if prefix.lower() == "auto" and found:
            station_filter = station.strip()
            if not station_filter:
                raise SystemExit("Use --base auto or --base auto|STATION/auto:STATION, with a non-empty station name.")
            return True, station_filter
    return False, None


def station_matches(base_dir: Path, base_obs: Path, station_filter: str | None) -> bool:
    if not station_filter:
        return True
    needle = station_filter.lower()
    values = [base_dir.name, read_marker_name(base_obs) or ""]
    return any(needle in value.lower() for value in values)


def overlap_seconds(a: RinexTimeSpan, b: RinexTimeSpan) -> float:
    if a.first is None or b.first is None:
        return 0.0
    a_last = a.last or a.first
    b_last = b.last or b.first
    start = max(a.first, b.first)
    end = min(a_last, b_last)
    return max(0.0, (end - start).total_seconds())


def format_span(span: RinexTimeSpan) -> str:
    first = span.first.isoformat() if span.first else "unknown"
    last = span.last.isoformat() if span.last else "unknown"
    system = f" {span.time_system}" if span.time_system else ""
    return f"{first} to {last}{system}"


def resolve_auto_base_dir(rover_obs: Path, station_filter: str | None) -> Path:
    if not BASE_RINEX_ROOT.is_dir():
        raise SystemExit(f"Base RINEX root not found: {BASE_RINEX_ROOT}")

    rover_span = read_obs_time_span(rover_obs)
    if rover_span.first is None:
        raise SystemExit(f"Could not read rover TIME OF FIRST OBS from {rover_obs}; cannot auto-select base.")

    matches: list[tuple[tuple[int, float, float, str], Path, Path, RinexTimeSpan]] = []
    scanned: list[str] = []
    for base_dir in sorted((path for path in BASE_RINEX_ROOT.iterdir() if path.is_dir()), key=lambda item: item.name.lower()):
        try:
            base_obs = find_one_obs(base_dir, "base")
        except SystemExit:
            continue
        if not station_matches(base_dir, base_obs, station_filter):
            continue

        base_span = read_obs_time_span(base_obs)
        scanned.append(f"{base_dir.name}: {format_span(base_span)}")
        overlap = overlap_seconds(rover_span, base_span)
        if overlap <= 0.0 or base_span.first is None:
            continue
        base_last = base_span.last or base_span.first
        covers_rover_start = int(base_span.first <= rover_span.first <= base_last)
        start_delta = abs((base_span.first - rover_span.first).total_seconds())
        score = (-covers_rover_start, -overlap, start_delta, base_dir.name.lower())
        matches.append((score, base_dir, base_obs, base_span))

    if not matches:
        filter_text = f" matching {station_filter!r}" if station_filter else ""
        scanned_text = "\n".join(f"  - {line}" for line in scanned) or "  none"
        raise SystemExit(
            f"No base RINEX directory{filter_text} overlaps rover time {format_span(rover_span)}.\n"
            f"Scanned base spans:\n{scanned_text}"
        )

    matches.sort(key=lambda item: item[0])
    best_score, best_dir, best_obs, best_span = matches[0]
    tied = [item for item in matches if item[0] == best_score]
    if len(tied) > 1:
        options = "\n".join(f"  - {base_dir.name}: {format_span(span)}" for _, base_dir, _, span in tied)
        raise SystemExit(
            "Auto base selection is ambiguous; pass an explicit --base name or use --base auto|STATION.\n"
            f"Rover time: {format_span(rover_span)}\n"
            f"Matching bases:\n{options}"
        )

    print(
        "Auto-selected base "
        f"{best_dir.name} ({best_obs.name}; {format_span(best_span)}) "
        f"for rover time {format_span(rover_span)}"
    )
    return best_dir.resolve()


def resolve_base_dir_for_rover(value: str, rover_session: Path) -> Path:
    auto, station_filter = parse_base_selector(value)
    if not auto:
        return resolve_base_dir(value)
    rover_obs = find_one_obs(rover_session / "rinex", "rover")
    return resolve_auto_base_dir(rover_obs, station_filter)


def discover_inputs(rover_session: Path, base_dir: Path) -> RinexInputs:
    rover_rinex_dir = rover_session / "rinex"
    rover_obs = find_one_obs(rover_rinex_dir, "rover")
    base_obs = find_one_obs(base_dir, "base")
    nav_files = find_nav_files(rover_rinex_dir, base_dir)
    if not nav_files:
        raise SystemExit(
            f"No navigation files found in rover/base RINEX directories:\n"
            f"  rover: {rover_rinex_dir}\n"
            f"  base:  {base_dir}"
        )
    return RinexInputs(
        rover_obs=rover_obs,
        base_dir=base_dir,
        base_obs=base_obs,
        nav_files=nav_files,
        base_approx_xyz=read_approx_position_xyz(base_obs),
    )


def command_to_text(command: Iterable[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    import shlex

    return " ".join(shlex.quote(part) for part in command)


def build_command(config: PpkConfig, inputs: RinexInputs, solution_pos: Path, extra_args: list[str]) -> list[str]:
    command = [
        str(config.rnx2rtkp_exe),
        "-k",
        str(config.rtklib_config),
    ]
    if inputs.base_approx_xyz is not None:
        command.extend(["-r", *(f"{value:.4f}" for value in inputs.base_approx_xyz)])
    command.extend([
        "-o",
        str(solution_pos),
        *extra_args,
        str(inputs.rover_obs),
        str(inputs.base_obs),
        *(str(path) for path in inputs.nav_files),
    ])
    return command


def distance_3d(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def assess_solution_csv(path: Path) -> tuple[SolutionStats | None, list[str]]:
    if not path.is_file():
        return None, [f"Solution CSV not found: {path}"]

    points: list[tuple[float, float, float]] = []
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        for row in reader:
            try:
                points.append((float(row["x"]), float(row["y"]), float(row["z"])))
            except (KeyError, TypeError, ValueError):
                continue

    if not points:
        return None, [f"No usable ECEF rows found in solution CSV: {path}"]

    total = sum(distance_3d(a, b) for a, b in zip(points, points[1:]))
    max_step = max((distance_3d(a, b) for a, b in zip(points, points[1:])), default=0.0)
    span = max((distance_3d(points[0], point) for point in points), default=0.0)
    stats = SolutionStats(
        rows=len(points),
        total_distance_m=total,
        max_step_m=max_step,
        span_m=span,
    )

    warnings: list[str] = []
    if max_step > SANITY_MAX_STEP_M:
        warnings.append(
            f"Suspicious PPK jump: max step is {max_step:.1f} m "
            f"(threshold {SANITY_MAX_STEP_M:.0f} m)."
        )
    if span > SANITY_SPAN_M:
        warnings.append(
            f"Suspicious PPK spread: path span is {span:.1f} m "
            f"(threshold {SANITY_SPAN_M:.0f} m)."
        )
    return stats, warnings


def parse_timestamp(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_receiver_points(rover_session: Path) -> tuple[Path | None, list[tuple[datetime, tuple[float, float, float]]]]:
    candidates = [
        rover_session / "csv" / "bestnavxyz_filtered.csv",
        rover_session / "csv" / "bestnavxyz.csv",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        points: list[tuple[datetime, tuple[float, float, float]]] = []
        with path.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                time = parse_timestamp(row.get("utc", "") or row.get("time", ""))
                if time is None:
                    continue
                try:
                    xyz = (float(row["x_m"]), float(row["y_m"]), float(row["z_m"]))
                except (KeyError, TypeError, ValueError):
                    continue
                points.append((time, xyz))
        if points:
            return path, points
    return None, []


def nearest_receiver(
    receiver_points: list[tuple[datetime, tuple[float, float, float]]],
    target_time: datetime,
    start_index: int,
) -> tuple[int, float]:
    best_index = min(start_index, len(receiver_points) - 1)
    best_delta = abs((receiver_points[best_index][0] - target_time).total_seconds())
    while best_index + 1 < len(receiver_points):
        delta = abs((receiver_points[best_index + 1][0] - target_time).total_seconds())
        if delta > best_delta:
            break
        best_index += 1
        best_delta = delta
    return best_index, best_delta


def filter_solution_csv(
    raw_csv: Path,
    filtered_csv: Path,
    rover_session: Path,
    max_receiver_time_delta_s: float = 0.35,
    max_receiver_distance_m: float = 25.0,
) -> FilterResult:
    receiver_csv, receiver_points = load_receiver_points(rover_session)
    if not receiver_points:
        shutil.copyfile(raw_csv, filtered_csv)
        return FilterResult(0, 0, 0, 0, 0, receiver_csv)

    receiver_start = receiver_points[0][0]
    receiver_end = receiver_points[-1][0]
    rows: list[dict[str, str]] = []
    fieldnames: list[str] = []
    with raw_csv.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    kept: list[dict[str, str]] = []
    removed_before = 0
    removed_after = 0
    removed_far = 0
    receiver_index = 0
    for row in rows:
        ppk_time = parse_timestamp(row.get("time", ""))
        if ppk_time is None:
            removed_far += 1
            continue
        ppk_utc = ppk_time - timedelta(seconds=GPS_TO_UTC_OFFSET_S)
        if ppk_utc < receiver_start - timedelta(seconds=max_receiver_time_delta_s):
            removed_before += 1
            continue
        if ppk_utc > receiver_end + timedelta(seconds=max_receiver_time_delta_s):
            removed_after += 1
            continue

        receiver_index, time_delta = nearest_receiver(receiver_points, ppk_utc, receiver_index)
        if time_delta <= max_receiver_time_delta_s:
            try:
                xyz = (float(row["x"]), float(row["y"]), float(row["z"]))
            except (KeyError, TypeError, ValueError):
                removed_far += 1
                continue
            if distance_3d(xyz, receiver_points[receiver_index][1]) > max_receiver_distance_m:
                removed_far += 1
                continue
        kept.append(row)

    if not kept:
        shutil.copyfile(raw_csv, filtered_csv)
        return FilterResult(len(rows), len(rows), removed_before, removed_after, removed_far, receiver_csv)

    filtered_csv.parent.mkdir(parents=True, exist_ok=True)
    with filtered_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)
    return FilterResult(len(rows), len(kept), removed_before, removed_after, removed_far, receiver_csv)


def write_report(
    path: Path,
    config: PpkConfig,
    mode: str,
    warnings: list[str],
    inputs: RinexInputs,
    command_text: str,
    returncode: int,
    solution_pos: Path,
    solution_csv: Path,
    solution_stats: SolutionStats | None = None,
    sanity_warnings: list[str] | None = None,
    filter_result: FilterResult | None = None,
    csv_error: str | None = None,
) -> None:
    lines = [
        f"Run time: {datetime.now().isoformat(timespec='seconds')}",
        f"RTKLIB version: {config.version}",
        f"RTKLIB executable: {config.rnx2rtkp_exe}",
        f"RTKLIB config: {config.rtklib_config}",
        f"PPK mode: {mode}",
        "",
        "Warnings:",
    ]
    lines.extend(f"  - {warning}" for warning in warnings)
    if not warnings:
        lines.append("  none")
    lines.extend([
        "",
        f"Rover OBS: {inputs.rover_obs}",
        f"Base directory: {inputs.base_dir}",
        f"Base OBS: {inputs.base_obs}",
        f"Base APPROX POSITION XYZ override: {inputs.base_approx_xyz or 'not found'}",
        "NAV files:",
    ])
    lines.extend(f"  - {path}" for path in inputs.nav_files)
    lines.extend([
        "",
        f"Command: {command_text}",
        f"Exit code: {returncode}",
        f"Solution POS: {solution_pos}",
        f"Solution CSV: {solution_csv}",
    ])
    if solution_stats:
        lines.extend([
            "",
            "Solution sanity:",
            f"  rows: {solution_stats.rows}",
            f"  total path: {solution_stats.total_distance_m:.3f} m",
            f"  max step: {solution_stats.max_step_m:.3f} m",
            f"  span from first point: {solution_stats.span_m:.3f} m",
        ])
    if sanity_warnings:
        lines.extend(["", "Sanity warnings:"])
        lines.extend(f"  - {warning}" for warning in sanity_warnings)
    if filter_result:
        lines.extend([
            "",
            "Solution filtering:",
            f"  receiver CSV: {filter_result.receiver_csv or 'not found'}",
            f"  input rows: {filter_result.input_rows}",
            f"  output rows: {filter_result.output_rows}",
            f"  removed before receiver time range: {filter_result.removed_before_receiver}",
            f"  removed after receiver time range: {filter_result.removed_after_receiver}",
            f"  removed far from receiver path: {filter_result.removed_far_from_receiver}",
        ])
    if csv_error:
        lines.extend(["", f"CSV conversion error: {csv_error}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_mode(
    mode: str,
    config: PpkConfig,
    inputs: RinexInputs,
    rover_session: Path,
    output_paths: PpkOutputPaths,
    extra_args: list[str],
) -> int:
    warnings = validate_rtklib(config)
    if mode == "dgps":
        warnings.append(
            "Mode 'dgps' is the less precise code-differential fallback. "
            "Use the fixed mode when carrier-phase PPK quality is acceptable."
        )
    elif mode == "float":
        warnings.append(
            "Mode 'float' is a carrier-phase kinematic fallback without ambiguity fixing. "
            "It can be useful when fixed PPK has too few accepted points."
        )
    for warning in warnings:
        print(f"WARNING [{mode}]: {warning}", file=sys.stderr)

    command = build_command(config, inputs, output_paths.solution_pos, extra_args)
    command_text = command_to_text(command)
    output_paths.command.write_text(command_text + "\n", encoding="utf-8")

    print(f"Running RTKLIB PPK ({mode}):")
    print(command_text)
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    output_paths.stdout.write_text(completed.stdout or "", encoding="utf-8", errors="ignore")
    output_paths.stderr.write_text(completed.stderr or "", encoding="utf-8", errors="ignore")

    csv_error = None
    solution_stats = None
    sanity_warnings: list[str] = []
    filter_result = None
    if completed.returncode == 0 and output_paths.solution_pos.is_file():
        try:
            convert_pos_to_csv(output_paths.solution_pos, output_paths.raw_solution_csv)
            filter_result = filter_solution_csv(output_paths.raw_solution_csv, output_paths.solution_csv, rover_session)
            solution_stats, sanity_warnings = assess_solution_csv(output_paths.solution_csv)
        except Exception as exc:
            csv_error = str(exc)

    write_report(
        output_paths.report,
        config=config,
        mode=mode,
        warnings=warnings,
        inputs=inputs,
        command_text=command_text,
        returncode=completed.returncode,
        solution_pos=output_paths.solution_pos,
        solution_csv=output_paths.solution_csv,
        solution_stats=solution_stats,
        sanity_warnings=sanity_warnings,
        filter_result=filter_result,
        csv_error=csv_error,
    )

    print(f"Exit code ({mode}): {completed.returncode}")
    print(f"Command ({mode}): {output_paths.command}")
    print(f"stdout ({mode}): {output_paths.stdout}")
    print(f"stderr ({mode}): {output_paths.stderr}")
    print(f"Report ({mode}): {output_paths.report}")

    if completed.returncode != 0:
        print(f"RTKLIB failed for {mode}. See stderr/stdout files in the ppk directory.", file=sys.stderr)
        return completed.returncode
    if not output_paths.solution_pos.is_file():
        print(f"RTKLIB finished for {mode} but did not create expected solution file: {output_paths.solution_pos}", file=sys.stderr)
        return 2
    if csv_error:
        print(f"RTKLIB created a {mode} solution file, but CSV conversion failed: {csv_error}", file=sys.stderr)
        return 3
    for warning in sanity_warnings:
        print(f"WARNING [{mode}]: {warning}", file=sys.stderr)
    if sanity_warnings:
        print(f"PPK {mode} solution failed sanity checks. See the report before using this path.", file=sys.stderr)
        return 4

    print(f"Solution POS ({mode}): {output_paths.solution_pos}")
    print(f"Solution CSV ({mode}): {output_paths.solution_csv}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RTKLIB PPK for one rover recording and one base station folder.")
    parser.add_argument("recording", help="Rover recording output directory, e.g. 20260503_132939Z_test_log_1")
    parser.add_argument(
        "--base",
        required=True,
        help=(
            "Base name under base/rinex/<base>, a full base RINEX directory path, "
            "or 'auto'/'auto|STATION'/'auto:STATION' to select by overlapping RINEX observation time."
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="PPK YAML config path.")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV, help="Environment file with local executable paths.")
    parser.add_argument("--rnx2rtkp", type=Path, help="Override RTKLIB 2.4.3 b34 rnx2rtkp executable path.")
    parser.add_argument("--rtklib-config", type=Path, help="Override RTKLIB .conf file path.")
    parser.add_argument(
        "--mode",
        choices=["all", "both", "dgps", "float", "fixed", "configured"],
        default="all",
        help=(
            "RTKLIB solution mode. Default 'all' calculates fixed kinematic PPK as the main "
            "solution, plus float kinematic and DGPS fallback solutions. 'both' is kept as an "
            "alias for fixed plus DGPS. Use 'fixed', 'float', or 'dgps' to run only one mode."
        ),
    )
    parser.add_argument("--extra-arg", action="append", default=[], help="Extra argument passed to rnx2rtkp. Repeat as needed.")
    args = parser.parse_args()

    load_env_file(resolve_project_path(args.env))
    base_config = load_config(resolve_project_path(args.config))
    if args.mode in {"all", "both"} and args.rtklib_config:
        raise SystemExit(f"--mode {args.mode} cannot be combined with --rtklib-config because it runs multiple RTKLIB configs.")
    config = base_config
    if args.mode in RUNNABLE_MODES and args.mode != "configured" and not args.rtklib_config:
        config = config_with_rtklib_config(config, MODE_CONFIGS[args.mode])
    if args.rnx2rtkp:
        config = PpkConfig(
            version=config.version,
            rnx2rtkp_exe=resolve_project_path(args.rnx2rtkp),
            rtklib_config=config.rtklib_config,
            solution_pos=config.solution_pos,
            solution_csv=config.solution_csv,
            report=config.report,
            command=config.command,
            stdout=config.stdout,
            stderr=config.stderr,
        )
    if args.rtklib_config:
        config = config_with_rtklib_config(config, args.rtklib_config)

    rover_session = resolve_session_dir(args.recording)
    base_dir = resolve_base_dir_for_rover(args.base, rover_session)
    ppk_dir = output_subdir(rover_session, "ppk")

    inputs = discover_inputs(rover_session, base_dir)
    if args.mode == "all":
        run_plan = DEFAULT_ALL_MODES
    elif args.mode == "both":
        run_plan = [("fixed", True), ("dgps", False)]
    else:
        run_plan = [(args.mode, True)]

    statuses: list[tuple[str, int]] = []
    for mode, primary in run_plan:
        mode_config = config
        if args.mode in {"all", "both"}:
            mode_config = config_with_rtklib_config(base_config, MODE_CONFIGS[mode])
            if args.rnx2rtkp:
                mode_config = PpkConfig(
                    version=mode_config.version,
                    rnx2rtkp_exe=resolve_project_path(args.rnx2rtkp),
                    rtklib_config=mode_config.rtklib_config,
                    solution_pos=mode_config.solution_pos,
                    solution_csv=mode_config.solution_csv,
                    report=mode_config.report,
                    command=mode_config.command,
                    stdout=mode_config.stdout,
                    stderr=mode_config.stderr,
                )
        outputs = output_paths_for_mode(ppk_dir, mode_config, mode, primary)
        statuses.append((mode, run_mode(mode, mode_config, inputs, rover_session, outputs, args.extra_arg)))

    print("PPK run summary:")
    for mode, status in statuses:
        label = "OK" if status == 0 else f"FAILED ({status})"
        print(f"  [{label}] {mode}")
    return 0 if all(status == 0 for _, status in statuses) else next(status for _, status in statuses if status != 0)


if __name__ == "__main__":
    raise SystemExit(main())
