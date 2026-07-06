#!/usr/bin/env python3
"""Create a filtered copy of a Unicore/UM982 recording by message ID."""

from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent
        / "to_rinex"
        / "rinex305_toolkit"
        / "rinex305_toolkit"
    ),
)

from session_paths import OUT_DIR, find_original_bin, output_subdir, resolve_session_dir
from trim_unicore_complete_packets import find_next_sync, parse_packet_length, unicore_crc32


MESSAGE_NAMES = {
    43: "RANGEB",
    138: "OBSVMCMPB",
    139: "OBSVHCMPB",
    140: "RANGECMPB",
}


def format_message_id(message_id: int) -> str:
    name = MESSAGE_NAMES.get(message_id)
    return f"ID {message_id} ({name})" if name else f"ID {message_id}"


def create_filtered_recording(
    source_session: Path,
    output_name: str,
    remove_ids: set[int],
    overwrite: bool,
) -> Path:
    input_path = find_original_bin(source_session)
    output_session = OUT_DIR / output_name
    output_original = output_subdir(output_session, "original")
    for name in ("csv", "rinex", "ppk", "other"):
        output_subdir(output_session, name)

    output_path = output_original / input_path.name
    if output_path.exists() and not overwrite:
        raise SystemExit(f"Output BIN already exists: {output_path}\nPass --overwrite to replace it.")

    buf = input_path.read_bytes()
    out = bytearray()
    kept_counts: Counter[int] = Counter()
    removed_counts: Counter[int] = Counter()
    kept_bytes: Counter[int] = Counter()
    removed_bytes: Counter[int] = Counter()
    skipped_bytes = 0
    bad_crc_packets = 0
    impossible_headers = 0
    truncated_packet_info: tuple[int, str, int, int, int] | None = None

    pos = 0
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

        packet_type, message_id, _payload_length, total_length = parsed
        if total_length <= 0 or total_length > 200_000:
            impossible_headers += 1
            pos += 1
            continue

        if pos + total_length > len(buf):
            truncated_packet_info = (pos, packet_type, message_id, total_length, len(buf) - pos)
            break

        packet = buf[pos : pos + total_length]
        expected_crc = struct.unpack_from("<I", packet, total_length - 4)[0]
        calculated_crc = unicore_crc32(packet[:-4])
        if expected_crc != calculated_crc:
            bad_crc_packets += 1
            pos += 1
            continue

        if message_id in remove_ids:
            removed_counts[message_id] += 1
            removed_bytes[message_id] += total_length
        else:
            out.extend(packet)
            kept_counts[message_id] += 1
            kept_bytes[message_id] += total_length

        pos += total_length

    output_path.write_bytes(out)
    write_report(
        output_session=output_session,
        input_path=input_path,
        output_path=output_path,
        input_bytes=len(buf),
        output_bytes=len(out),
        remove_ids=remove_ids,
        kept_counts=kept_counts,
        removed_counts=removed_counts,
        kept_bytes=kept_bytes,
        removed_bytes=removed_bytes,
        skipped_bytes=skipped_bytes,
        bad_crc_packets=bad_crc_packets,
        impossible_headers=impossible_headers,
        truncated_packet_info=truncated_packet_info,
    )
    return output_session


def add_counts(lines: list[str], title: str, counts: Counter[int], byte_counts: Counter[int]) -> None:
    lines.append(title)
    if not counts:
        lines.append("  none")
        return
    for message_id in sorted(counts):
        lines.append(
            f"  {format_message_id(message_id)}: {counts[message_id]:,} packets, "
            f"{byte_counts[message_id]:,} bytes"
        )


def write_report(
    output_session: Path,
    input_path: Path,
    output_path: Path,
    input_bytes: int,
    output_bytes: int,
    remove_ids: set[int],
    kept_counts: Counter[int],
    removed_counts: Counter[int],
    kept_bytes: Counter[int],
    removed_bytes: Counter[int],
    skipped_bytes: int,
    bad_crc_packets: int,
    impossible_headers: int,
    truncated_packet_info: tuple[int, str, int, int, int] | None,
) -> None:
    lines = [
        f"Created: {datetime.now().isoformat(timespec='seconds')}",
        f"Source BIN: {input_path}",
        f"Output BIN: {output_path}",
        f"Input bytes: {input_bytes:,}",
        f"Output bytes: {output_bytes:,}",
        f"Skipped bytes before/after packets: {skipped_bytes:,}",
        f"Bad CRC packets skipped: {bad_crc_packets:,}",
        f"Impossible/false headers skipped: {impossible_headers:,}",
        "Removed message IDs: " + ", ".join(format_message_id(mid) for mid in sorted(remove_ids)),
        "",
    ]
    add_counts(lines, "Removed packets:", removed_counts, removed_bytes)
    lines.append("")
    add_counts(lines, "Kept packets:", kept_counts, kept_bytes)

    if truncated_packet_info is not None:
        pos, packet_type, message_id, expected_bytes, available_bytes = truncated_packet_info
        lines.extend(
            [
                "",
                "Truncated packet found and not copied:",
                f"  position: {pos:,}",
                f"  packet type: {packet_type}",
                f"  message ID: {message_id}",
                f"  expected bytes: {expected_bytes:,}",
                f"  available bytes: {available_bytes:,}",
            ]
        )

    report_path = output_subdir(output_session, "other") / "split_filter_report.txt"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_message_ids(value: str) -> set[int]:
    message_ids: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            message_ids.add(int(item))
    if not message_ids:
        raise argparse.ArgumentTypeError("provide at least one message ID")
    return message_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", help="Recording output directory name, or full session directory path.")
    parser.add_argument("--output-name", required=True, help="New directory name under out/.")
    parser.add_argument("--remove-ids", required=True, type=parse_message_ids, help="Comma-separated message IDs.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output BIN.")
    args = parser.parse_args()

    output_session = create_filtered_recording(
        source_session=resolve_session_dir(args.recording),
        output_name=args.output_name,
        remove_ids=args.remove_ids,
        overwrite=args.overwrite,
    )
    print(f"Created filtered recording: {output_session}")
    print(f"Report: {output_session / 'other' / 'split_filter_report.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
