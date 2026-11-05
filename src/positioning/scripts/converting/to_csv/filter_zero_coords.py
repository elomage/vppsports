#!/usr/bin/env python3
from __future__ import annotations
import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from session_paths import find_csv_to_filter, output_subdir, resolve_session_dir

LAT_KEYS = ["lat", "latitude", "lat_deg", "latitude_deg"]
LON_KEYS = ["lon", "lng", "longitude", "lon_deg", "longitude_deg"]
X_KEYS = ["x_m", "x", "ecef_x", "ecef_x_m"]
Y_KEYS = ["y_m", "y", "ecef_y", "ecef_y_m"]
Z_KEYS = ["z_m", "z", "ecef_z", "ecef_z_m"]

def find_key(fieldnames, candidates):
    lookup = {f.lower(): f for f in fieldnames}
    for c in candidates:
        if c.lower() in lookup:
            return lookup[c.lower()]
    return None

def to_float(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None

def main():
    ap = argparse.ArgumentParser(description="Remove zero coordinate rows from CSV.")
    ap.add_argument("recording", help="Recording output directory, e.g. 20260421_213418Z_LOG00003")
    ap.add_argument("--csv", dest="csv_path", help="Optional explicit CSV file override")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    session_dir = resolve_session_dir(args.recording)
    csv_path = Path(args.csv_path) if args.csv_path else find_csv_to_filter(session_dir)
    output = Path(args.output) if args.output else output_subdir(session_dir, "csv") / f"{csv_path.stem}_filtered.csv"

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit("CSV has no header row")
        fieldnames = reader.fieldnames

        lat_key = find_key(fieldnames, LAT_KEYS)
        lon_key = find_key(fieldnames, LON_KEYS)
        x_key = find_key(fieldnames, X_KEYS)
        y_key = find_key(fieldnames, Y_KEYS)
        z_key = find_key(fieldnames, Z_KEYS)

        rows_kept = []
        rows_removed = 0

        for row in reader:
            remove = False

            if lat_key and lon_key:
                lat = to_float(row.get(lat_key))
                lon = to_float(row.get(lon_key))
                if lat == 0.0 and lon == 0.0:
                    remove = True

            if (not remove) and x_key and y_key and z_key:
                x = to_float(row.get(x_key))
                y = to_float(row.get(y_key))
                z = to_float(row.get(z_key))
                if x == 0.0 and y == 0.0 and z == 0.0:
                    remove = True

            if remove:
                rows_removed += 1
            else:
                rows_kept.append(row)

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_kept)

    print(f"Saved: {output}")
    print(f"Rows kept: {len(rows_kept)}")
    print(f"Rows removed: {rows_removed}")

if __name__ == "__main__":
    main()
