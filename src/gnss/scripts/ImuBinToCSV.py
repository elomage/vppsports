# palaist ar komandu: py BinToCSV.py brauciens_7.BIN -o output.csv
from __future__ import annotations
import argparse
import struct
import sys
from typing import BinaryIO, Iterator, Tuple


RECORD_STRUCT = struct.Struct("<Iiii")
RECORD_SIZE = RECORD_STRUCT.size


def iter_records(f: BinaryIO) -> Iterator[Tuple[int, int, int, int]]:
    while True:
        chunk = f.read(RECORD_SIZE)
        if not chunk:
            return
        if len(chunk) != RECORD_SIZE:
            raise ValueError(f"Trailing {len(chunk)} bytes (expected multiple of {RECORD_SIZE}).")
        ts_us, x, y, z = RECORD_STRUCT.unpack(chunk)
        yield ts_us, x, y, z


def raw_to_g(raw: int, sensitivity_ug_per_lsb: float) -> float:
    return (raw * sensitivity_ug_per_lsb) / 1_000_000.0


def main() -> int:
    ap = argparse.ArgumentParser(description="Decode packed SensorRecord .BIN to readable CSV-like text.")
    ap.add_argument("input", help="Input .BIN file (e.g. brauciens_7.BIN)")
    ap.add_argument("-o", "--output", default=None, help="Output text file (default: stdout)")
    ap.add_argument("--sens-x", type=float, default=19.5, help="X sensitivity in micro-g/LSB (default: 19.5)")
    ap.add_argument("--sens-y", type=float, default=19.5, help="Y sensitivity in micro-g/LSB (default: 19.5)")
    ap.add_argument("--sens-z", type=float, default=19.5, help="Z sensitivity in micro-g/LSB (default: 19.5)")
    ap.add_argument("--header", action="store_true", help="Include CSV header line")
    ap.add_argument("--delimiter", default=",", help="Delimiter (default: ',')")
    ap.add_argument("--limit", type=int, default=None, help="Decode only first N records (debug)")

    args = ap.parse_args()

    out = open(args.output, "w", newline="") if args.output else sys.stdout
    try:
        if args.header:
            out.write(f"seconds{args.delimiter}x_g{args.delimiter}y_g{args.delimiter}z_g\n")

        with open(args.input, "rb") as f:
            for i, (ts_us, x, y, z) in enumerate(iter_records(f), start=1):
                seconds = ts_us / 1_000_000.0
                x_g = raw_to_g(x, args.sens_x)
                y_g = raw_to_g(y, args.sens_y)
                z_g = raw_to_g(z, args.sens_z)

                out.write(
                    f"{seconds:.6f}{args.delimiter}"
                    f"{x_g:.6f}{args.delimiter}"
                    f"{y_g:.6f}{args.delimiter}"
                    f"{z_g:.6f}\n"
                )

                if args.limit is not None and i >= args.limit:
                    break
    finally:
        if out is not sys.stdout:
            out.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
