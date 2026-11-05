"""Video saistīšana ar laiku: vienkārša nobīde (video t=0 -> UTC), pozīcija pēc video laika."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from . import store, tracks as tr
from .paths import OUT_DIR


def probe(path: Path) -> dict:
    """Ilgums un izveides laiks ar ffprobe (ja pieejams)."""
    info = {"duration_s": None, "creation_utc": None}
    exe = shutil.which("ffprobe")
    if not exe:
        return info
    try:
        r = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_format", str(path)],
                           capture_output=True, text=True, timeout=30)
        fmt = json.loads(r.stdout).get("format", {})
        info["duration_s"] = float(fmt["duration"]) if "duration" in fmt else None
        ct = fmt.get("tags", {}).get("creation_time")
        if ct:
            info["creation_utc"] = store.parse_utc(ct)
    except Exception:
        pass
    return info


def _trip_track(trip_id: str, track_id: str) -> tr.Track:
    return tr.load_track(OUT_DIR / store.get_trip(trip_id)["session"], track_id)


def set_video(trip_id: str, path: str | None = None, start_utc=None, video_t: float | None = None, utc=None,
              lat: float | None = None, lon: float | None = None, shift_s: float | None = None,
              track: str = "gnss:bestnav", duration_s: float | None = None) -> dict:
    """Uzstāda/maina video nobīdi. Veidi: start_utc | (video_t + utc) | (video_t + lat/lon) | shift_s."""
    trip = store.get_trip(trip_id)
    cur = dict(trip.get("video") or {})
    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            raise ValueError(f"Video fails nav atrasts: {path}")
        cur["path"] = str(p.resolve())
        meta = probe(p)
        cur["duration_s"] = duration_s or meta["duration_s"]
        if "start_utc" not in cur:
            guess = meta["creation_utc"]
            cur["start_utc"] = guess if guess else (p.stat().st_mtime - (cur["duration_s"] or 0.0))
            cur["start_guess"] = "ffprobe" if guess else "mtime"
    if "path" not in cur:
        raise ValueError("Vispirms jānorāda video fails (path).")
    if duration_s:
        cur["duration_s"] = duration_s
    if start_utc is not None:
        cur["start_utc"] = store.parse_utc(start_utc)
        cur.pop("start_guess", None)
    elif video_t is not None and utc is not None:
        cur["start_utc"] = store.parse_utc(utc) - float(video_t)
        cur.pop("start_guess", None)
    elif video_t is not None and lat is not None and lon is not None:
        t = _trip_track(trip_id, track)
        x, y = tr.xy(t.lat, t.lon, lat, lon)
        cur["start_utc"] = float(t.t[int(np.argmin(np.hypot(x, y)))]) - float(video_t)
        cur.pop("start_guess", None)
    elif shift_s is not None:
        cur["start_utc"] = float(cur["start_utc"]) + float(shift_s)
        cur.pop("start_guess", None)
    cur["start_utc_iso"] = store.iso(cur["start_utc"])
    cur["updated"] = store.now()
    store.update_trip(trip_id, video=cur)
    return cur


def get_video(trip_id: str) -> dict | None:
    return store.get_trip(trip_id).get("video")


def position(trip_id: str, video_t: float, track_id: str = "gnss:bestnav") -> dict:
    v = get_video(trip_id)
    if not v:
        raise ValueError("Braucienam nav piesaistīts video.")
    t = v["start_utc"] + float(video_t)
    return {"video_t": float(video_t), "utc": store.iso(t), "track": track_id,
            "position": tr.position_at(_trip_track(trip_id, track_id), t)}


def video_geojson(trip_id: str, track_ids: list[str]) -> dict:
    v = get_video(trip_id)
    if not v:
        raise ValueError("Braucienam nav piesaistīts video.")
    feats = [tr.to_geojson(_trip_track(trip_id, i), video_start=v["start_utc"]) for i in track_ids]
    return {"type": "FeatureCollection", "features": feats, "video": v}


# ---------------------------------------------------------------- video visam ierakstam (bez brauciena)
def _links_path(rec: str) -> Path:
    from .paths import session_dir
    return session_dir(rec) / "video" / "links.json"


def rec_video_links(rec: str) -> dict:
    p = _links_path(rec)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def default_start(rec: str) -> float | None:
    """Ieraksta pirmā GNSS laika zīmogs: sākuma pieņēmums, kamēr nobīde nav precizēta."""
    try:
        from . import splitter
        rng = splitter.get_index(rec).time_range()
        return rng[0] if rng else None
    except Exception:
        return None


def set_rec_video(rec: str, file: str, start_utc=None, video_t: float | None = None, utc=None,
                  lat: float | None = None, lon: float | None = None, shift_s: float | None = None,
                  track: str = "gnss:bestnav") -> dict:
    from . import workspace
    from .paths import session_dir
    sdir = session_dir(rec)
    name = workspace.clean_name(file)
    if not (sdir / "video" / name).is_file():
        raise ValueError(f"Video fails nav atrasts: {name}")
    links = rec_video_links(rec)
    cur = dict(links.get(name) or {})
    if "start_utc" not in cur:
        d = default_start(rec)
        if d is None:
            raise ValueError("Nevar noteikt ieraksta sākuma laiku.")
        cur["start_utc"] = d
    if start_utc is not None:
        cur["start_utc"] = store.parse_utc(start_utc)
    elif video_t is not None and utc is not None:
        cur["start_utc"] = store.parse_utc(utc) - float(video_t)
    elif video_t is not None and lat is not None and lon is not None:
        t = tr.load_track(sdir, track)
        x, y = tr.xy(t.lat, t.lon, lat, lon)
        cur["start_utc"] = float(t.t[int(np.argmin(np.hypot(x, y)))]) - float(video_t)
    elif shift_s is not None:
        cur["start_utc"] += float(shift_s)
    cur["start_utc_iso"] = store.iso(cur["start_utc"])
    cur["updated"] = store.now()
    links[name] = cur
    p = _links_path(rec)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(links, indent=2), encoding="utf-8")
    tmp.replace(p)
    return cur
