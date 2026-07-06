#!/usr/bin/env python3
"""
trim_unicore_complete_packets.py

Converts a raw Unicore/UM982 recording into a cleaner BIN file containing only
complete binary packets.

It supports the two binary packet headers seen in LOG00001.BIN:
  1) AA 44 12  - legacy/OEM-style binary header, used by RANGECMPB
  2) AA 44 B5  - Unicore N4 binary header, used by BESTNAVXYZB and ephemerides

For LOG00001.BIN this removes:
  - the small ASCII preamble at the beginning, e.g. "$devicename,COM2*64"
  - the incomplete final packet at the end
  - any corrupted/invalid packets if CRC checking is enabled

Usage:
  python trim_unicore_complete_packets.py 20260421_212949Z_LOG00001
  python trim_unicore_complete_packets.py 20260421_212949Z_LOG00001 --no-crc
"""

from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from session_paths import find_original_bin, output_subdir, resolve_session_dir


SYNC_OEM = b"\xAA\x44\x12"
SYNC_N4 = b"\xAA\x44\xB5"


def unicore_crc32(data: bytes) -> int:
    """
    CRC-32 used by NovAtel/Unicore binary logs.

    Important: this is NOT Python's binascii.crc32 result.
    Initial value is 0, polynomial is 0xEDB88320, no final XOR.
    """
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
            crc &= 0xFFFFFFFF
    return crc


def find_next_sync(buf: bytes, start: int) -> int:
    """Find the next supported binary sync sequence."""
    p1 = buf.find(SYNC_OEM, start)
    p2 = buf.find(SYNC_N4, start)

    found = [p for p in (p1, p2) if p != -1]
    return min(found) if found else -1


def parse_packet_length(buf: bytes, pos: int) -> tuple[str, int, int, int] | None:
    """
    Return (packet_type, message_id, payload_length, total_packet_length)
    or None if there is no supported header at pos.

    Packet total includes header + payload + 4-byte CRC.
    """
    sync = buf[pos:pos + 3]

    if sync == SYNC_OEM:
        # OEM-style binary header:
        # byte 3 = header length
        # bytes 4..5 = message ID, little-endian
        # bytes 8..9 = payload/message length, little-endian
        if pos + 28 > len(buf):
            return ("OEM_AA4412_INCOMPLETE_HEADER", -1, 0, len(buf) - pos)

        header_length = buf[pos + 3]
        if header_length < 28:
            return None

        message_id = struct.unpack_from("<H", buf, pos + 4)[0]
        payload_length = struct.unpack_from("<H", buf, pos + 8)[0]
        total_length = header_length + payload_length + 4
        return ("OEM_AA4412", message_id, payload_length, total_length)

    if sync == SYNC_N4:
        # Unicore N4 binary header as seen in this recording:
        # fixed 24-byte header
        # bytes 4..5 = message ID, little-endian
        # bytes 6..7 = payload/message length, little-endian
        if pos + 24 > len(buf):
            return ("N4_AA44B5_INCOMPLETE_HEADER", -1, 0, len(buf) - pos)

        message_id = struct.unpack_from("<H", buf, pos + 4)[0]
        payload_length = struct.unpack_from("<H", buf, pos + 6)[0]
        total_length = 24 + payload_length + 4
        return ("N4_AA44B5", message_id, payload_length, total_length)

    return None


def clean_recording(input_path: Path, output_path: Path, check_crc: bool = True) -> int:
    buf = input_path.read_bytes()

    out = bytearray()
    pos = 0

    counts_by_type: Counter[str] = Counter()
    counts_by_msg: Counter[int] = Counter()

    skipped_bytes = 0
    bad_crc_packets = 0
    impossible_headers = 0
    truncated_packet_info = None

    while pos < len(buf):
        sync_pos = find_next_sync(buf, pos)

        if sync_pos == -1:
            skipped_bytes += len(buf) - pos
            break

        if sync_pos > pos:
            skipped_bytes += sync_pos - pos
            pos = sync_pos

        parsed = parse_packet_length(buf, pos)
        if parsed is None:
            impossible_headers += 1
            pos += 1
            continue

        packet_type, message_id, payload_length, total_length = parsed

        # Guard against nonsense lengths from false sync bytes.
        if total_length <= 0 or total_length > 200_000:
            impossible_headers += 1
            pos += 1
            continue

        if pos + total_length > len(buf):
            truncated_packet_info = {
                "position": pos,
                "packet_type": packet_type,
                "message_id": message_id,
                "expected_bytes": total_length,
                "available_bytes": len(buf) - pos,
            }
            break

        packet = buf[pos:pos + total_length]

        if check_crc:
            expected_crc = struct.unpack_from("<I", packet, total_length - 4)[0]
            calculated_crc = unicore_crc32(packet[:-4])

            if expected_crc != calculated_crc:
                bad_crc_packets += 1
                # Do not trust the length if CRC is wrong. Resync one byte later.
                pos += 1
                continue

        out.extend(packet)

        counts_by_type[packet_type] += 1
        counts_by_msg[message_id] += 1

        pos += total_length

    output_path.write_bytes(out)

    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print()
    print(f"Input bytes:    {len(buf):,}")
    print(f"Output bytes:   {len(out):,}")
    print(f"Skipped bytes:  {skipped_bytes:,}")
    print(f"CRC checking:   {'ON' if check_crc else 'OFF'}")
    print(f"Bad CRC packets skipped: {bad_crc_packets:,}")
    print(f"Impossible/false headers skipped: {impossible_headers:,}")
    print()

    print("Packets kept by binary header:")
    for packet_type, count in counts_by_type.most_common():
        print(f"  {packet_type}: {count:,}")

    print()
    print("Packets kept by message ID:")
    for message_id, count in sorted(counts_by_msg.items()):
        print(f"  ID {message_id}: {count:,}")

    if truncated_packet_info:
        print()
        print("Truncated packet found and NOT copied:")
        print(f"  position:        {truncated_packet_info['position']:,}")
        print(f"  packet type:     {truncated_packet_info['packet_type']}")
        print(f"  message ID:      {truncated_packet_info['message_id']}")
        print(f"  expected bytes:  {truncated_packet_info['expected_bytes']:,}")
        print(f"  available bytes: {truncated_packet_info['available_bytes']:,}")

    return 0


def default_output_name(input_path: Path) -> Path:
    return input_path.with_name(input_path.stem + "_complete_packets" + input_path.suffix)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trim a Unicore/UM982 raw BIN recording to complete binary packets only."
    )
    parser.add_argument("input", type=Path, help="Recording output directory name, or explicit input raw BIN file")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output cleaned BIN file. Default: <input>_complete_packets.BIN",
    )
    parser.add_argument(
        "--no-crc",
        action="store_true",
        help="Do not validate packet CRC. Faster, but less safe.",
    )

    args = parser.parse_args()

    if args.input.is_file():
        input_path = args.input
        output_path = args.output or default_output_name(input_path)
    else:
        session_dir = resolve_session_dir(args.input)
        input_path = find_original_bin(session_dir)
        output_path = args.output or output_subdir(session_dir, "other") / default_output_name(input_path).name

    if not input_path.exists():
        raise SystemExit(f"Input file does not exist: {input_path}")

    return clean_recording(
        input_path=input_path,
        output_path=output_path,
        check_crc=not args.no_crc,
    )


if __name__ == "__main__":
    raise SystemExit(main())
