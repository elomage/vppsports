#!/usr/bin/env python3
"""
unicore_rangecmp_to_rinex_obs.py

Direct RINEX OBS converter for Unicore/UM982 recordings that contain
RANGECMPB packets (message ID 140, sync AA 44 12).

This script is intended for the failure case where Unicore/UPrecise produces
valid NAV files but an OBS file with 0 observations.

It converts the RANGECMPB raw observations into a RINEX 3.03 / 3.05 observation
file. It does NOT fully convert GPSEPHB/GLOEPHB/BDSEPHB/GALEPHB navigation
messages; use your official Unicore NAV outputs together with the OBS produced
by this script.

Example:
  python unicore_rangecmp_to_rinex_obs.py 20260503_132939Z_test_log_1 --gps-week 2417

For your 2026-05-03 recording, GPS week is 2417.

Notes:
  - Output time system is GPS time, matching the usual mixed-GNSS RINEX OBS style.
  - The script scans the original file directly, so you do not need to pre-trim it.
  - Corrupt or incomplete packets are skipped.
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from collections import Counter, defaultdict, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from session_paths import find_original_bin, output_subdir, resolve_session_dir

C = 299_792_458.0
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
SYNC_OEM = b"\xAA\x44\x12"
SYNC_N4 = b"\xAA\x44\xB5"
MAX_ADR_ROLL = 8_388_608.0

# RINEX observation code mappings for the signal type bits in the RANGECMP
# channel-tracking-status word. For each signal, the tuple is:
#   (system_char, obs_code_suffix, frequency_hz)
# The suffix "1C" means C1C/L1C/D1C/S1C.
SIGNAL_MAP_STANDARD = {
    # GPS, system bits = 0
    (0, 0):  ("G", "1C", 1575.42e6),     # L1 C/A
    (0, 5):  ("G", "2P", 1227.60e6),     # L2 P
    (0, 9):  ("G", "2W", 1227.60e6),     # L2 P(Y)
    (0, 14): ("G", "5Q", 1176.45e6),     # L5 Q
    (0, 16): ("G", "1L", 1575.42e6),     # L1C(P)
    (0, 17): ("G", "2S", 1227.60e6),     # L2C(M)

    # GLONASS, system bits = 1. Frequency is handled separately because it
    # depends on the GLONASS frequency channel.
    (1, 0):  ("R", "1C", None),           # G1 C/A
    (1, 1):  ("R", "2C", None),           # G2 C/A
    # Your Unicore converter header used C2C for the second GLONASS signal.
    # NovAtel labels signal type 5 as L2P, but C2C is usually more compatible
    # with this UM982 output and with your empty Unicore OBS header.
    (1, 5):  ("R", "2C", None),
    (1, 6):  ("R", "3Q", 1202.025e6),

    # Galileo, system bits = 3
    (3, 2):  ("E", "1C", 1575.42e6),      # E1 C
    (3, 6):  ("E", "6B", 1278.75e6),
    (3, 7):  ("E", "6C", 1278.75e6),
    (3, 12): ("E", "5Q", 1176.45e6),
    (3, 17): ("E", "7Q", 1207.14e6),
    (3, 20): ("E", "8Q", 1191.795e6),

    # BeiDou, system bits = 4.
    # Standard RINEX 3.x codes. For your UM982 file, the two observed BDS
    # signal IDs are 0 and 21. ID 21 is treated as B3I because your official
    # converter's empty OBS header listed a C3* second BDS signal.
    (4, 0):  ("C", "2I", 1561.098e6),     # B1I
    (4, 1):  ("C", "7I", 1207.14e6),      # B2I
    (4, 2):  ("C", "6I", 1268.52e6),      # B3I
    (4, 4):  ("C", "2I", 1561.098e6),     # B1I D2
    (4, 5):  ("C", "7I", 1207.14e6),      # B2I D2
    (4, 6):  ("C", "6I", 1268.52e6),      # B3I D2
    (4, 7):  ("C", "1P", 1575.42e6),      # B1C(P)
    (4, 9):  ("C", "5P", 1176.45e6),      # B2a(P)
    (4, 11): ("C", "7D", 1207.14e6),      # B2b(I)
    (4, 21): ("C", "6I", 1268.52e6),      # Unicore/UM982: likely B3I in this file

    # QZSS, system bits = 5
    (5, 0):  ("J", "1C", 1575.42e6),
    (5, 14): ("J", "5Q", 1176.45e6),
    (5, 16): ("J", "1L", 1575.42e6),
    (5, 17): ("J", "2S", 1227.60e6),
}

# Compatibility mode matching your empty Unicore OBS header more closely.
SIGNAL_MAP_LEGACY_BDS = dict(SIGNAL_MAP_STANDARD)
SIGNAL_MAP_LEGACY_BDS[(4, 0)] = ("C", "1C", 1561.098e6)
SIGNAL_MAP_LEGACY_BDS[(4, 21)] = ("C", "3C", 1268.52e6)

# Preferred ordering of observation codes in the RINEX header.
OBS_ORDER = {
    "G": ["1C", "1L", "2S", "2P", "2W", "5Q"],
    "R": ["1C", "2C", "2P", "3Q"],
    "E": ["1C", "5Q", "7Q", "8Q", "6B", "6C"],
    "C": ["1C", "2I", "1P", "5P", "7I", "7D", "6I", "3C"],
    "J": ["1C", "1L", "2S", "5Q", "6L", "6S"],
}


@dataclass
class Obs:
    psr: Optional[float]
    adr: Optional[float]
    doppler: Optional[float]
    cn0: Optional[float]
    lock: float
    lli: str = " "


@dataclass
class Packet:
    pos: int
    msg_id: int
    header_len: int
    payload_len: int
    tow_ms: Optional[int]
    payload: bytes


def crc32_novatel(data: bytes) -> int:
    """NovAtel/Unicore binary CRC-32: polynomial 0xEDB88320, init 0, no final XOR."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
            crc &= 0xFFFFFFFF
    return crc


