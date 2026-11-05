"""Ātra Unicore BIN pakešu skenēšana (N4 AA44B5 un OEM AA4412) ar CRC pārbaudi un laika indeksu."""
from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GPS_EPOCH_UNIX = 315964800.0  # 1980-01-06 00:00:00 UTC
WEEK_S = 604800.0
MIN_VALID_WEEK = 2086  # 2020-01-05; mazākas nedēļas (piem. 1) = uztvērējs vēl bez laika
DEFAULT_LEAP_S = 18
EPHEMERIS_IDS = (106, 107, 108, 109)  # GPS, GLO, BDS, GAL

_SYNC = re.compile(rb"\xaa\x44[\x12\xb5]")


def unicore_crc(data: bytes) -> int:
    """NovAtel/Unicore CRC32 (init 0, bez gala XOR) caur zlib."""
    return (zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF) & 0xFFFFFFFF


@dataclass
class Pkt:
    pos: int
    total: int
    msg_id: int
    n4: bool
    hlen: int
    week: int
    tow_ms: int
    leap: int

    @property
    def valid_time(self) -> bool:
        return self.week >= MIN_VALID_WEEK

    @property
    def gps_s(self) -> float:
        return self.week * WEEK_S + self.tow_ms / 1000.0


def iter_pkts(buf: bytes, check_crc: bool = True):
    n = len(buf)
    pos = 0
    while pos < n:
        m = _SYNC.search(buf, pos)
        if not m:
            return
        p = m.start()
        if buf[p + 2] == 0xB5:
            if p + 28 > n:
                return
            hlen = 24
            msg_id = struct.unpack_from("<H", buf, p + 4)[0]
            plen = struct.unpack_from("<H", buf, p + 6)[0]
            week = struct.unpack_from("<H", buf, p + 10)[0]
            tow = struct.unpack_from("<I", buf, p + 12)[0]
            leap = buf[p + 21]
            n4 = True
        else:
            if p + 28 > n:
                return
            hlen = buf[p + 3]
            if hlen < 28 or hlen > 128:
                pos = p + 1
                continue
            msg_id = struct.unpack_from("<H", buf, p + 4)[0]
            plen = struct.unpack_from("<H", buf, p + 8)[0]
            week = struct.unpack_from("<H", buf, p + 14)[0]
            tow = struct.unpack_from("<I", buf, p + 16)[0]
            leap = 0
            n4 = False
        total = hlen + plen + 4
        if total > 1_000_000:
            pos = p + 1
            continue
        if p + total > n:
            return
        if check_crc:
            expected = struct.unpack_from("<I", buf, p + total - 4)[0]
            if unicore_crc(buf[p:p + total - 4]) != expected:
                pos = p + 1
                continue
        yield Pkt(p, total, msg_id, n4, hlen, week, tow, leap)
        pos = p + total


def rewrite_time(packet: bytes, n4: bool, hlen: int, week: int, tow_ms: int) -> bytes:
    """Pārraksta paketes headera GPS nedēļu/ms un pārrēķina CRC."""
    b = bytearray(packet)
    if n4:
        struct.pack_into("<H", b, 10, week)
        struct.pack_into("<I", b, 12, tow_ms)
    else:
        struct.pack_into("<H", b, 14, week)
        struct.pack_into("<I", b, 16, tow_ms)
    struct.pack_into("<I", b, len(b) - 4, unicore_crc(bytes(b[:-4])))
    return bytes(b)


class BinIndex:
    """Visu pakešu tabula: offset, garums, msg_id, n4, hlen, UTC (nan, ja nav laika)."""

    def __init__(self, pos, total, msg, n4, hlen, week, tow, utc, leap, size):
        self.pos, self.total, self.msg, self.n4, self.hlen = pos, total, msg, n4, hlen
        self.week, self.tow, self.utc, self.leap, self.size = week, tow, utc, leap, size

    @classmethod
    def build(cls, path: Path) -> "BinIndex":
        buf = Path(path).read_bytes()
        pkts = list(iter_pkts(buf))
        leap = DEFAULT_LEAP_S
        for p in pkts:
            if p.n4 and p.valid_time and 10 <= p.leap <= 30:
                leap = p.leap
                break
        a = lambda f, dt: np.array([f(p) for p in pkts], dtype=dt)
        week = a(lambda p: p.week, np.int64)
        tow = a(lambda p: p.tow_ms, np.int64)
        gps = week * WEEK_S + tow / 1000.0
        utc = np.where(week >= MIN_VALID_WEEK, GPS_EPOCH_UNIX + gps - leap, np.nan)
        return cls(a(lambda p: p.pos, np.int64), a(lambda p: p.total, np.int64), a(lambda p: p.msg_id, np.int64),
                   a(lambda p: p.n4, bool), a(lambda p: p.hlen, np.int64), week, tow, utc, leap, len(buf))

    def save(self, path: Path) -> None:
        tmp = Path(str(path) + ".tmp")
        with tmp.open("wb") as f:
            np.savez_compressed(f, pos=self.pos, total=self.total, msg=self.msg, n4=self.n4, hlen=self.hlen,
                                week=self.week, tow=self.tow, utc=self.utc, leap=self.leap, size=self.size)
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "BinIndex":
        z = np.load(path)
        return cls(z["pos"], z["total"], z["msg"], z["n4"], z["hlen"], z["week"], z["tow"], z["utc"],
                   int(z["leap"]), int(z["size"]))

    @classmethod
    def cached(cls, bin_path: Path, cache: Path) -> "BinIndex":
        size = Path(bin_path).stat().st_size
        if cache.is_file():
            try:
                idx = cls.load(cache)
                if idx.size == size:
                    return idx
            except Exception:
                pass
        idx = cls.build(bin_path)
        cache.parent.mkdir(parents=True, exist_ok=True)
        idx.save(cache)
        return idx

    def time_range(self) -> tuple[float, float] | None:
        ok = self.utc[~np.isnan(self.utc)]
        return (float(ok.min()), float(ok.max())) if len(ok) else None
