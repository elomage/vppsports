#!/usr/bin/env python3
"""
Convert GNSS data to CSV with columns: time,x,y,z,direction

What this script can do
-----------------------
1. Try to extract position directly from a Unicore .BIN file *if* the file contains
   already-solved position/heading logs.
2. Run RTKLIB's rnx2rtkp on RINEX files (PPK/PPP workflow) and convert the resulting
   .pos file to CSV.
3. Convert an existing RTKLIB .pos file directly to CSV.

Important for your sample file
------------------------------
If the .BIN contains only raw observation messages (e.g. OBSVMCMP / OBSVHCMP), this
script will tell you that direct extraction is not possible. In that case, first convert
BIN -> RINEX with the receiver vendor's converter, then use this script with --rover-obs
(and optionally --base-obs) to run rnx2rtkp and export CSV.

Dependencies
------------
- Python 3.10+
- For direct Unicore BIN parsing: pip install pyunigps
- For RINEX processing: RTKLIB rnx2rtkp executable available on disk
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from session_paths import find_original_bin, output_subdir, resolve_session_dir

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)


@dataclass
class PointRow:
    time_iso: str
    x: float
    y: float
    z: float
    direction_deg: Optional[float]


def gpsweek_tow_ms_to_utc(week: int, tow_ms: int, leap_seconds: int = 18) -> datetime:
    gps_time = GPS_EPOCH + timedelta(weeks=week, milliseconds=tow_ms)
    return gps_time - timedelta(seconds=leap_seconds)


def llh_to_ecef(lat_deg: float, lon_deg: float, h_m: float) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + h_m) * cos_lat * cos_lon
    y = (n + h_m) * cos_lat * sin_lon
    z = (n * (1 - WGS84_E2) + h_m) * sin_lat
    return x, y, z


def ecef_to_llh(x: float, y: float, z: float) -> tuple[float, float, float]:
    b = WGS84_A * (1 - WGS84_F)
    ep2 = (WGS84_A**2 - b**2) / b**2
    p = math.hypot(x, y)
    th = math.atan2(WGS84_A * z, b * p)
    lon = math.atan2(y, x)
    lat = math.atan2(
        z + ep2 * b * math.sin(th) ** 3,
        p - WGS84_E2 * WGS84_A * math.cos(th) ** 3,
    )
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    h = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), h


def bearing_from_ecef(p1: tuple[float, float, float], p2: tuple[float, float, float]) -> Optional[float]:
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    if (x1, y1, z1) == (x2, y2, z2):
        return None

    lat0_deg, lon0_deg, _ = ecef_to_llh(x1, y1, z1)
    lat0 = math.radians(lat0_deg)
    lon0 = math.radians(lon0_deg)

    dx = x2 - x1
    dy = y2 - y1
    dz = z2 - z1

    east = -math.sin(lon0) * dx + math.cos(lon0) * dy
    north = (
        -math.sin(lat0) * math.cos(lon0) * dx
        - math.sin(lat0) * math.sin(lon0) * dy
        + math.cos(lat0) * dz
    )

    if abs(east) < 1e-9 and abs(north) < 1e-9:
        return None
    return (math.degrees(math.atan2(east, north)) + 360.0) % 360.0


def write_csv(rows: Iterable[PointRow], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "x", "y", "z", "direction"])
        for row in rows:
            direction = "" if row.direction_deg is None else f"{row.direction_deg:.3f}"
            w.writerow([
                row.time_iso,
                f"{row.x:.4f}",
                f"{row.y:.4f}",
                f"{row.z:.4f}",
                direction,
            ])


# ----------------------------
# Direct Unicore BIN handling
# ----------------------------

def _safe_get(obj, *names):
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


DIRECT_POSITION_HINTS = {
    # Preferred direct Cartesian logs
    "BESTXYZ",
    "MATCHEDXYZ",
    "RTKXYZ",
    # Common lat/lon/heading style logs
    "BESTPOS",
    "MATCHEDPOS",
    "INSPVA",
    "INSPVAX",
    "INSPVAA",
    "PVTSLN",
    "HEADING",
    "UNIHEADING",
}


def extract_direct_from_unicore_bin(bin_path: Path, csv_path: Path) -> bool:
    try:
        from pyunigps import ERR_IGNORE, UNIReader
    except ImportError:
        print(
            "Direct .BIN parsing requires 'pyunigps'. Install it with: pip install pyunigps",
            file=sys.stderr,
        )
        return False

    rows: list[PointRow] = []
    identities: dict[str, int] = {}
    last_xyz: Optional[tuple[float, float, float]] = None

    with bin_path.open("rb") as f:
        reader = UNIReader(f, quitonerror=ERR_IGNORE)
        for _, msg in reader:
            identity = str(getattr(msg, "identity", "UNKNOWN"))
            identities[identity] = identities.get(identity, 0) + 1

            week = _safe_get(msg, "wno", "week", "gpsweek")
            tow = _safe_get(msg, "tow", "towms", "ms")
            leap = _safe_get(msg, "leapsecond", "leapsec")
            if week is None or tow is None:
                continue

            # Try Cartesian first
            x = _safe_get(msg, "x", "ecefx", "ecef_x")
            y = _safe_get(msg, "y", "ecefy", "ecef_y")
            z = _safe_get(msg, "z", "ecefz", "ecef_z")

            # If not available, try geodetic and convert to ECEF
            if x is None or y is None or z is None:
                lat = _safe_get(msg, "lat", "latitude")
                lon = _safe_get(msg, "lon", "longitude")
                h = _safe_get(msg, "hgt", "height", "alt", "altitude", "undulation")
                if lat is not None and lon is not None:
                    x, y, z = llh_to_ecef(float(lat), float(lon), float(h or 0.0))
                else:
                    continue

            utc = gpsweek_tow_ms_to_utc(int(week), int(tow), int(leap or 18))
            xyz = (float(x), float(y), float(z))

            # Prefer a heading field if present; otherwise infer from motion.
            heading = _safe_get(msg, "heading", "azimuth", "track", "yaw", "direction")
            direction = float(heading) if heading is not None else None
            if direction is None and last_xyz is not None:
                direction = bearing_from_ecef(last_xyz, xyz)

            rows.append(PointRow(utc.isoformat(), xyz[0], xyz[1], xyz[2], direction))
            last_xyz = xyz

    if rows:
        write_csv(rows, csv_path)
        print(f"Wrote {len(rows)} rows to {csv_path}")
        return True

    print("No directly usable position logs found in the Unicore BIN.", file=sys.stderr)
    if identities:
        print("Messages present in file:", file=sys.stderr)
        for name, count in sorted(identities.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {name}: {count}", file=sys.stderr)
    print(
        "This usually means the BIN contains raw observations only and must be converted to RINEX first.",
        file=sys.stderr,
    )
    return False


# ----------------------------
# RTKLIB helpers
# ----------------------------

def find_rnx2rtkp(explicit: Optional[str]) -> str:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"rnx2rtkp not found: {explicit}")

    found = shutil.which("rnx2rtkp")
    if found:
        return found

    raise FileNotFoundError(
        "Could not find rnx2rtkp. Pass --rnx2rtkp with the full path, for example: "
        r'--rnx2rtkp "C:\RTKLIB\bin\rnx2rtkp.exe"'
    )


def run_rnx2rtkp(
    rnx2rtkp_exe: str,
    rover_obs: Path,
    nav_files: list[Path],
    out_pos: Path,
    config_path: Optional[Path] = None,
    base_obs: Optional[Path] = None,
    extra_args: Optional[list[str]] = None,
) -> None:
    cmd = [rnx2rtkp_exe]

    if config_path is not None:
        cmd += ["-k", str(config_path)]

    cmd += ["-o", str(out_pos)]

    if extra_args:
        cmd += extra_args

    cmd.append(str(rover_obs))
    for nav in nav_files:
        cmd.append(str(nav))
    if base_obs is not None:
        cmd.append(str(base_obs))

    print("Running:", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    subprocess.run(cmd, check=True)


# ----------------------------
# RTKLIB .pos -> CSV
# ----------------------------

def parse_rtklib_pos(pos_path: Path) -> list[PointRow]:
    rows: list[PointRow] = []
    last_xyz: Optional[tuple[float, float, float]] = None
    mode = None  # 'xyz' or 'llh'

    header_re_xyz = re.compile(r"x-ecef|x/y/z", re.IGNORECASE)
    header_re_llh = re.compile(r"latitude|lat/lon/height|lat\(deg\)", re.IGNORECASE)

    with pos_path.open("r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("%"):
                if header_re_xyz.search(line):
                    mode = "xyz"
                elif header_re_llh.search(line):
                    mode = "llh"
                continue

            parts = line.split()
            if len(parts) < 5:
                continue

            # Most RTKLIB formats start with date and time, then 3 coordinates.
            date_s = parts[0]
            time_s = parts[1]
            try:
                dt = datetime.fromisoformat(f"{date_s}T{time_s.replace(' ', '')}")
            except ValueError:
                # fallback: RTKLIB sometimes uses slashes in date; fromisoformat won't like it
                try:
                    dt = datetime.strptime(f"{date_s} {time_s}", "%Y/%m/%d %H:%M:%S.%f")
                except ValueError:
                    try:
                        dt = datetime.strptime(f"{date_s} {time_s}", "%Y/%m/%d %H:%M:%S")
                    except ValueError:
                        continue

            try:
                c1 = float(parts[2])
                c2 = float(parts[3])
                c3 = float(parts[4])
            except ValueError:
                continue

            # Auto-detect if no useful header was present
            local_mode = mode
            if local_mode is None:
                # latitude is bounded; ECEF X isn't
                if abs(c1) <= 90.0 and abs(c2) <= 180.0:
                    local_mode = "llh"
                else:
                    local_mode = "xyz"

            if local_mode == "llh":
                x, y, z = llh_to_ecef(c1, c2, c3)
            else:
                x, y, z = c1, c2, c3

            xyz = (x, y, z)
            direction = bearing_from_ecef(last_xyz, xyz) if last_xyz is not None else None
            rows.append(PointRow(dt.isoformat(), x, y, z, direction))
            last_xyz = xyz

    if not rows:
        raise ValueError(f"No solution rows could be parsed from {pos_path}")
    return rows


def convert_pos_to_csv(pos_path: Path, csv_path: Path) -> None:
    rows = parse_rtklib_pos(pos_path)
    write_csv(rows, csv_path)
    print(f"Wrote {len(rows)} rows to {csv_path}")


# ----------------------------
# CLI
# ----------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Convert GNSS data to CSV: time,x,y,z,direction")

    p.add_argument("recording", nargs="?", help="Recording output directory, e.g. 20260421_213418Z_LOG00003")
    p.add_argument("--bin", dest="bin_path", help="Unicore .BIN file")
    p.add_argument("--pos-in", dest="pos_in", help="Existing RTKLIB .pos file")
    p.add_argument("--csv-out", help="Output CSV path")

    # RINEX / RTKLIB path
    p.add_argument("--rover-obs", help="Rover observation RINEX (.obs/.o)")
    p.add_argument("--base-obs", help="Base observation RINEX (.obs/.o) for PPK")
    p.add_argument(
        "--nav",
        action="append",
        default=[],
        help="Navigation / auxiliary files for rnx2rtkp (.nav, .gnav, .hnav, .sp3, .clk, etc.). Repeat as needed.",
    )
    p.add_argument("--rnx2rtkp", help="Full path to rnx2rtkp executable")
    p.add_argument("--config", help="RTKLIB config file (.conf)")
    p.add_argument("--pos-out", help="Optional path for intermediate RTKLIB .pos output")
    p.add_argument(
        "--extra-rnx2rtkp-arg",
        action="append",
        default=[],
        help="Extra argument to pass through to rnx2rtkp. Repeat as needed.",
    )

    return p


def find_rinex_file(rinex_dir: Path, suffixes: set[str], description: str) -> Path:
    candidates = []
    if rinex_dir.is_dir():
        for path in rinex_dir.iterdir():
            lower_name = path.name.lower()
            lower_suffix = path.suffix.lower()
            if path.is_file() and (lower_suffix in suffixes or any(lower_name.endswith(s) for s in suffixes)):
                candidates.append(path)
    if not candidates:
        raise SystemExit(f"No {description} found in {rinex_dir}")
    return sorted(candidates)[0]


def find_nav_files(rinex_dir: Path) -> list[Path]:
    suffixes = {".nav", ".gnav", ".hnav", ".qnav", ".lnav", ".rnx", ".sp3", ".clk"}
    if not rinex_dir.is_dir():
        return []
    return sorted(path for path in rinex_dir.iterdir() if path.is_file() and path.suffix.lower() in suffixes)


def main() -> int:
    args = build_arg_parser().parse_args()
    session_dir = resolve_session_dir(args.recording) if args.recording else None
    csv_out = Path(args.csv_out) if args.csv_out else (
        output_subdir(session_dir, "csv") / "gnss_solution.csv" if session_dir else None
    )
    if csv_out is None:
        print("Nothing to do. Pass a recording output directory or --csv-out.", file=sys.stderr)
        return 1

    if session_dir and not args.bin_path and not args.pos_in and not args.rover_obs:
        args.bin_path = str(find_original_bin(session_dir))

    rinex_dir = session_dir / "rinex" if session_dir else None
    if session_dir and args.rover_obs is None and not args.bin_path and rinex_dir:
        args.rover_obs = str(find_rinex_file(rinex_dir, {".obs", ".o", ".26o", ".25o", ".24o"}, "rover observation RINEX file"))
    if session_dir and not args.nav and rinex_dir:
        args.nav = [str(path) for path in find_nav_files(rinex_dir)]
    if session_dir and not args.pos_out:
        args.pos_out = str(output_subdir(session_dir, "other") / "rtklib_solution.pos")

    # 1) Existing .pos -> csv
    if args.pos_in:
        convert_pos_to_csv(Path(args.pos_in), csv_out)
        return 0

    # 2) Try direct BIN extraction first, if provided
    if args.bin_path and not args.rover_obs:
        ok = extract_direct_from_unicore_bin(Path(args.bin_path), csv_out)
        return 0 if ok else 2

    # 3) RINEX -> rnx2rtkp -> .pos -> csv
    if args.rover_obs:
        rover_obs = Path(args.rover_obs)
        base_obs = Path(args.base_obs) if args.base_obs else None
        nav_files = [Path(x) for x in args.nav]
        config = Path(args.config) if args.config else None
        out_pos = Path(args.pos_out) if args.pos_out else csv_out.with_suffix(".pos")

        rnx2rtkp = find_rnx2rtkp(args.rnx2rtkp)
        run_rnx2rtkp(
            rnx2rtkp_exe=rnx2rtkp,
            rover_obs=rover_obs,
            nav_files=nav_files,
            out_pos=out_pos,
            config_path=config,
            base_obs=base_obs,
            extra_args=args.extra_rnx2rtkp_arg,
        )
        convert_pos_to_csv(out_pos, csv_out)
        return 0

    print(
        "Nothing to do. Use one of:\n"
        "  20260421_213115Z_LOG00002\n"
        "  --pos-in solution.pos --csv-out out.csv\n"
        "  --rover-obs rover.obs --nav rover.nav --csv-out out.csv [--base-obs base.obs] [--rnx2rtkp path]",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
