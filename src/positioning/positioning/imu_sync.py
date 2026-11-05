"""GNSS ↔ XDK/IMU laika sinhronizācija braucienam: poga, manuāli (laiks / punktu pāri / nobīdīšana) vai yaw korelācija.

Visur glabājam absolūtu `xdk_clock0_utc` (UTC epoch sekundes, kad XDK pulkstenis rāda 0). Pogas sinhronizācija
tiek rēķināta pret vecāka PILNO BIN (rx_bytes ir pilnā faila nobīdes), tāpēc brauciena BIN to nepārrēķina.
"""
from __future__ import annotations

import statistics
from pathlib import Path

from . import store
from .paths import OUT_DIR, session_dir

MARGIN_S = 30.0


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except SystemExit as exc:  # esošie skripti beidzas ar SystemExit(teksts)
        raise ValueError(str(exc)) from None


def attach_to_parent(parent: str, xdk: str, xdk_sync: str | None = None, gnss_sync: str | None = None,
                     note: str = "", make_default: bool | None = None) -> dict:
    """Piesaista XDK žurnālu (un SYNC failus) garajam ierakstam; pogas sinhronizāciju aprēķina pret pilno BIN."""
    import attach_xdk
    return _wrap(attach_xdk.attach, session_dir(parent), Path(xdk), Path(xdk_sync) if xdk_sync else None,
                 Path(gnss_sync) if gnss_sync else None, make_default, note)


def parent_links(parent: str) -> dict:
    import imu_links
    return imu_links.load(session_dir(parent))


def resolve_xdk(parent: str, xdk: str) -> Path:
    p = Path(xdk)
    if p.is_file():
        return p.resolve()
    cand = session_dir(parent) / "imu" / Path(xdk).name
    if cand.is_file():
        return cand.resolve()
    raise ValueError(f"XDK fails nav atrasts: {xdk}")


def clock0_from_pairs(pairs: list[dict]) -> tuple[float, float]:
    """Pāri {gnss_utc, xdk_t_s} -> (mediānā clock0, izkliede ms). Lietotājs norāda, kurā GNSS laikā notika kāds XDK notikums."""
    if not pairs:
        raise ValueError("Nav punktu pāru.")
    vals = [store.parse_utc(p["gnss_utc"]) - float(p["xdk_t_s"]) for p in pairs]
    med = statistics.median(vals)
    spread = (max(vals) - min(vals)) * 1000.0 if len(vals) > 1 else 0.0
    return med, spread


