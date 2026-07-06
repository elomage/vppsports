#!/usr/bin/env python3
"""
unicore_bin_to_rinex305_full.py

Standalone converter for Unicore/UM982 binary logs to RINEX 3.05.

It does NOT call UPrecise. It parses the packets directly from the original .BIN:

  OBS:
    RANGEB      message ID 43   -> RINEX .yyO
    RANGECMPB   message ID 140  -> RINEX .yyO
    OBSVMB      message ID 12   -> RINEX .yyO
    OBSVMCMPB   message ID 138  -> RINEX .yyO
    OBSVHB      message ID 13   -> RINEX .yyO (slave antenna, explicit option)
    OBSVHCMPB   message ID 139  -> RINEX .yyO (slave antenna, explicit option)

  NAV:
    GPSEPHB    message ID 106  -> GPS     .yyN
    GLOEPHB    message ID 107  -> GLONASS .yyG
    BDSEPHB    message ID 108  -> BeiDou  .yyC
    GALEPHB    message ID 109  -> Galileo .yyL
    all NAV records together   -> Mixed   .yyP

This was written for the Unicore/UM982 packet layout in your recordings. It keeps the
code self-contained and avoids external GNSS packages.

Typical use:

  python rinex305_conversion_full.py 20260503_132939Z_test_log_1

If the date is not supplied, the script tries to infer GPS week from ephemeris packets.
For your 2026-05-03 recording, GPS week is 2417.

Notes:
  * By default, navigation records from old receiver memory are filtered out; only records
    matching the observation GPS week are written. Use --include-all-nav to keep all.
  * BDS ephemeris logs use a GPS-week-like field in this Unicore log. RINEX BDS NAV
    requires BDT week, so the script writes BDT week = GPS week - 1356.
  * RANGECMPB/OBSVMCMPB/OBSVHCMPB observation decoding follows the Unicore
    compressed observation bit layout and writes standard RINEX observation codes
    where possible.
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
import zipfile
from collections import Counter, OrderedDict, defaultdict
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
BDS_GPS_WEEK_OFFSET = 1356  # GPS week 1356 == BDT week 0, 2006-01-01

# Message IDs used by the UM982 recording.
MSG_OBSVMB = 12
MSG_OBSVHB = 13
MSG_RANGEB = 43
MSG_OBSVMCMPB = 138
MSG_OBSVHCMPB = 139
MSG_RANGECMPB = 140
MSG_BESTNAVXYZB = 240
MSG_GPSEPHB = 106
MSG_GLOEPHB = 107
MSG_BDSEPHB = 108
MSG_GALEPHB = 109

# RINEX observation code mappings for the signal type bits in RANGECMP channel status.
# Each tuple is: (RINEX system char, code suffix, frequency Hz or None for GLONASS FDMA).
SIGNAL_MAP_STANDARD = {
    # GPS, system bits = 0
    (0, 0):  ("G", "1C", 1575.42e6),
    (0, 5):  ("G", "2P", 1227.60e6),
    (0, 9):  ("G", "2W", 1227.60e6),
    (0, 14): ("G", "5Q", 1176.45e6),
    (0, 16): ("G", "1L", 1575.42e6),
    (0, 17): ("G", "2S", 1227.60e6),

    # GLONASS, system bits = 1
    (1, 0):  ("R", "1C", None),
    (1, 1):  ("R", "2C", None),
    (1, 5):  ("R", "2C", None),
    (1, 6):  ("R", "3Q", 1202.025e6),

    # Galileo, system bits = 3
    (3, 2):  ("E", "1C", 1575.42e6),
    (3, 6):  ("E", "6B", 1278.75e6),
    (3, 7):  ("E", "6C", 1278.75e6),
    (3, 12): ("E", "5Q", 1176.45e6),
    (3, 17): ("E", "7Q", 1207.14e6),
    (3, 20): ("E", "8Q", 1191.795e6),

    # BeiDou, system bits = 4
    (4, 0):  ("C", "2I", 1561.098e6),  # B1I
    (4, 1):  ("C", "7I", 1207.14e6),   # B2I
    (4, 2):  ("C", "6I", 1268.52e6),   # B3I
    (4, 4):  ("C", "2I", 1561.098e6),
    (4, 5):  ("C", "7I", 1207.14e6),
    (4, 6):  ("C", "6I", 1268.52e6),
    (4, 7):  ("C", "1P", 1575.42e6),
    (4, 9):  ("C", "5P", 1176.45e6),
    (4, 11): ("C", "7D", 1207.14e6),
    (4, 17): ("C", "7I", 1207.14e6),
    (4, 21): ("C", "6I", 1268.52e6),   # UM982 observed B3-like signal in your file

    # QZSS, system bits = 5
    (5, 0):  ("J", "1C", 1575.42e6),
    (5, 14): ("J", "5Q", 1176.45e6),
    (5, 16): ("J", "1L", 1575.42e6),
    (5, 17): ("J", "2S", 1227.60e6),
}

SIGNAL_MAP_LEGACY_BDS = dict(SIGNAL_MAP_STANDARD)
SIGNAL_MAP_LEGACY_BDS[(4, 0)] = ("C", "1C", 1561.098e6)
SIGNAL_MAP_LEGACY_BDS[(4, 21)] = ("C", "3C", 1268.52e6)

OBS_ORDER = {
    "G": ["1C", "1L", "2S", "2P", "2W", "5Q"],
    "R": ["1C", "2C", "2P", "3Q"],
    "E": ["1C", "5Q", "7Q", "8Q", "6B", "6C"],
    "C": ["1C", "2I", "1P", "5P", "7I", "7D", "6I", "3C"],
    "J": ["1C", "1L", "2S", "5Q"],
}

RTKLIB_PRIMARY_SUFFIXES = {
    # Keep one broadly-supported signal per constellation. RTKLIB 2.4.3 b34
    # rejects some newer/less-common RINEX 3 codes emitted by the full writer
    # (for example BeiDou C6I), and that can leave the solver with no epochs.
    "G": {"1C"},
    "R": {"1C"},
    "E": {"1C"},
    "C": {"2I"},
    "J": {"1C"},
}

OBS_SOURCE_IDS = {
    "rangeb": (MSG_RANGEB,),
    "rangecmpb": (MSG_RANGECMPB,),
    "obsvmb": (MSG_OBSVMB,),
    "obsvmcmpb": (MSG_OBSVMCMPB,),
    "obsvhb": (MSG_OBSVHB,),
    "obsvhcmpb": (MSG_OBSVHCMPB,),
}

OBS_SOURCE_LABELS = {
    "rangeb": "RANGEB",
    "rangecmpb": "RANGECMPB",
    "obsvmb": "OBSVMB master antenna",
    "obsvmcmpb": "OBSVMCMPB master antenna",
    "obsvhb": "OBSVHB slave antenna",
    "obsvhcmpb": "OBSVHCMPB slave antenna",
}

AUTO_OBS_SOURCE_ORDER = ("rangecmpb", "obsvmcmpb", "obsvmb", "rangeb")


@dataclass
class Packet:
    pos: int
    msg_id: int
    header_len: int
    payload_len: int
    gps_week: Optional[int]
    tow_ms: Optional[int]
    payload: bytes


@dataclass
class Obs:
    psr: Optional[float]
    adr: Optional[float]
    doppler: Optional[float]
    cn0: Optional[float]
    lock: float
    lli: str = " "


@dataclass
class NavRecord:
    sys: str
    sat: str
    gps_week: int
    toc_s: float
    lines: List[List[Optional[float]]]
    sort_time_s: float
    key: Tuple


def crc32_novatel(data: bytes) -> int:
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


def gps_datetime(gps_week: int, tow_s: float) -> datetime:
    return GPS_EPOCH + timedelta(weeks=gps_week, seconds=float(tow_s))


def rinex_line(content: str, label: str = "") -> str:
    return f"{content[:60]:<60}{label:>20}\n"


def find_next_sync(buf: bytes, start: int) -> int:
    a = buf.find(SYNC_OEM, start)
    b = buf.find(SYNC_N4, start)
    found = [x for x in (a, b) if x >= 0]
    return min(found) if found else -1


def iter_packets(buf: bytes, check_crc: bool = True) -> Iterable[Packet]:
    """Yield complete AA4412 and AA44B5 binary packets from a noisy recording."""
    pos = 0
    n = len(buf)
    while pos < n:
        p = find_next_sync(buf, pos)
        if p < 0:
            break

        sync = buf[p:p + 3]
        gps_week: Optional[int] = None
        tow_ms: Optional[int] = None

        if sync == SYNC_OEM:
            if p + 28 > n:
                break
            hlen = buf[p + 3]
            if hlen < 28 or hlen > 128:
                pos = p + 1
                continue
            msg_id = struct.unpack_from("<H", buf, p + 4)[0]
            payload_len = struct.unpack_from("<H", buf, p + 8)[0]
            # Legacy/OEM header contains GPS week at +14 and ms-of-week at +16.
            gps_week = struct.unpack_from("<H", buf, p + 14)[0]
            tow_ms = struct.unpack_from("<I", buf, p + 16)[0]
            total = hlen + payload_len + 4

        elif sync == SYNC_N4:
            # UM982 N4 packets in your file: 24-byte binary header.
            if p + 24 > n:
                break
            hlen = 24
            msg_id = struct.unpack_from("<H", buf, p + 4)[0]
            payload_len = struct.unpack_from("<H", buf, p + 6)[0]
            # Observed N4 header: GPS week at +10, ms-of-week at +12.
            gps_week = struct.unpack_from("<H", buf, p + 10)[0]
            tow_ms = struct.unpack_from("<I", buf, p + 12)[0]
            total = hlen + payload_len + 4

        else:
            pos = p + 1
            continue

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
            gps_week=gps_week,
            tow_ms=tow_ms,
            payload=buf[p + hlen:p + hlen + payload_len],
        )
        pos = p + total


def get_bits(value: int, offset: int, width: int, signed: bool = False) -> int:
    x = (value >> offset) & ((1 << width) - 1)
    if signed and (x & (1 << (width - 1))):
        x -= 1 << width
    return x


def glonass_frequency_hz(signal_suffix: str, glofreq_field: int) -> float:
    k = glofreq_field - 7
    if signal_suffix.startswith("1"):
        return 1602.0e6 + k * 0.5625e6
    if signal_suffix.startswith("2"):
        return 1246.0e6 + k * 0.4375e6
    if signal_suffix.startswith("3"):
        return 1202.025e6
    return 1602.0e6


def corrected_adr(raw_adr: float, psr: float, wavelength: float) -> float:
    rolls = (psr / wavelength + raw_adr) / MAX_ADR_ROLL
    rolls = int(rolls - 0.5) if rolls <= 0 else int(rolls + 0.5)
    return raw_adr - MAX_ADR_ROLL * rolls


def satellite_id(sys_char: str, prn: int) -> Optional[str]:
    if sys_char in ("G", "E", "C") and 1 <= prn <= 99:
        return f"{sys_char}{prn:02d}"
    if sys_char == "R":
        slot = prn - 37 if prn >= 38 else prn
        if 1 <= slot <= 99:
            return f"R{slot:02d}"
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
    glofreq = get_bits(value, 170, 6)

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
    # Unicore ADR has the opposite sign from the RINEX carrier-phase convention.
    adr_out = -corrected_adr(raw_adr, psr, wavelength) if phase_locked and parity_known and psr_out is not None else None
    lli = "1" if half_cycle_added else " "
    return sat, suffix, Obs(psr_out, adr_out, doppler_out, cn0_out, lock, lli), sys_bits, sig_bits


def parse_obsvm_record(rec: bytes, signal_map: dict) -> Optional[Tuple[str, str, Obs, int, int]]:
    if len(rec) < 40:
        return None

    glofreq = struct.unpack_from("<H", rec, 0)[0]
    prn = struct.unpack_from("<H", rec, 2)[0]
    psr = struct.unpack_from("<d", rec, 4)[0]
    adr = struct.unpack_from("<d", rec, 12)[0]
    doppler = struct.unpack_from("<f", rec, 24)[0]
    cn0 = struct.unpack_from("<H", rec, 28)[0] / 100.0
    lock = struct.unpack_from("<f", rec, 32)[0]
    status = struct.unpack_from("<I", rec, 36)[0]

    phase_valid = (status >> 10) & 1
    code_valid = (status >> 12) & 1
    sys_bits = (status >> 16) & 0x7
    sig_bits = (status >> 21) & 0x1F

    mapped = signal_map.get((sys_bits, sig_bits))
    if not mapped:
        return None
    sys_char, suffix, freq = mapped
    sat = satellite_id(sys_char, prn)
    if not sat:
        return None
    if freq is None and sys_char == "R":
        freq = glonass_frequency_hz(suffix, glofreq)

    psr_out = psr if code_valid and psr > 0 else None
    # Unicore ADR has the opposite sign from the RINEX carrier-phase convention.
    adr_out = -adr if phase_valid and psr_out is not None else None
    doppler_out = doppler if code_valid else None
    cn0_out = cn0 if cn0 > 0 else None
    return sat, suffix, Obs(psr_out, adr_out, doppler_out, cn0_out, lock), sys_bits, sig_bits


def parse_rangeb_record(rec: bytes, signal_map: dict) -> Optional[Tuple[str, str, Obs, int, int]]:
    if len(rec) != 44:
        return None

    prn = struct.unpack_from("<H", rec, 0)[0]
    glofreq = struct.unpack_from("<H", rec, 2)[0]
    psr = struct.unpack_from("<d", rec, 4)[0]
    adr = struct.unpack_from("<d", rec, 16)[0]
    doppler = struct.unpack_from("<f", rec, 28)[0]
    cn0 = struct.unpack_from("<f", rec, 32)[0]
    lock = struct.unpack_from("<f", rec, 36)[0]
    status = struct.unpack_from("<I", rec, 40)[0]

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

    psr_out = psr if code_locked and psr > 0 else None
    # Unicore ADR has the opposite sign from the RINEX carrier-phase convention.
    adr_out = -adr if phase_locked and parity_known and psr_out is not None else None
    doppler_out = doppler if code_locked else None
    cn0_out = cn0 if cn0 > 0 else None
    lli = "1" if half_cycle_added else " "
    return sat, suffix, Obs(psr_out, adr_out, doppler_out, cn0_out, lock, lli), sys_bits, sig_bits


def choose_obs_source(packets: List[Packet], requested: str) -> str:
    if requested != "auto":
        return requested
    packet_counts = Counter(pkt.msg_id for pkt in packets)
    for source in AUTO_OBS_SOURCE_ORDER:
        if any(packet_counts[msg_id] for msg_id in OBS_SOURCE_IDS[source]):
            return source
    return "rangecmpb"


def read_observations(
    packets: List[Packet],
    signal_map: dict,
    obs_source: str,
    max_epochs: Optional[int] = None,
) -> Tuple[OrderedDict[int, Dict[str, Dict[str, Obs]]], Counter, Counter]:
    epochs: OrderedDict[int, Dict[str, Dict[str, Obs]]] = OrderedDict()
    signal_counts: Counter = Counter()
    skipped_signals: Counter = Counter()
    prev_lock: Dict[Tuple[str, str], float] = {}
    msg_ids = OBS_SOURCE_IDS[obs_source]
    compressed = obs_source in {"rangecmpb", "obsvmcmpb", "obsvhcmpb"}
    rangeb = obs_source == "rangeb"
    record_len = 24 if compressed else 44 if rangeb else 40

    for pkt in packets:
        if pkt.msg_id not in msg_ids:
            continue
        if pkt.tow_ms is None or len(pkt.payload) < 4:
            continue

        nobs = struct.unpack_from("<I", pkt.payload, 0)[0]
        if nobs <= 0:
            continue
        if 4 + nobs * record_len > len(pkt.payload):
            continue

        epoch = epochs.setdefault(pkt.tow_ms, {})
        for i in range(nobs):
            rec = pkt.payload[4 + i * record_len:4 + (i + 1) * record_len]
            if compressed:
                parsed = parse_rangecmp_record(rec, signal_map)
            elif rangeb:
                parsed = parse_rangeb_record(rec, signal_map)
            else:
                parsed = parse_obsvm_record(rec, signal_map)
            if parsed is None:
                status = (
                    get_bits(int.from_bytes(rec, "little"), 0, 32)
                    if compressed
                    else struct.unpack_from("<I", rec, 40 if rangeb else 36)[0]
                )
                skipped_signals[((status >> 16) & 0x7, (status >> 21) & 0x1F)] += 1
                continue

            sat, suffix, obs, sys_bits, sig_bits = parsed
            signal_counts[(sat[0], suffix)] += 1

            key = (sat, suffix)
            old_lock = prev_lock.get(key)
            if old_lock is not None and obs.lock + 0.10 < old_lock:
                obs.lli = "1"
            prev_lock[key] = obs.lock
            epoch.setdefault(sat, {})[suffix] = obs

        if max_epochs is not None and len(epochs) >= max_epochs:
            break

    return epochs, signal_counts, skipped_signals


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


def filter_epochs_for_obs_profile(
    epochs: OrderedDict[int, Dict[str, Dict[str, Obs]]],
    obs_profile: str,
) -> OrderedDict[int, Dict[str, Dict[str, Obs]]]:
    if obs_profile == "full":
        return epochs
    if obs_profile != "rtklib":
        raise ValueError(f"Unknown OBS profile: {obs_profile}")

    filtered: OrderedDict[int, Dict[str, Dict[str, Obs]]] = OrderedDict()
    for tow_ms, sats in epochs.items():
        kept_sats: Dict[str, Dict[str, Obs]] = {}
        for sat, obs_by_suffix in sats.items():
            allowed = RTKLIB_PRIMARY_SUFFIXES.get(sat[0])
            if not allowed:
                continue
            kept = {suffix: obs for suffix, obs in obs_by_suffix.items() if suffix in allowed}
            if kept:
                kept_sats[sat] = kept
        if kept_sats:
            filtered[tow_ms] = kept_sats
    return filtered


def count_obs_signals(epochs: OrderedDict[int, Dict[str, Dict[str, Obs]]]) -> Counter:
    counts: Counter = Counter()
    for sats in epochs.values():
        for sat, obs_by_suffix in sats.items():
            for suffix in obs_by_suffix:
                counts[(sat[0], suffix)] += 1
    return counts


def fmt_obs_value(value: Optional[float], lli: str = " ") -> str:
    if value is None:
        return " " * 16
    return f"{value:14.3f}{lli:1s} "


def parse_bestnavxyz_approx_position(packets: List[Packet]) -> Optional[Tuple[float, float, float]]:
    last: Optional[Tuple[float, float, float]] = None
    for pkt in packets:
        if pkt.msg_id != MSG_BESTNAVXYZB or len(pkt.payload) < 36:
            continue
        try:
            sol_status = struct.unpack_from("<I", pkt.payload, 0)[0]
            x, y, z = struct.unpack_from("<ddd", pkt.payload, 8)
        except struct.error:
            continue
        if sol_status == 0 and any(abs(v) > 1.0 for v in (x, y, z)):
            last = (x, y, z)
    return last


def write_rinex_obs(
    output_path: Path,
    epochs: OrderedDict[int, Dict[str, Dict[str, Obs]]],
    gps_week: int,
    rinex_version: str,
    marker_name: str,
    approx_position: Optional[Tuple[float, float, float]],
) -> None:
    if not epochs:
        raise RuntimeError("No observations found; cannot write RINEX OBS.")

    obs_types = obs_types_from_epochs(epochs)
    first_tow_ms = next(iter(epochs.keys()))
    last_tow_ms = next(reversed(epochs.keys()))
    first_dt = gps_datetime(gps_week, first_tow_ms / 1000.0)
    last_dt = gps_datetime(gps_week, last_tow_ms / 1000.0)

    lines: List[str] = []
    lines.append(rinex_line(f"{float(rinex_version):9.2f}           OBSERVATION DATA    M                   ", "RINEX VERSION / TYPE"))
    now = datetime.now(timezone.utc).strftime("%Y%m%d %H%M%S UTC")
    lines.append(rinex_line(f"unicore_full      Python             {now:<20}", "PGM / RUN BY / DATE"))
    lines.append(rinex_line("Direct OBS from raw logs; direct NAV from ephemeris logs", "COMMENT"))
    lines.append(rinex_line(marker_name, "MARKER NAME"))
    lines.append(rinex_line("GEODETIC", "MARKER TYPE"))
    lines.append(rinex_line(f"{'UNKNOWN':<20}{'UNKNOWN':<40}", "OBSERVER / AGENCY"))
    lines.append(rinex_line(f"{'UNKNOWN':<20}{'Unicore UM982':<20}{'UNKNOWN':<20}", "REC # / TYPE / VERS"))
    lines.append(rinex_line(f"{'UNKNOWN':<20}{'UNKNOWN':<40}", "ANT # / TYPE"))

    x, y, z = approx_position or (0.0, 0.0, 0.0)
    lines.append(rinex_line(f"{x:14.4f}{y:14.4f}{z:14.4f}", "APPROX POSITION XYZ"))
    lines.append(rinex_line(f"{0.0:14.4f}{0.0:14.4f}{0.0:14.4f}", "ANTENNA: DELTA H/E/N"))

    for sys_char, types in obs_types.items():
        chunks = [types[i:i + 13] for i in range(0, len(types), 13)]
        for idx, chunk in enumerate(chunks):
            if idx == 0:
                content = f"{sys_char}  {len(types):3d} " + " ".join(f"{t:>3s}" for t in chunk)
            else:
                content = "      " + " ".join(f"{t:>3s}" for t in chunk)
            lines.append(rinex_line(content, "SYS / # / OBS TYPES"))

    # Estimate interval from epochs where possible.
    interval = 0.0
    if len(epochs) >= 2:
        keys = list(epochs.keys())[:20]
        diffs = [(b - a) / 1000.0 for a, b in zip(keys, keys[1:]) if b > a]
        if diffs:
            interval = min(diffs)
    if interval <= 0:
        interval = 0.05
    lines.append(rinex_line(f"{interval:10.3f}", "INTERVAL"))
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
        dt = gps_datetime(gps_week, tow_ms / 1000.0)
        sat_ids = sorted(sats.keys())
        sec = dt.second + dt.microsecond / 1e6
        lines.append(f"> {dt.year:4d} {dt.month:02d} {dt.day:02d} {dt.hour:02d} {dt.minute:02d} {sec:10.7f}  0{len(sat_ids):3d}\n")

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


# ---- Navigation parsing/writing -------------------------------------------------

def u8(p: bytes, o: int) -> int:
    return struct.unpack_from("<B", p, o)[0]


def u16(p: bytes, o: int) -> int:
    return struct.unpack_from("<H", p, o)[0]


def u32(p: bytes, o: int) -> int:
    return struct.unpack_from("<I", p, o)[0]


def d64(p: bytes, o: int) -> float:
    return struct.unpack_from("<d", p, o)[0]


def safe_sqrt_a(a: float) -> float:
    return math.sqrt(a) if a > 0 else 0.0


def bds_week_from_gps_week(gps_week: int) -> int:
    return gps_week - BDS_GPS_WEEK_OFFSET


def fmt_nav_num(v: Optional[float]) -> str:
    if v is None:
        return " " * 19
    if math.isnan(float(v)) or math.isinf(float(v)):
        return " " * 19
    s = f"{float(v):19.12E}".replace("E", "D")
    # RINEX examples often omit the zero before decimal for positive fractional values;
    # fixed E/D format with leading zero is still accepted by normal parsers.
    return s


def nav_epoch_line(sat: str, dt: datetime, vals: List[Optional[float]]) -> str:
    sec = int(round(dt.second + dt.microsecond / 1e6))
    return f"{sat:3s} {dt.year:4d} {dt.month:02d} {dt.day:02d} {dt.hour:02d} {dt.minute:02d} {sec:02d}" + "".join(fmt_nav_num(v) for v in vals) + "\n"


def nav_cont_line(vals: List[Optional[float]]) -> str:
    return "    " + "".join(fmt_nav_num(v) for v in vals) + "\n"


def nav_record_to_text(rec: NavRecord) -> str:
    dt = gps_datetime(rec.gps_week, rec.toc_s)
    # rec.lines[0] is clock values for the first line. Remaining lines are continuation lines.
    out = nav_epoch_line(rec.sat, dt, rec.lines[0])
    for line in rec.lines[1:]:
        out += nav_cont_line(line)
    return out


def parse_gps_nav(pkt: Packet) -> Optional[NavRecord]:
    p = pkt.payload
    if len(p) < 224:
        return None
    prn = u32(p, 0)
    if not (1 <= prn <= 42):
        return None
    sys_char = "J" if prn >= 33 else "G"
    sat_prn = prn - 32 if sys_char == "J" else prn
    sat = f"{sys_char}{sat_prn:02d}"
    week = u32(p, 24)
    if week <= 0:
        week = pkt.gps_week or 0
    toe = d64(p, 32)
    toc = d64(p, 164)
    iode1 = u32(p, 16)
    iodc = u32(p, 160)
    health = u32(p, 12)
    ura_m = safe_sqrt_a(d64(p, 216))

    lines = [
        [d64(p, 180), d64(p, 188), d64(p, 196)],
        [float(iode1), d64(p, 104), d64(p, 48), d64(p, 56)],
        [d64(p, 80), d64(p, 64), d64(p, 88), safe_sqrt_a(d64(p, 40))],
        [toe, d64(p, 112), d64(p, 144), d64(p, 120)],
        [d64(p, 128), d64(p, 96), d64(p, 72), d64(p, 152)],
        [d64(p, 136), 1.0, float(week), 0.0],
        [ura_m, float(health), d64(p, 172), float(iodc)],
        [d64(p, 4), 0.0, None, None],
    ]
    return NavRecord(sys_char, sat, int(week), toc, lines, int(week) * 604800 + toc, (sys_char, sat, int(week), toe, toc, iode1, iodc))


def parse_bds_nav(pkt: Packet) -> Optional[NavRecord]:
    p = pkt.payload
    if len(p) < 232:
        return None
    prn = u32(p, 0)
    if not (1 <= prn <= 63):
        return None
    gps_week = u32(p, 24) or (pkt.gps_week or 0)
    if gps_week <= 0:
        return None
    bdt_week = bds_week_from_gps_week(int(gps_week))
    sat = f"C{prn:02d}"
    toe = d64(p, 32)
    toc = d64(p, 164)
    aode = u32(p, 16)
    aodc = u32(p, 160)
    health = u32(p, 12)
    ura_m = safe_sqrt_a(d64(p, 224))

    lines = [
        [d64(p, 188), d64(p, 196), d64(p, 204)],
        [float(aode), d64(p, 104), d64(p, 48), d64(p, 56)],
        [d64(p, 80), d64(p, 64), d64(p, 88), safe_sqrt_a(d64(p, 40))],
        [toe, d64(p, 112), d64(p, 144), d64(p, 120)],
        [d64(p, 128), d64(p, 96), d64(p, 72), d64(p, 152)],
        [d64(p, 136), None, float(bdt_week), None],
        [ura_m, float(health), d64(p, 172), d64(p, 180)],
        [d64(p, 4), float(aodc), None, None],
    ]
    # The date/time is the same calendar time used by Unicore and common tools;
    # the week value inside the record is written as BDT week per RINEX.
    return NavRecord("C", sat, int(gps_week), toc, lines, int(gps_week) * 604800 + toc, ("C", sat, int(gps_week), toe, toc, aode, aodc))


def gal_data_sources(fnav: bool, inav: bool) -> float:
    # RINEX Galileo data sources bitfield. Practical convention:
    # 258 = I/NAV E1B, 513 = F/NAV E5a, 517 = both common data sources.
    if fnav and inav:
        return 517.0
    if fnav:
        return 513.0
    if inav:
        return 258.0
    return 0.0


def gal_health_bits(p: bytes, fnav: bool, inav: bool) -> float:
    # Compact health/data-validity indicator. If all status fields are zero, this is healthy.
    e1b_health, e5a_health, e5b_health = u8(p, 12), u8(p, 13), u8(p, 14)
    e1b_dvs, e5a_dvs, e5b_dvs = u8(p, 15), u8(p, 16), u8(p, 17)
    # Simple combined bit mask that most software treats sensibly; zero == healthy.
    val = 0
    if inav:
        val |= (e1b_health & 0x3) << 0
        val |= (e1b_dvs & 0x1) << 2
        val |= (e5b_health & 0x3) << 3
        val |= (e5b_dvs & 0x1) << 5
    if fnav:
        val |= (e5a_health & 0x3) << 6
        val |= (e5a_dvs & 0x1) << 8
    return float(val)


def parse_gal_nav(pkt: Packet) -> Optional[NavRecord]:
    p = pkt.payload
    if len(p) < 220:
        return None
    sat_id = u32(p, 0)
    if not (1 <= sat_id <= 36):
        return None
    sat = f"E{sat_id:02d}"
    fnav = bool(u32(p, 4))
    inav = bool(u32(p, 8))
    if not (fnav or inav):
        return None
    week = pkt.gps_week or 0
    if week <= 0:
        return None

    toe = float(u32(p, 24))
    # Prefer I/NAV when present because it carries E1/E5b and is usually what mixed RINEX tools expect.
    if inav:
        toc = float(u32(p, 176))
        af0, af1, af2 = d64(p, 180), d64(p, 188), d64(p, 196)
    else:
        toc = float(u32(p, 148))
        af0, af1, af2 = d64(p, 152), d64(p, 160), d64(p, 168)

    iodnav = u32(p, 20)
    sisa = float(u8(p, 18))
    lines = [
        [af0, af1, af2],
        [float(iodnav), d64(p, 92), d64(p, 36), d64(p, 44)],
        [d64(p, 68), d64(p, 52), d64(p, 76), d64(p, 28)],
        [toe, d64(p, 100), d64(p, 132), d64(p, 108)],
        [d64(p, 116), d64(p, 84), d64(p, 60), d64(p, 140)],
        [d64(p, 124), gal_data_sources(fnav, inav), float(week), None],
        [sisa, gal_health_bits(p, fnav, inav), d64(p, 204), d64(p, 212)],
        [toc, None, None, None],
    ]
    return NavRecord("E", sat, int(week), toc, lines, int(week) * 604800 + toc, ("E", sat, int(week), toe, toc, iodnav))


def parse_glo_nav(pkt: Packet) -> Optional[NavRecord]:
    p = pkt.payload
    if len(p) < 144:
        return None
    slot_raw = u16(p, 0)
    slot = slot_raw - 37 if slot_raw >= 38 else slot_raw
    if not (1 <= slot <= 99):
        return None
    sat = f"R{slot:02d}"
    freq_k = int(u16(p, 2)) - 7
    week = int(u16(p, 6)) or (pkt.gps_week or 0)
    e_time_s = u32(p, 8) / 1000.0
    # RINEX GLONASS epoch is usually on the 15-minute boundary of the ephemeris reference.
    toc = math.floor(e_time_s / 900.0) * 900.0
    if week <= 0:
        return None

    # RINEX GLONASS uses km, km/s, km/s^2. Unicore gives m, m/s, m/s^2.
    x, y, z = d64(p, 28) / 1000.0, d64(p, 36) / 1000.0, d64(p, 44) / 1000.0
    vx, vy, vz = d64(p, 52) / 1000.0, d64(p, 60) / 1000.0, d64(p, 68) / 1000.0
    ax, ay, az = d64(p, 76) / 1000.0, d64(p, 84) / 1000.0, d64(p, 92) / 1000.0
    tau_n = d64(p, 100)
    gamma = d64(p, 116)
    health = u32(p, 24)
    age = u32(p, 136)
    # GLONASS Tk is given in GLONASS time. RINEX examples use UTC-like seconds of day.
    tk_utc = (float(u32(p, 124)) - 10800.0) % 86400.0

    lines = [
        [-tau_n, gamma, tk_utc],
        [x, vx, ax, float(health)],
        [y, vy, ay, float(freq_k)],
        [z, vz, az, float(age)],
    ]
    return NavRecord("R", sat, week, toc, lines, week * 604800 + toc, ("R", sat, week, toc, u32(p, 20)))


def parse_nav_records(packets: List[Packet], obs_week: Optional[int], include_all_nav: bool) -> List[NavRecord]:
    records: List[NavRecord] = []
    for pkt in packets:
        rec: Optional[NavRecord] = None
        if pkt.msg_id == MSG_GPSEPHB:
            rec = parse_gps_nav(pkt)
        elif pkt.msg_id == MSG_BDSEPHB:
            rec = parse_bds_nav(pkt)
        elif pkt.msg_id == MSG_GALEPHB:
            rec = parse_gal_nav(pkt)
        elif pkt.msg_id == MSG_GLOEPHB:
            rec = parse_glo_nav(pkt)
        if rec is None:
            continue
        if obs_week is not None and not include_all_nav and rec.gps_week != obs_week:
            continue
        records.append(rec)

    # Deduplicate identical ephemerides. For Galileo, prefer the record with the
    # richer data-source bitfield (usually 517 = both FNAV and INAV) when the
    # orbital parameters and clock epoch are otherwise identical.
    by_key: OrderedDict[Tuple, NavRecord] = OrderedDict()
    for rec in records:
        old = by_key.get(rec.key)
        if old is None:
            by_key[rec.key] = rec
        elif rec.sys == "E":
            old_src = old.lines[5][1] or 0.0
            new_src = rec.lines[5][1] or 0.0
            if new_src > old_src:
                by_key[rec.key] = rec
    return sorted(by_key.values(), key=lambda r: (r.sys, r.sat, r.sort_time_s, r.key))


def nav_header(rinex_version: str, file_kind: str, leap_seconds: int = 18) -> str:
    # file_kind: M mixed, G GPS, R GLONASS, E Galileo, C BDS, J QZSS
    names = {
        "M": "M: MIXED",
        "G": "G: GPS",
        "R": "R: GLONASS",
        "E": "E: GALILEO",
        "C": "C: BDS",
        "J": "J: QZSS",
    }
    kind = names.get(file_kind, file_kind)
    lines = []
    lines.append(rinex_line(f"{float(rinex_version):9.2f}           N: GNSS NAV DATA    {kind:<20}", "RINEX VERSION / TYPE"))
    now = datetime.now(timezone.utc).strftime("%Y%m%d %H%M%S UTC")
    lines.append(rinex_line(f"unicore_full      Python             {now:<20}", "PGM / RUN BY / DATE"))
    lines.append(rinex_line("Direct conversion from Unicore GPSEPH/GLOEPH/BDSEPH/GALEPH", "COMMENT"))
    lines.append(rinex_line(f"{leap_seconds:6d}", "LEAP SECONDS"))
    lines.append(rinex_line("", "END OF HEADER"))
    return "".join(lines)


def write_nav_file(path: Path, records: List[NavRecord], rinex_version: str, file_kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    selected = [r for r in records if file_kind == "M" or r.sys == file_kind]
    if not selected:
        return
    text = nav_header(rinex_version, file_kind) + "".join(nav_record_to_text(r) for r in selected)
    path.write_text(text, encoding="ascii", newline="")


def infer_gps_week_from_ephemerides(packets: List[Packet]) -> Optional[int]:
    candidates: Counter[int] = Counter()
    for pkt in packets:
        if pkt.msg_id in (MSG_GPSEPHB, MSG_BDSEPHB) and len(pkt.payload) >= 32:
            w = u32(pkt.payload, 24)
            if 2000 <= w <= 4000:
                candidates[w] += 1
        elif pkt.msg_id == MSG_GLOEPHB and len(pkt.payload) >= 8:
            w = u16(pkt.payload, 6)
            if 2000 <= w <= 4000:
                candidates[w] += 1
        elif pkt.msg_id == MSG_GALEPHB and pkt.gps_week and 2000 <= pkt.gps_week <= 4000:
            candidates[pkt.gps_week] += 1
    return max(candidates) if candidates else None


def infer_gps_week_from_obs_packets(packets: List[Packet], obs_source: str) -> Optional[int]:
    msg_ids = OBS_SOURCE_IDS[obs_source]
    candidates = Counter(pkt.gps_week for pkt in packets if pkt.msg_id in msg_ids and pkt.gps_week and 2000 <= pkt.gps_week <= 4000)
    return max(candidates) if candidates else None


def legacy_year_suffix(gps_week: int) -> str:
    year = (GPS_EPOCH + timedelta(weeks=gps_week)).year % 100
    return f"{year:02d}"


def run_conversion(args: argparse.Namespace) -> Dict[str, Path]:
    if not args.input.exists():
        raise SystemExit(f"Input file does not exist: {args.input}")

    outdir: Path = args.output_dir
    outdir.mkdir(parents=True, exist_ok=True)
    basename = args.basename or args.input.stem
    buf = args.input.read_bytes()
    packets = list(iter_packets(buf, check_crc=not args.no_crc))
    packet_counts = Counter(pkt.msg_id for pkt in packets)
    obs_source = choose_obs_source(packets, args.obs_source)

    gps_week = args.gps_week
    if args.date:
        gps_week = gps_week_from_date(args.date)
    if gps_week is None:
        gps_week = infer_gps_week_from_obs_packets(packets, obs_source) or infer_gps_week_from_ephemerides(packets)
    if gps_week is None:
        raise SystemExit("Could not infer GPS week. Supply --date YYYY-MM-DD or --gps-week.")

    signal_map = SIGNAL_MAP_LEGACY_BDS if args.legacy_bds_codes else SIGNAL_MAP_STANDARD
    epochs, decoded_signal_counts, skipped_signals = read_observations(
        packets,
        signal_map=signal_map,
        obs_source=obs_source,
        max_epochs=args.max_epochs,
    )
    epochs = filter_epochs_for_obs_profile(epochs, args.obs_profile)
    if args.min_sats > 1:
        epochs = OrderedDict((tow, sats) for tow, sats in epochs.items() if len(sats) >= args.min_sats)
    signal_counts = count_obs_signals(epochs)
    approx_position = parse_bestnavxyz_approx_position(packets)

    yy = legacy_year_suffix(gps_week)
    obs_path = outdir / f"{basename}.{yy}O"
    write_rinex_obs(obs_path, epochs, gps_week, args.rinex_version, args.marker, approx_position)

    nav_records = parse_nav_records(packets, obs_week=gps_week, include_all_nav=args.include_all_nav)
    paths = {
        "OBS": obs_path,
        "MIXED_NAV": outdir / f"{basename}.{yy}P",
        "GPS_NAV": outdir / f"{basename}.{yy}N",
        "GLO_NAV": outdir / f"{basename}.{yy}G",
        "BDS_NAV": outdir / f"{basename}.{yy}C",
        "GAL_NAV": outdir / f"{basename}.{yy}L",
    }
    write_nav_file(paths["MIXED_NAV"], nav_records, args.rinex_version, "M")
    write_nav_file(paths["GPS_NAV"], nav_records, args.rinex_version, "G")
    write_nav_file(paths["GLO_NAV"], nav_records, args.rinex_version, "R")
    write_nav_file(paths["BDS_NAV"], nav_records, args.rinex_version, "C")
    write_nav_file(paths["GAL_NAV"], nav_records, args.rinex_version, "E")

    # Optional zip convenience output.
    if args.zip:
        zip_path = outdir / f"{basename}_rinex305.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in paths.values():
                if p.exists():
                    zf.write(p, arcname=p.name)
        paths["ZIP"] = zip_path

    # Write a small conversion report.
    report_path = outdir / f"{basename}_conversion_report.txt"
    nav_counts = Counter(r.sys for r in nav_records)
    with report_path.open("w", encoding="utf-8") as f:
        f.write(f"Input: {args.input}\n")
        f.write(f"RINEX version: {args.rinex_version}\n")
        f.write(f"GPS week: {gps_week}\n")
        f.write(f"OBS source: {obs_source} ({OBS_SOURCE_LABELS[obs_source]})\n")
        f.write(f"OBS profile: {args.obs_profile}\n")
        f.write(f"Packets parsed with CRC {'OFF' if args.no_crc else 'ON'}:\n")
        for mid, cnt in sorted(packet_counts.items()):
            f.write(f"  ID {mid}: {cnt}\n")
        f.write(f"\nOBS epochs: {len(epochs)}\n")
        f.write(f"OBS satellite epoch lines: {sum(len(s) for s in epochs.values())}\n")
        f.write("OBS signals kept:\n")
        for k, cnt in sorted(signal_counts.items()):
            f.write(f"  {k[0]}{k[1]}: {cnt}\n")
        if args.obs_profile != "full":
            f.write("OBS signals decoded before profile filtering:\n")
            for k, cnt in sorted(decoded_signal_counts.items()):
                f.write(f"  {k[0]}{k[1]}: {cnt}\n")
        if skipped_signals:
            f.write("Skipped/unmapped signal types:\n")
            for (sys_bits, sig_bits), cnt in skipped_signals.most_common():
                f.write(f"  system={sys_bits}, signal={sig_bits}: {cnt}\n")
        f.write("\nNAV records written:\n")
        for sys_char in ("G", "R", "E", "C", "J"):
            if nav_counts[sys_char]:
                f.write(f"  {sys_char}: {nav_counts[sys_char]}\n")
        f.write("\nFiles:\n")
        for label, p in paths.items():
            if p.exists():
                f.write(f"  {label}: {p.name}\n")
    paths["REPORT"] = report_path

    print(f"Wrote RINEX files to: {outdir}")
    print(f"GPS week: {gps_week}")
    print(f"OBS source: {obs_source} ({OBS_SOURCE_LABELS[obs_source]})")
    print(f"OBS epochs: {len(epochs):,}")
    print("NAV records:", ", ".join(f"{sys}={nav_counts[sys]}" for sys in sorted(nav_counts)))
    print("Files:")
    for label, p in paths.items():
        if p.exists():
            print(f"  {label}: {p}")
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert Unicore/UM982 BIN directly to RINEX 3.05 OBS + NAV files.")
    ap.add_argument("recording", help="Recording output directory, e.g. 20260503_132939Z_test_log_1")
    ap.add_argument("--input", type=Path, help="Optional explicit original or cleaned Unicore .BIN recording")
    ap.add_argument("-o", "--output-dir", type=Path, help="Output folder. Default: recording/rinex")
    ap.add_argument("--basename", help="Base name for output files. Default: input file stem")
    ap.add_argument("--rinex-version", default="3.05", choices=["3.03", "3.05"], help="RINEX version to write")
    ap.add_argument("--date", help="Recording date YYYY-MM-DD; used to determine GPS week")
    ap.add_argument("--gps-week", type=int, help="GPS week override. For 2026-05-03 use 2417")
    ap.add_argument("--marker", default="UM982_ROVER", help="RINEX marker name")
    ap.add_argument(
        "--obs-source",
        default="auto",
        choices=["auto", "rangeb", "rangecmpb", "obsvmb", "obsvmcmpb", "obsvhb", "obsvhcmpb"],
        help=(
            "Raw observation log to use. auto prefers master antenna logs: "
            "RANGECMPB, then OBSVMCMPB, then OBSVMB, then RANGEB. "
            "Use obsvhcmpb/obsvhb for the slave antenna."
        ),
    )
    ap.add_argument("--min-sats", type=int, default=4, help="Drop OBS epochs with fewer than this many satellites")
    ap.add_argument("--max-epochs", type=int, help="Debug: convert only first N observation epochs")
    ap.add_argument(
        "--obs-profile",
        default="rtklib",
        choices=["rtklib", "full"],
        help="Observation signal profile. rtklib keeps one supported primary signal per constellation.",
    )
    ap.add_argument("--no-crc", action="store_true", help="Disable CRC checking")
    ap.add_argument("--legacy-bds-codes", action="store_true", help="Use legacy BDS OBS C1C/C3C instead of standard C2I/C6I")
    ap.add_argument("--include-all-nav", action="store_true", help="Keep old NAV records from receiver memory instead of filtering to the observation GPS week")
    ap.add_argument("--zip", action="store_true", help="Also create a ZIP with generated RINEX files")
    args = ap.parse_args()
    session_dir = resolve_session_dir(args.recording)
    args.input = args.input or find_original_bin(session_dir)
    args.output_dir = args.output_dir or output_subdir(session_dir, "rinex")
    run_conversion(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
