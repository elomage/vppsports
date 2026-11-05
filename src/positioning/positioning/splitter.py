"""Garā ieraksta sadalīšana laika intervālā: jauna sesijas mape ar BIN izgriezumu + ephemeris pārnešanu."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from . import store
from .binpackets import EPHEMERIS_IDS, GPS_EPOCH_UNIX, WEEK_S, BinIndex, rewrite_time
from .paths import OUT_DIR, session_dir

SUBDIRS = ("original", "csv", "rinex", "ppk", "other", "imu", "sync")


def parent_bin(parent_dir: Path) -> Path:
    bins = sorted({p.resolve() for pat in ("*.BIN", "*.bin") for p in (parent_dir / "original").glob(pat)})
    if len(bins) != 1:
        raise ValueError(f"{parent_dir.name}/original jāsatur tieši vienu BIN (atrasti {len(bins)}).")
    return bins[0]


def get_index(parent: str) -> BinIndex:
    d = session_dir(parent)
    return BinIndex.cached(parent_bin(d), d / "trips" / "bin_index.npz")


def _eph_key(blob: bytes, pos: int, hlen: int, msg: int) -> tuple:
    return (msg, blob[pos + hlen:pos + hlen + 4])


def plan(idx: BinIndex, buf: bytes, start: float, end: float) -> dict:
    """Izvēlas paketes: loga paketes + katram satelītam tuvākā ephemeris, kuras logā nav."""
    inside = np.where(~np.isnan(idx.utc) & (idx.utc >= start) & (idx.utc < end))[0]
    if not len(inside):
        raise ValueError("Norādītajā laika logā nav neviena paketes ar derīgu laiku.")
    first_pos = int(idx.pos[inside[0]])
    last_pos = int(idx.pos[inside[-1]])
    in_set = set(int(i) for i in inside)
    eph_idx = [i for i in range(len(idx.pos)) if int(idx.msg[i]) in EPHEMERIS_IDS]
    in_window_keys, before, after = set(), {}, {}
    for i in eph_idx:
        key = _eph_key(buf, int(idx.pos[i]), int(idx.hlen[i]), int(idx.msg[i]))
        p = int(idx.pos[i])
        if i in in_set:
            in_window_keys.add(key)
        elif p < first_pos:
            before[key] = i  # pēdējā pirms loga
        elif p > last_pos:
            after.setdefault(key, i)  # pirmā pēc loga
    carry = []
    for key, i in before.items():
        if key not in in_window_keys:
            carry.append(i)
    for key, i in after.items():
        if key not in in_window_keys and key not in before:
            carry.append(i)
    carry.sort(key=lambda i: int(idx.pos[i]))
    return {"inside": [int(i) for i in inside], "carry": carry}


def split(parent: str, start, end, name: str = "") -> dict:
    """Izveido jaunu brauciena sesiju. Atgriež brauciena ierakstu (dict), kas saglabāts trips.json."""
    start_s, end_s = store.parse_utc(start), store.parse_utc(end)
    if end_s <= start_s:
        raise ValueError("Beigu laikam jābūt vēlākam par sākuma laiku.")
    pdir = session_dir(parent)
    src = parent_bin(pdir)
    idx = get_index(parent)
    buf = src.read_bytes()
    chosen = plan(idx, buf, start_s, end_s)
    inside, carry = chosen["inside"], chosen["carry"]

    first = idx.utc[inside[0]]
    first_gps = first + idx.leap - GPS_EPOCH_UNIX
    week, tow_ms = int(first_gps // WEEK_S), int(round((first_gps % WEEK_S) * 1000))

    trips = store.list_trips(parent)
    trip_id = store.next_id(parent, trips)
    sdir = OUT_DIR / trip_id
    sdir.mkdir(parents=True)
    for sub in SUBDIRS:
        (sdir / sub).mkdir(exist_ok=True)

    out = bytearray()
    for i in carry:  # ephemeris ar derīgu headera laiku (Galileo nedēļu ņem no headera)
        p, t, h = int(idx.pos[i]), int(idx.total[i]), int(idx.hlen[i])
        out += rewrite_time(buf[p:p + t], bool(idx.n4[i]), h, week, tow_ms)
    for i in inside:
        p, t = int(idx.pos[i]), int(idx.total[i])
        out += buf[p:p + t]
    (sdir / "original" / src.name).write_bytes(bytes(out))

    msgs = [int(m) for m in idx.msg[inside]]
    warnings = []
    for mid, label in ((106, "GPS"), (107, "GLONASS"), (108, "BDS"), (109, "Galileo")):
        n_in = sum(1 for m in msgs if m == mid)
        n_carry = sum(1 for i in carry if int(idx.msg[i]) == mid)
        if n_in + n_carry == 0:
            warnings.append(f"Nav {label} ephemeris (ID {mid}) — RINEX NAV šai konstelācijai būs tukšs.")
    trip = {
        "id": trip_id, "parent": parent, "session": trip_id,
        "name": name or f"Brauciens {trip_id.rsplit('__t', 1)[1]}",
        "start_utc": store.iso(start_s), "end_utc": store.iso(end_s),
        "actual_start_utc": store.iso(float(idx.utc[inside[0]])), "actual_end_utc": store.iso(float(idx.utc[inside[-1]])),
        "created": store.now(), "packets": len(inside), "ephemeris_carried": len(carry),
        "warnings": warnings, "status": {"split": store.now()}, "sync": None, "video": None,
    }
    for other in trips:  # pārklāšanās brīdinājums
        o0, o1 = store.parse_utc(other["start_utc"]), store.parse_utc(other["end_utc"])
        if start_s < o1 and end_s > o0:
            warnings.append(f"Pārklājas ar {other['id']}.")
    (sdir / "trip.json").write_text(json.dumps(trip, indent=2, ensure_ascii=False), encoding="utf-8")
    store.add_trip(parent, trip)
    return trip


def delete_trip_session(trip_id: str) -> None:
    d = OUT_DIR / trip_id
    if d.is_dir() and (d / "trip.json").is_file():  # dzēš tikai mapes, ko izveidojis dalītājs
        shutil.rmtree(d)