def gps_week_from_date(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int((dt - GPS_EPOCH).total_seconds() // 604800)


def gps_datetime(gps_week: int, tow_ms: int) -> datetime:
    return GPS_EPOCH + timedelta(weeks=gps_week, milliseconds=tow_ms)


def rinex_line(content: str, label: str = "") -> str:
    return f"{content[:60]:<60}{label:>20}\n"


def find_next_sync(buf: bytes, start: int) -> int:
    a = buf.find(SYNC_OEM, start)
    b = buf.find(SYNC_N4, start)
    found = [x for x in (a, b) if x >= 0]
    return min(found) if found else -1


def iter_packets(buf: bytes, check_crc: bool = True) -> Iterable[Packet]:
    """Yield complete supported binary packets from a noisy/original recording."""
    pos = 0
    n = len(buf)
    while pos < n:
        p = find_next_sync(buf, pos)
        if p < 0:
            break

        sync = buf[p:p + 3]

        if sync == SYNC_OEM:
            if p + 28 > n:
                break
            hlen = buf[p + 3]
            if hlen < 28 or hlen > 128:
                pos = p + 1
                continue
            msg_id = struct.unpack_from("<H", buf, p + 4)[0]
            payload_len = struct.unpack_from("<H", buf, p + 8)[0]
            total = hlen + payload_len + 4
            tow_ms = struct.unpack_from("<I", buf, p + 16)[0] if p + 20 <= n else None

        elif sync == SYNC_N4:
            # The N4 packets in this UM982 recording have a 24-byte binary header.
            if p + 24 > n:
                break
            hlen = 24
            msg_id = struct.unpack_from("<H", buf, p + 4)[0]
            payload_len = struct.unpack_from("<H", buf, p + 6)[0]
            total = hlen + payload_len + 4
            tow_ms = struct.unpack_from("<I", buf, p + 12)[0] if p + 16 <= n else None

        else:
            pos = p + 1
            continue

        # Avoid trusting false sync bytes.
        if payload_len < 0 or total <= 0 or total > 1_000_000:
            pos = p + 1
            continue
        if p + total > n:
            break

        packet_bytes = buf[p:p + total]
        if check_crc:
            expected = struct.unpack_from("<I", packet_bytes, total - 4)[0]
            actual = crc32_novatel(packet_bytes[:-4])
            if expected != actual:
                pos = p + 1
                continue

        yield Packet(
            pos=p,
            msg_id=msg_id,
            header_len=hlen,
            payload_len=payload_len,
            tow_ms=tow_ms,
            payload=buf[p + hlen:p + hlen + payload_len],
        )
        pos = p + total


def infer_gps_week_from_ephemerides(buf: bytes) -> Optional[int]:
    """
    Best-effort GPS week inference from Unicore N4 ephemeris payloads.

    In the UM982 files seen here, useful GPS-week-like values appear at:
      GPSEPHB/BDSEPHB payload offsets 24 and 28
      GLOEPHB payload offset 6
    This is intentionally conservative; users can always override with --gps-week.
    """
    candidates: Counter[int] = Counter()
    for pkt in iter_packets(buf, check_crc=False):
        if pkt.msg_id in (106, 108):
            for off in (24, 28):
                if off + 2 <= len(pkt.payload):
                    v = struct.unpack_from("<H", pkt.payload, off)[0]
                    if 2000 <= v <= 3000:
                        candidates[v] += 1
        elif pkt.msg_id == 107:
            off = 6
            if off + 2 <= len(pkt.payload):
                v = struct.unpack_from("<H", pkt.payload, off)[0]
                if 2000 <= v <= 3000:
                    candidates[v] += 1

    if not candidates:
        return None

    # Ephemeris packets can contain adjacent/previous week values. Choosing the
    # maximum realistic candidate works for recordings near a GPS-week boundary,
    # including your 2026-05-03 test file.
    return max(candidates)


def parse_bestnavxyz_approx_position(buf: bytes) -> Optional[Tuple[float, float, float]]:
    """Return the last computed ECEF XYZ position from BESTNAVXYZB, if present."""
    last: Optional[Tuple[float, float, float]] = None
    for pkt in iter_packets(buf, check_crc=False):
        if pkt.msg_id != 240 or len(pkt.payload) < 36:
            continue
        try:
            sol_status = struct.unpack_from("<I", pkt.payload, 0)[0]
            x, y, z = struct.unpack_from("<ddd", pkt.payload, 8)
        except struct.error:
            continue
        if sol_status == 0 and any(abs(v) > 1.0 for v in (x, y, z)):
            last = (x, y, z)
    return last


def get_bits(value: int, offset: int, width: int, signed: bool = False) -> int:
    x = (value >> offset) & ((1 << width) - 1)
    if signed and (x & (1 << (width - 1))):
        x -= (1 << width)
    return x


def glonass_frequency_hz(signal_suffix: str, glofreq_field: int) -> float:
    # RANGECMP stores GLONASS frequency number as k + 7.
    k = glofreq_field - 7
    if signal_suffix.startswith("1"):
        return (1602.0e6 + k * 0.5625e6)
    if signal_suffix.startswith("2"):
        return (1246.0e6 + k * 0.4375e6)
    if signal_suffix.startswith("3"):
        return 1202.025e6
    return 1602.0e6


def corrected_adr(raw_adr: float, psr: float, wavelength: float) -> float:
    """Undo the RANGECMP ADR roll compression and return carrier phase in cycles."""
    rolls = (psr / wavelength + raw_adr) / MAX_ADR_ROLL
    # NovAtel's documented algorithm: round to nearest integer, with sign handling.
    if rolls <= 0:
        rolls = int(rolls - 0.5)
    else:
        rolls = int(rolls + 0.5)
    return raw_adr - MAX_ADR_ROLL * rolls


def satellite_id(sys_char: str, prn: int) -> Optional[str]:
    if sys_char == "G":
        if 1 <= prn <= 99:
            return f"G{prn:02d}"
    if sys_char == "R":
        # RANGECMP GLONASS uses 38..61; RINEX uses R01..R24.
        slot = prn - 37 if prn >= 38 else prn
        if 1 <= slot <= 99:
            return f"R{slot:02d}"
    if sys_char == "E":
        if 1 <= prn <= 99:
            return f"E{prn:02d}"
    if sys_char == "C":
        if 1 <= prn <= 99:
            return f"C{prn:02d}"
    if sys_char == "J":
        qzss = prn - 192 if prn >= 193 else prn
        if 1 <= qzss <= 99:
            return f"J{qzss:02d}"
    return None


def parse_rangecmp_record(rec: bytes, signal_map: dict) -> Optional[Tuple[str, str, Obs, int, int]]:
    if len(rec) != 24:
        return None
    value = int.from_bytes(rec, "little")

    status = get_bits(value, 0, 32)
    doppler = get_bits(value, 32, 28, signed=True) / 256.0
    psr = get_bits(value, 60, 36, signed=False) / 128.0
    raw_adr = get_bits(value, 96, 32, signed=True) / 256.0
    prn = get_bits(value, 136, 8)
    lock = get_bits(value, 144, 21) / 32.0
    cn0 = get_bits(value, 165, 5) + 20.0
    glofreq = get_bits(value, 170, 6)  # stored as k + 7 for GLONASS

    phase_locked = (status >> 10) & 1
    parity_known = (status >> 11) & 1
    code_locked = (status >> 12) & 1
    sys_bits = (status >> 16) & 0x7
    sig_bits = (status >> 21) & 0x1F
    half_cycle_added = (status >> 28) & 1

    mapped = signal_map.get((sys_bits, sig_bits))
    if not mapped:
        return None

    sys_char, suffix, freq = mapped
    sat = satellite_id(sys_char, prn)
    if not sat:
        return None

    if freq is None and sys_char == "R":
        freq = glonass_frequency_hz(suffix, glofreq)
    if not freq:
        return None

    wavelength = C / freq

    psr_out = psr if code_locked and psr > 0 else None
    doppler_out = doppler if code_locked else None
    cn0_out = cn0 if cn0 > 0 else None
    adr_out = None
    if phase_locked and parity_known and psr_out is not None:
        # Unicore ADR has the opposite sign from the RINEX carrier-phase convention.
        adr_out = -corrected_adr(raw_adr, psr, wavelength)

    # RINEX LLI: put 1 when there is known half-cycle ambiguity/correction.
    lli = "1" if half_cycle_added else " "

    return sat, suffix, Obs(psr_out, adr_out, doppler_out, cn0_out, lock, lli), sys_bits, sig_bits


def read_observations(
    input_path: Path,
    signal_map: dict,
    check_crc: bool = True,
    max_epochs: Optional[int] = None,
) -> Tuple[OrderedDict[int, Dict[str, Dict[str, Obs]]], Counter, Counter, Counter]:
    buf = input_path.read_bytes()
    epochs: OrderedDict[int, Dict[str, Dict[str, Obs]]] = OrderedDict()
    signal_counts: Counter = Counter()
    skipped_signals: Counter = Counter()
    packet_counts: Counter = Counter()

    prev_lock: Dict[Tuple[str, str], float] = {}

    for pkt in iter_packets(buf, check_crc=check_crc):
        packet_counts[pkt.msg_id] += 1
        if pkt.msg_id != 140:
            continue
        if pkt.tow_ms is None or len(pkt.payload) < 4:
            continue

        nobs = struct.unpack_from("<I", pkt.payload, 0)[0]
        if nobs <= 0:
            continue
        if 4 + nobs * 24 > len(pkt.payload):
            continue

        epoch = epochs.setdefault(pkt.tow_ms, {})
        for i in range(nobs):
            rec = pkt.payload[4 + i * 24:4 + (i + 1) * 24]
            parsed = parse_rangecmp_record(rec, signal_map)
            if parsed is None:
                # Count unknown signals for diagnostics.
                value = int.from_bytes(rec, "little")
                status = get_bits(value, 0, 32)
                sys_bits = (status >> 16) & 0x7
                sig_bits = (status >> 21) & 0x1F
                skipped_signals[(sys_bits, sig_bits)] += 1
                continue
            sat, suffix, obs, sys_bits, sig_bits = parsed
            signal_counts[(sat[0], suffix)] += 1

            # Cycle-slip LLI from lock-time reset.
            key = (sat, suffix)
            old_lock = prev_lock.get(key)
            if old_lock is not None and obs.lock + 0.10 < old_lock:
                obs.lli = "1"
            prev_lock[key] = obs.lock

            epoch.setdefault(sat, {})[suffix] = obs

        if max_epochs is not None and len(epochs) >= max_epochs:
            break

    return epochs, signal_counts, skipped_signals, packet_counts


def order_obs_suffixes(sys_char: str, suffixes: Iterable[str]) -> List[str]:
    suffixes = set(suffixes)
    preferred = OBS_ORDER.get(sys_char, [])
    ordered = [s for s in preferred if s in suffixes]
    ordered += sorted(suffixes - set(ordered))
    return ordered


def obs_types_from_epochs(epochs: OrderedDict[int, Dict[str, Dict[str, Obs]]]) -> Dict[str, List[str]]:
    suffixes_by_sys: Dict[str, set] = defaultdict(set)
    for sats in epochs.values():
        for sat, obs_by_suffix in sats.items():
            for suffix in obs_by_suffix:
                suffixes_by_sys[sat[0]].add(suffix)

    out: Dict[str, List[str]] = OrderedDict()
    for sys_char in ("G", "R", "E", "C", "J"):
        if sys_char not in suffixes_by_sys:
            continue
        obs_types: List[str] = []
        for suffix in order_obs_suffixes(sys_char, suffixes_by_sys[sys_char]):
            obs_types.extend(["C" + suffix, "L" + suffix, "D" + suffix, "S" + suffix])
        out[sys_char] = obs_types
    return out


def fmt_obs_value(value: Optional[float], lli: str = " ") -> str:
    if value is None:
        return " " * 16
    # 14-char numeric field + LLI + signal strength indicator.
    return f"{value:14.3f}{lli:1s} "


def write_rinex_obs(
    output_path: Path,
    epochs: OrderedDict[int, Dict[str, Dict[str, Obs]]],
    gps_week: int,
    rinex_version: str = "3.03",
    marker_name: str = "UM982_ROVER",
    receiver_type: str = "Unicore UM982",
    antenna_type: str = "UNKNOWN",
    approx_position: Optional[Tuple[float, float, float]] = None,
) -> None:
    if not epochs:
        raise RuntimeError("No observations found; cannot write RINEX OBS.")

    obs_types = obs_types_from_epochs(epochs)
    first_tow = next(iter(epochs.keys()))
    last_tow = next(reversed(epochs.keys()))
    first_dt = gps_datetime(gps_week, first_tow)
    last_dt = gps_datetime(gps_week, last_tow)

    lines: List[str] = []
    lines.append(rinex_line(f"{float(rinex_version):9.2f}           OBSERVATION DATA    M                   ", "RINEX VERSION / TYPE"))
    now = datetime.now(timezone.utc).strftime("%Y%m%d %H%M%S UTC")
    lines.append(rinex_line(f"rangecmp2rinex     ChatGPT/Python      {now:<20}", "PGM / RUN BY / DATE"))
    lines.append(rinex_line("Direct conversion from Unicore/NovAtel RANGECMPB message ID 140", "COMMENT"))
    lines.append(rinex_line("Navigation files from official Unicore converter can be used with this OBS", "COMMENT"))
    lines.append(rinex_line(marker_name, "MARKER NAME"))
    lines.append(rinex_line("GEODETIC", "MARKER TYPE"))
    lines.append(rinex_line(f"{'UNKNOWN':<20}{'UNKNOWN':<40}", "OBSERVER / AGENCY"))
    lines.append(rinex_line(f"{'UNKNOWN':<20}{receiver_type:<20}{'UNKNOWN':<20}", "REC # / TYPE / VERS"))
    lines.append(rinex_line(f"{'UNKNOWN':<20}{antenna_type:<40}", "ANT # / TYPE"))

    if approx_position:
        x, y, z = approx_position
    else:
        x = y = z = 0.0
    lines.append(rinex_line(f"{x:14.4f}{y:14.4f}{z:14.4f}", "APPROX POSITION XYZ"))
    lines.append(rinex_line(f"{0.0:14.4f}{0.0:14.4f}{0.0:14.4f}", "ANTENNA: DELTA H/E/N"))

    for sys_char, types in obs_types.items():
        # Up to 13 observation types per RINEX header line after sys/count.
        chunks = [types[i:i + 13] for i in range(0, len(types), 13)]
        for idx, chunk in enumerate(chunks):
            if idx == 0:
                content = f"{sys_char}  {len(types):3d} " + " ".join(f"{t:>3s}" for t in chunk)
            else:
                content = "      " + " ".join(f"{t:>3s}" for t in chunk)
            lines.append(rinex_line(content, "SYS / # / OBS TYPES"))

    lines.append(rinex_line(f"{0.050:10.3f}", "INTERVAL"))
    lines.append(rinex_line(
        f"  {first_dt.year:4d}    {first_dt.month:2d}    {first_dt.day:2d}    {first_dt.hour:2d}    {first_dt.minute:2d}   {first_dt.second + first_dt.microsecond/1e6:10.7f}     GPS",
        "TIME OF FIRST OBS",
    ))
    lines.append(rinex_line(
        f"  {last_dt.year:4d}    {last_dt.month:2d}    {last_dt.day:2d}    {last_dt.hour:2d}    {last_dt.minute:2d}   {last_dt.second + last_dt.microsecond/1e6:10.7f}     GPS",
        "TIME OF LAST OBS",
    ))
    lines.append(rinex_line("     0", "RCV CLOCK OFFS APPL"))
    lines.append(rinex_line("", "END OF HEADER"))

    for tow_ms, sats in epochs.items():
        dt = gps_datetime(gps_week, tow_ms)
        sat_ids = sorted(sats.keys())
        sec = dt.second + dt.microsecond / 1e6
        lines.append(f"> {dt.year:4d} {dt.month:02d} {dt.day:02d} {dt.hour:02d} {dt.minute:02d} {sec:10.7f}  0 {len(sat_ids):3d}\n")

        for sat in sat_ids:
            sys_char = sat[0]
            types = obs_types[sys_char]
            by_suffix = sats[sat]
            line = sat
            for typ in types:
                kind = typ[0]
                suffix = typ[1:]
                obs = by_suffix.get(suffix)
                if obs is None:
                    line += " " * 16
                elif kind == "C":
                    line += fmt_obs_value(obs.psr)
                elif kind == "L":
                    line += fmt_obs_value(obs.adr, obs.lli)
                elif kind == "D":
                    line += fmt_obs_value(obs.doppler)
                elif kind == "S":
                    line += fmt_obs_value(obs.cn0)
            lines.append(line + "\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(lines), encoding="ascii", newline="")


def default_output_path(input_path: Path, gps_week: int) -> Path:
    # Make a RINEX-style OBS extension from GPS week year when possible.
    dt = GPS_EPOCH + timedelta(weeks=gps_week)
    yy = dt.year % 100
    return input_path.with_suffix(f".{yy:02d}O")


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert Unicore/UM982 RANGECMPB observations to RINEX 3 OBS.")
    ap.add_argument("input", type=Path, help="Recording output directory name, or explicit original/cleaned .BIN recording")
    ap.add_argument("-o", "--output", type=Path, help="Output RINEX observation file, e.g. test.26O")
    ap.add_argument("--rinex-version", default="3.03", choices=["3.03", "3.05"], help="RINEX OBS version to write")
    ap.add_argument("--gps-week", type=int, help="GPS week of the recording. For 2026-05-03 use 2417.")
    ap.add_argument("--date", help="UTC/GPS date of recording as YYYY-MM-DD; used to compute GPS week")
    ap.add_argument("--no-crc", action="store_true", help="Disable CRC checking")
    ap.add_argument("--legacy-bds-codes", action="store_true", help="Use BDS C1C/C3C codes like your empty Unicore OBS header instead of standard C2I/C6I")
    ap.add_argument("--marker", default="UM982_ROVER", help="RINEX marker name")
    ap.add_argument("--max-epochs", type=int, help="Debug: convert only first N epochs")
    ap.add_argument("--min-sats", type=int, default=1, help="Drop epochs with fewer than this many satellites. Use 4 to remove early weak startup epochs.")

    args = ap.parse_args()
    session_dir = None
    if args.input.is_file():
        input_path = args.input
    else:
        session_dir = resolve_session_dir(args.input)
        input_path = find_original_bin(session_dir)
    if not input_path.exists():
        raise SystemExit(f"Input file does not exist: {input_path}")

    buf = input_path.read_bytes()

    gps_week = args.gps_week
    if args.date:
        gps_week = gps_week_from_date(args.date)
    if gps_week is None:
        gps_week = infer_gps_week_from_ephemerides(buf)
        if gps_week is not None:
            print(f"Auto-detected GPS week: {gps_week}")
    if gps_week is None:
        now_week = int((datetime.now(timezone.utc) - GPS_EPOCH).total_seconds() // 604800)
        gps_week = now_week
        print(f"WARNING: Could not infer GPS week. Using current GPS week {gps_week}. Override with --gps-week or --date.", file=sys.stderr)

    out = args.output or (
        output_subdir(session_dir, "rinex") / default_output_path(input_path, gps_week).name
        if session_dir else default_output_path(input_path, gps_week)
    )
    signal_map = SIGNAL_MAP_LEGACY_BDS if args.legacy_bds_codes else SIGNAL_MAP_STANDARD

    epochs, signal_counts, skipped_signals, packet_counts = read_observations(
        input_path,
        signal_map=signal_map,
        check_crc=not args.no_crc,
        max_epochs=args.max_epochs,
    )

    if args.min_sats > 1:
        epochs = OrderedDict((tow, sats) for tow, sats in epochs.items() if len(sats) >= args.min_sats)

    approx_position = parse_bestnavxyz_approx_position(buf)

    write_rinex_obs(
        output_path=out,
        epochs=epochs,
        gps_week=gps_week,
        rinex_version=args.rinex_version,
        marker_name=args.marker,
        approx_position=approx_position,
    )

    obs_count = sum(len(sats) for sats in epochs.values())
    print(f"Wrote: {out}")
    print(f"Epochs: {len(epochs):,}")
    print(f"Satellite epoch lines: {obs_count:,}")
    print("Packet counts:")
    for msg_id, cnt in sorted(packet_counts.items()):
        print(f"  ID {msg_id}: {cnt:,}")
    print("Observation signals kept:")
    for (sys_char, suffix), cnt in sorted(signal_counts.items()):
        print(f"  {sys_char}{suffix}: {cnt:,}")
    if skipped_signals:
        print("Skipped/unmapped signal types:")
        for (sys_bits, sig_bits), cnt in skipped_signals.most_common():
            print(f"  system={sys_bits}, signal={sig_bits}: {cnt:,}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
