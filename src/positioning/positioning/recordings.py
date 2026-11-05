"""Garo ierakstu saraksts un pārskats (trajektorija + ātrums + satelīti pa laiku) dalīšanas izvēlei."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from . import pipeline, splitter, store, tracks
from .paths import OUT_DIR, session_dir


def list_recordings() -> list[dict]:
    out = []
    for d in sorted(OUT_DIR.iterdir() if OUT_DIR.is_dir() else []):
        if not d.is_dir() or (d / "trip.json").is_file():
            continue
        bins = list((d / "original").glob("*.[Bb][Ii][Nn]")) if (d / "original").is_dir() else []
        if len(bins) != 1:
            continue
        tf = d / "trips" / "trips.json"
        out.append({"id": d.name, "bin": bins[0].name, "bytes": bins[0].stat().st_size,
                    "has_csv": (d / "csv" / "bestnavxyz.csv").is_file(),
                    "trips": len(store.list_trips(d.name)) if tf.is_file() else 0})
    return out


def _sats_by_time(csv_path: Path) -> tuple[np.ndarray, np.ndarray]:
    t, s = [], []
    with csv_path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                t.append(store.parse_utc(r["utc"]))
                s.append(int(float(r.get("satellites_used") or 0)))
            except (ValueError, KeyError):
                continue
    o = np.argsort(t)
    return np.array(t)[o], np.array(s)[o]


def overview(recording: str, step_s: float = 1.0) -> dict:
    pdir = session_dir(recording)
    if not (pdir / "csv" / "bestnavxyz.csv").is_file():
        for cmd in pipeline.commands_for("csv", pdir):
            res = pipeline._run(cmd, None)
            if res["returncode"] != 0:
                raise ValueError(f"CSV izgūšana neizdevās: {res['stderr'][-300:]}")
    idx = splitter.get_index(recording)
    tr = tracks.load_track(pdir, "gnss:bestnav")
    keep = [0]
    for i in range(1, len(tr)):
        if tr.t[i] - tr.t[keep[-1]] >= step_s:
            keep.append(i)
    k = np.array(keep)
    st, ss = _sats_by_time(pdir / "csv" / "bestnavxyz.csv")
    sats = ss[np.clip(np.searchsorted(st, tr.t[k]), 0, len(ss) - 1)] if len(ss) else np.zeros(len(k), int)
    rng = idx.time_range()
    return {
        "recording": recording, "start_utc": store.iso(rng[0]) if rng else None, "end_utc": store.iso(rng[1]) if rng else None,
        "duration_s": (rng[1] - rng[0]) if rng else None, "packets": int(len(idx.pos)),
        "track": tracks.to_geojson(tr, max_vertices=len(k)) if len(k) == len(tr) else tracks.to_geojson(
            tracks.Track(tr.id, tr.label, tr.t[k], tr.lat[k], tr.lon[k], tr.h[k], tr.speed[k] if tr.speed is not None else None, tr.color),
            max_vertices=len(k)),
        "timeline": {"t": [store.iso(x) for x in tr.t[k]],
                     "speed_mps": [round(float(x), 2) for x in (tr.speed[k] if tr.speed is not None else [])],
                     "satellites": [int(x) for x in sats]},
        "trips": store.list_trips(recording),
    }


def session_tree() -> list[dict]:
    """Ieraksti ar saviem braucieniem (kartes sānjoslai)."""
    out = []
    for r in list_recordings():
        d = OUT_DIR / r["id"]
        trips = [{"id": t["session"], "label": t["name"], "kind": "trip", "start_utc": t["start_utc"], "end_utc": t["end_utc"],
                  "sync": bool(t.get("sync")), "video": bool(t.get("video"))} for t in store.list_trips(r["id"])] \
            if (d / "trips" / "trips.json").is_file() else []
        out.append({"id": r["id"], "label": r["id"], "kind": "recording", "has_csv": r["has_csv"], "children": trips})
    return out


def session_catalog(name: str) -> dict:
    import imu_links
    d = session_dir(name)
    link = imu_links.resolve_xdk(d)
    is_trip = (d / "trip.json").is_file()
    sync = (link.entry.get("sync") if link else None) or {}
    return {"id": name, "is_trip": is_trip, "tracks": tracks.catalog(d), "xdk": link.name if link else None,
            "has_sync": bool(sync.get("xdk_clock0_utc")),
            "can_fuse": bool(is_trip and link and sync.get("xdk_clock0_utc")),
            "can_imu_raw": bool(link),
            "videos": _videos(name, d, is_trip)}


def _videos(name: str, d: Path, is_trip: bool) -> list[dict]:
    """Sesijai piesaistītie video: brauciena video vai visa ieraksta video/ mapes faili."""
    from . import video, workspace
    if is_trip:
        v = store.get_trip(name).get("video")
        return [{"kind": "trip", "name": Path(v["path"]).name, "start_utc": v["start_utc"], "linked": True,
                 "url": f"/api/trips/{name}/video/stream"}] if v else []
    vdir = d / "video"
    files = sorted(p.name for p in vdir.iterdir() if p.suffix.lower() in workspace.VIDEO_EXT) if vdir.is_dir() else []
    if not files:
        return []
    links = video.rec_video_links(name)
    default = video.default_start(name)
    return [{"kind": "recording", "name": f, "start_utc": (links.get(f) or {}).get("start_utc", default),
             "linked": f in links, "url": f"/api/recordings/{name}/video/{f}"} for f in files]