def trim_xdk_csv(src: Path, dst: Path, t_lo_s: float, t_hi_s: float) -> int:
    """Izgriež XDK CSV rindas ar t_ms ∈ [t_lo, t_hi] sekundēs (galvene paliek)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with src.open("r", encoding="utf-8-sig") as f, dst.open("w", encoding="utf-8", newline="") as o:
        o.write(f.readline())
        for line in f:
            try:
                t = float(line.split(",", 1)[0]) / 1000.0
            except ValueError:
                continue
            if t_lo_s <= t <= t_hi_s:
                o.write(line if line.endswith("\n") else line + "\n")
                n += 1
    return n


def _trip_points(trip: dict):
    import gnss_curves
    return _wrap(gnss_curves.load_curve, OUT_DIR / trip["session"], "bestnav")


def suggest(trip_id: str, xdk: str) -> dict:
    """Pieejamie clock0 aprēķini: poga (no vecāka) un yaw korelācija uz brauciena logu."""
    from xdk_imu import find_offset, load_xdk
    trip = store.get_trip(trip_id)
    parent = trip["parent"]
    path = resolve_xdk(parent, xdk)
    out: dict = {"xdk": path.name, "button": None, "yaw": None}
    entry = parent_links(parent)["files"].get(path.name, {})
    sync = entry.get("sync") or {}
    if sync.get("xdk_clock0_utc"):
        out["button"] = {"xdk_clock0_utc": sync["xdk_clock0_utc"], "confidence": sync.get("confidence"),
                         "spread_ms": sync.get("spread_ms"), "pairs": sync.get("pairs")}
    try:
        pts = _trip_points(trip)
        res = find_offset(_wrap(load_xdk, path), pts)
        out["yaw"] = {"xdk_clock0_utc": pts[0].time.timestamp() + res.offset_s, "correlation": res.correlation,
                      "second_correlation": res.second_correlation, "confidence": res.confidence,
                      "overlap_s": res.overlap_s}
    except (ValueError, OSError) as exc:
        out["yaw_error"] = str(exc)
    if out["button"] and out["yaw"]:
        out["button_vs_yaw_ms"] = (out["button"]["xdk_clock0_utc"] - out["yaw"]["xdk_clock0_utc"]) * 1000.0
    return out


def overlap_s(path: Path, clock0: float, start: float, end: float) -> float:
    from xdk_imu import load_xdk
    x = _wrap(load_xdk, path)
    return max(0.0, min(end, clock0 + float(x.t[-1])) - max(start, clock0 + float(x.t[0])))


def set_sync(trip_id: str, method: str, xdk: str, xdk_clock0_utc=None, pairs: list[dict] | None = None,
             shift_s: float | None = None, note: str = "") -> dict:
    """method: button | manual | pairs | yaw. Saglabā brauciena sync + izgrieztu XDK CSV brauciena imu/ mapē."""
    import imu_links
    trip = store.get_trip(trip_id)
    parent = trip["parent"]
    path = resolve_xdk(parent, xdk)
    info: dict = {}
    if method == "button":
        sug = suggest(trip_id, xdk)["button"]
        if xdk_clock0_utc is None:
            if not sug:
                raise ValueError("Šim XDK vecākam nav pogas sinhronizācijas (piesaisti ar SYNC failiem vai izmanto manual).")
            xdk_clock0_utc = sug["xdk_clock0_utc"]
            info = {"confidence": sug.get("confidence"), "spread_ms": sug.get("spread_ms")}
    elif method == "yaw":
        sug = suggest(trip_id, xdk)
        if not sug["yaw"]:
            raise ValueError(f"Yaw sinhronizācija nav iespējama: {sug.get('yaw_error', 'nav kustības')}")
        xdk_clock0_utc = sug["yaw"]["xdk_clock0_utc"]
        info = {"confidence": sug["yaw"]["confidence"], "correlation": sug["yaw"]["correlation"]}
    elif method == "pairs":
        xdk_clock0_utc, spread = clock0_from_pairs(pairs or [])
        info = {"spread_ms": spread, "pairs": len(pairs or [])}
    elif method == "manual":
        if xdk_clock0_utc is None:
            prev = (trip.get("sync") or {}).get("xdk_clock0_utc")
            if shift_s is None or prev is None:
                raise ValueError("manual: norādi xdk_clock0_utc vai shift_s (ja sync jau ir iestatīts).")
            xdk_clock0_utc = prev + float(shift_s)
        xdk_clock0_utc = store.parse_utc(xdk_clock0_utc)
    else:
        raise ValueError(f"Nezināma metode: {method}")
    if shift_s is not None and method != "manual":
        xdk_clock0_utc = float(xdk_clock0_utc) + float(shift_s)
    clock0 = float(xdk_clock0_utc)
    start, end = store.parse_utc(trip["start_utc"]), store.parse_utc(trip["end_utc"])

    ov = overlap_s(path, clock0, start, end)
    warnings = [] if ov >= 0.8 * (end - start) else [f"XDK pārklājas tikai {ov:.0f} s no {end - start:.0f} s brauciena."]
    session = OUT_DIR / trip["session"]
    trimmed = session / "imu" / path.name
    rows = trim_xdk_csv(path, trimmed, start - MARGIN_S - clock0, end + MARGIN_S - clock0)
    if rows < 100:
        warnings.append(f"Izgrieztajā XDK ir tikai {rows} rindas.")
    sync = {"xdk": path.name, "method": method, "xdk_clock0_utc": clock0, "xdk_clock0": store.iso(clock0),
            "overlap_s": ov, "trimmed_rows": rows, "note": note, "updated": store.now(), "warnings": warnings, **info}
    imu_links.register(session, path.name, {"kind": "xdk", "attached_utc": store.now(), "note": f"trip sync ({method})",
                                            "source": str(path), "sync": {k: sync[k] for k in ("xdk_clock0_utc", "xdk_clock0") },
                                            "duration_s": None, "overlap_s": ov, "warnings": warnings}, True)
    store.update_trip(trip_id, sync=sync)
    return sync
