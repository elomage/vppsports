
#!/usr/bin/env python3
"""
Extract selected human-readable CSV files from Unicore N4 binary logs.

Supported today:
- BESTNAVXYZB   (message ID 240): ECEF position + ECEF velocity
- UNIHEADINGB   (message ID 972): heading / pitch / baseline length
- Generic frame index for every detected binary message

Outputs:
- message_summary.csv
- records_index.csv
- bestnavxyz.csv                  (if message 240 exists)
- uniheading.csv                  (if message 972 exists)
- location_heading_xyz.csv        (if both 240 and 972 exist)

Usage:
    python scripts/converting/to_csv/unicore_n4_extract.py 20260421_213418Z_LOG00003
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from session_paths import find_original_bin, output_subdir, resolve_session_dir

SYNC = b"\xAA\x44\xB5"
HEADER_LEN = 24
CRC_LEN = 4

# Based on the Unicore N4 reference manual for the logs used here.
MESSAGE_NAMES = {
    218: "HWSTATUS",
    220: "SATELLITE_OR_STATUS_220",
    240: "BESTNAVXYZ",
    242: "BESTNAVXYZH",
    509: "MSG_509",
    511: "MSG_511",
    972: "UNIHEADING",
}

# Partial enum maps used by the current file and common logs.
SOLUTION_STATUS = {
    0: "SOL_COMPUTED",
    1: "INSUFFICIENT_OBS",
}
POSITION_OR_VELOCITY_TYPE = {
    0: "NONE",
    1: "FIXEDPOS",
    2: "FIXEDHEIGHT",
    8: "DOPPLER_VELOCITY",
    16: "SINGLE",
    17: "PSRDIFF",
    18: "SBAS",
    32: "L1_FLOAT",
    33: "IONOFREE_FLOAT",
    34: "NARROW_FLOAT",
    48: "L1_INT",
    49: "WIDE_INT",
    50: "NARROW_INT",
    68: "PPP",
    69: "INS",
}


def gps_to_utc(week: int, ms: int, leap_seconds: int) -> dt.datetime:
    gps_epoch = dt.datetime(1980, 1, 6, tzinfo=dt.timezone.utc)
    return gps_epoch + dt.timedelta(weeks=week, milliseconds=ms, seconds=-leap_seconds)


def isoformat_z(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def decode_str4(raw: bytes) -> str:
    return raw.decode("ascii", errors="replace").rstrip("\x00").strip()


def iter_n4_frames(blob: bytes) -> Iterator[dict]:
    i = 0
    n = len(blob)
    while i <= n - (HEADER_LEN + CRC_LEN):
        if blob[i:i+3] != SYNC:
            i += 1
            continue

        try:
            cpu_idle = blob[i + 3]
            message_id = struct.unpack_from("<H", blob, i + 4)[0]
            message_len = struct.unpack_from("<H", blob, i + 6)[0]
            time_ref = blob[i + 8]
            time_status = blob[i + 9]
            week = struct.unpack_from("<H", blob, i + 10)[0]
            ms = struct.unpack_from("<I", blob, i + 12)[0]
            version = struct.unpack_from("<I", blob, i + 16)[0]
            reserved = blob[i + 20]
            leap_seconds = blob[i + 21]
            delay_ms = struct.unpack_from("<H", blob, i + 22)[0]
            total_len = HEADER_LEN + message_len + CRC_LEN

            if i + total_len > n:
                i += 1
                continue

            payload = blob[i + HEADER_LEN:i + HEADER_LEN + message_len]
            crc32 = struct.unpack_from("<I", blob, i + HEADER_LEN + message_len)[0]

            yield {
                "file_offset": i,
                "cpu_idle": cpu_idle,
                "message_id": message_id,
                "message_name": MESSAGE_NAMES.get(message_id, f"MSG_{message_id}"),
                "message_len": message_len,
                "time_ref": time_ref,
                "time_status": time_status,
                "week": week,
                "ms": ms,
                "version": version,
                "reserved": reserved,
                "leap_seconds": leap_seconds,
                "delay_ms": delay_ms,
                "utc": gps_to_utc(week, ms, leap_seconds),
                "payload": payload,
                "crc32_le": crc32,
                "total_len": total_len,
            }
            i += total_len
        except Exception:
            # If the candidate sync is a false positive, advance by one byte.
            i += 1


def decode_bestnavxyz(frame: dict) -> Optional[dict]:
    payload = frame["payload"]
    if len(payload) < 112:
        return None
    pos_sol_status = struct.unpack_from("<I", payload, 0)[0]
    pos_type = struct.unpack_from("<I", payload, 4)[0]
    x = struct.unpack_from("<d", payload, 8)[0]
    y = struct.unpack_from("<d", payload, 16)[0]
    z = struct.unpack_from("<d", payload, 24)[0]
    x_sigma = struct.unpack_from("<f", payload, 32)[0]
    y_sigma = struct.unpack_from("<f", payload, 36)[0]
    z_sigma = struct.unpack_from("<f", payload, 40)[0]
    vel_sol_status = struct.unpack_from("<I", payload, 44)[0]
    vel_type = struct.unpack_from("<I", payload, 48)[0]
    vx = struct.unpack_from("<d", payload, 52)[0]
    vy = struct.unpack_from("<d", payload, 60)[0]
    vz = struct.unpack_from("<d", payload, 68)[0]
    vx_sigma = struct.unpack_from("<f", payload, 76)[0]
    vy_sigma = struct.unpack_from("<f", payload, 80)[0]
    vz_sigma = struct.unpack_from("<f", payload, 84)[0]
    stn_id = decode_str4(payload[88:92])
    v_latency = struct.unpack_from("<f", payload, 92)[0]
    diff_age = struct.unpack_from("<f", payload, 96)[0]
    sol_age = struct.unpack_from("<f", payload, 100)[0]
    svs = payload[104]
    soln_svs = payload[105]
    l1_svs = payload[106]
    multi_svs = payload[107]
    ext_sol_stat = payload[109] if len(payload) > 109 else None
    gal_bds3_sig_mask = payload[110] if len(payload) > 110 else None
    gps_glo_bds2_sig_mask = payload[111] if len(payload) > 111 else None

    return {
        "utc": isoformat_z(frame["utc"]),
        "gps_week": frame["week"],
        "gps_ms": frame["ms"],
        "file_offset": frame["file_offset"],
        "message_id": frame["message_id"],
        "message_name": frame["message_name"],
        "position_solution_status": SOLUTION_STATUS.get(pos_sol_status, pos_sol_status),
        "position_solution_status_raw": pos_sol_status,
        "position_type": POSITION_OR_VELOCITY_TYPE.get(pos_type, pos_type),
        "position_type_raw": pos_type,
        "x_m": x,
        "y_m": y,
        "z_m": z,
        "x_sigma_m": x_sigma,
        "y_sigma_m": y_sigma,
        "z_sigma_m": z_sigma,
        "velocity_solution_status": SOLUTION_STATUS.get(vel_sol_status, vel_sol_status),
        "velocity_solution_status_raw": vel_sol_status,
        "velocity_type": POSITION_OR_VELOCITY_TYPE.get(vel_type, vel_type),
        "velocity_type_raw": vel_type,
        "vx_mps": vx,
        "vy_mps": vy,
        "vz_mps": vz,
        "vx_sigma_mps": vx_sigma,
        "vy_sigma_mps": vy_sigma,
        "vz_sigma_mps": vz_sigma,
        "station_id": stn_id,
        "velocity_latency_s": v_latency,
        "differential_age_s": diff_age,
        "solution_age_s": sol_age,
        "satellites_tracked": svs,
        "satellites_used": soln_svs,
        "l1_g1_b1_used": l1_svs,
        "multi_freq_used": multi_svs,
        "ext_solution_status": ext_sol_stat,
        "galileo_bds3_sig_mask": gal_bds3_sig_mask,
        "gps_glonass_bds2_sig_mask": gps_glo_bds2_sig_mask,
    }


def decode_uniheading(frame: dict) -> Optional[dict]:
    payload = frame["payload"]
    if len(payload) < 44:
        return None
    sol_status = struct.unpack_from("<I", payload, 0)[0]
    pos_type = struct.unpack_from("<I", payload, 4)[0]
    baseline_len = struct.unpack_from("<f", payload, 8)[0]
    heading = struct.unpack_from("<f", payload, 12)[0]
    pitch = struct.unpack_from("<f", payload, 16)[0]
    reserved_float = struct.unpack_from("<f", payload, 20)[0]
    heading_stddev = struct.unpack_from("<f", payload, 24)[0]
    pitch_stddev = struct.unpack_from("<f", payload, 28)[0]
    stn_id = decode_str4(payload[32:36])
    svs = payload[36]
    soln_svs = payload[37]
    obs_svs = payload[38]
    multi_svs = payload[39]
    ext_sol_stat = payload[41] if len(payload) > 41 else None
    gal_bds3_sig_mask = payload[42] if len(payload) > 42 else None
    gps_glo_bds2_sig_mask = payload[43] if len(payload) > 43 else None

    return {
        "utc": isoformat_z(frame["utc"]),
        "gps_week": frame["week"],
        "gps_ms": frame["ms"],
        "file_offset": frame["file_offset"],
        "message_id": frame["message_id"],
        "message_name": frame["message_name"],
        "solution_status": SOLUTION_STATUS.get(sol_status, sol_status),
        "solution_status_raw": sol_status,
        "position_type": POSITION_OR_VELOCITY_TYPE.get(pos_type, pos_type),
        "position_type_raw": pos_type,
        "baseline_length_m": baseline_len,
        "heading_deg": heading,
        "pitch_deg": pitch,
        "reserved_float": reserved_float,
        "heading_stddev_deg": heading_stddev,
        "pitch_stddev_deg": pitch_stddev,
        "station_id": stn_id,
        "satellites_tracked": svs,
        "satellites_used": soln_svs,
        "satellites_above_mask": obs_svs,
        "satellites_multi_freq": multi_svs,
        "ext_solution_status": ext_sol_stat,
        "galileo_bds3_sig_mask": gal_bds3_sig_mask,
        "gps_glonass_bds2_sig_mask": gps_glo_bds2_sig_mask,
    }


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_index_rows(frames: List[dict]) -> List[dict]:
    rows = []
    for idx, frame in enumerate(frames):
        rows.append({
            "sequence": idx,
            "utc": isoformat_z(frame["utc"]),
            "gps_week": frame["week"],
            "gps_ms": frame["ms"],
            "file_offset": frame["file_offset"],
            "message_id": frame["message_id"],
            "message_name": frame["message_name"],
            "message_len": frame["message_len"],
            "total_len": frame["total_len"],
            "cpu_idle": frame["cpu_idle"],
            "time_ref": frame["time_ref"],
            "time_status": frame["time_status"],
            "version": frame["version"],
            "leap_seconds": frame["leap_seconds"],
            "delay_ms": frame["delay_ms"],
            "crc32_le_hex": f"0x{frame['crc32_le']:08X}",
            "payload_preview_hex": frame["payload"][:24].hex(),
        })
    return rows


def build_summary_rows(frames: List[dict]) -> List[dict]:
    by_id: Dict[int, List[dict]] = defaultdict(list)
    for frame in frames:
        by_id[frame["message_id"]].append(frame)

    rows = []
    for message_id in sorted(by_id):
        group = by_id[message_id]
        rows.append({
            "message_id": message_id,
            "message_name": group[0]["message_name"],
            "count": len(group),
            "payload_length_min": min(f["message_len"] for f in group),
            "payload_length_max": max(f["message_len"] for f in group),
            "first_utc": isoformat_z(group[0]["utc"]),
            "last_utc": isoformat_z(group[-1]["utc"]),
            "first_file_offset": group[0]["file_offset"],
            "last_file_offset": group[-1]["file_offset"],
        })
    return rows


def merge_location_heading(best_rows: List[dict], heading_rows: List[dict]) -> List[dict]:
    heading_by_key = {(r["gps_week"], r["gps_ms"]): r for r in heading_rows}
    merged = []
    for b in best_rows:
        h = heading_by_key.get((b["gps_week"], b["gps_ms"]))
        row = {
            "utc": b["utc"],
            "gps_week": b["gps_week"],
            "gps_ms": b["gps_ms"],
            "x_m": b["x_m"],
            "y_m": b["y_m"],
            "z_m": b["z_m"],
            "heading_deg": h["heading_deg"] if h else "",
            "pitch_deg": h["pitch_deg"] if h else "",
            "baseline_length_m": h["baseline_length_m"] if h else "",
            "position_solution_status": b["position_solution_status"],
            "position_type": b["position_type"],
            "heading_solution_status": h["solution_status"] if h else "",
            "heading_position_type": h["position_type"] if h else "",
            "satellites_used_position": b["satellites_used"],
            "satellites_used_heading": h["satellites_used"] if h else "",
            "vx_mps": b["vx_mps"],
            "vy_mps": b["vy_mps"],
            "vz_mps": b["vz_mps"],
        }
        merged.append(row)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract human-readable CSV from Unicore N4 binary logs.")
    parser.add_argument("recording", help="Recording output directory, e.g. 20260421_213418Z_LOG00003")
    parser.add_argument("--input", help="Optional explicit .BIN file override")
    parser.add_argument("--outdir", help="Optional explicit output directory override")
    args = parser.parse_args()

    session_dir = resolve_session_dir(args.recording)
    input_path = Path(args.input) if args.input else find_original_bin(session_dir)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    outdir = Path(args.outdir) if args.outdir else output_subdir(session_dir, "csv")
    outdir.mkdir(parents=True, exist_ok=True)

    blob = input_path.read_bytes()
    frames = list(iter_n4_frames(blob))
    if not frames:
        raise SystemExit("No Unicore N4 binary frames detected.")

    index_rows = build_index_rows(frames)
    summary_rows = build_summary_rows(frames)
    write_csv(outdir / "records_index.csv", index_rows)
    write_csv(outdir / "message_summary.csv", summary_rows)

    best_rows = []
    heading_rows = []

    for frame in frames:
        if frame["message_id"] == 240:
            rec = decode_bestnavxyz(frame)
            if rec:
                best_rows.append(rec)
        elif frame["message_id"] == 972:
            rec = decode_uniheading(frame)
            if rec:
                heading_rows.append(rec)

    if best_rows:
        write_csv(outdir / "bestnavxyz.csv", best_rows)
    if heading_rows:
        write_csv(outdir / "uniheading.csv", heading_rows)
    if best_rows and heading_rows:
        write_csv(outdir / "location_heading_xyz.csv", merge_location_heading(best_rows, heading_rows))

    print(f"Input: {input_path}")
    print(f"Frames found: {len(frames)}")
    print(f"Output directory: {outdir}")
    print("Created:")
    for name in [
        "message_summary.csv",
        "records_index.csv",
        "bestnavxyz.csv",
        "uniheading.csv",
        "location_heading_xyz.csv",
    ]:
        p = outdir / name
        if p.exists():
            print(f"  - {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
