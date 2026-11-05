"""Vienots trajektoriju modelis: GNSS avoti (bestnav/PPK/DGPS/observation) un Kalman rezultāti."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .paths import SCRIPTS_DIR  # noqa: F401  (sys.path)

COLORS = {"bestnav": "#2563eb", "fixed_ppk": "#c026d3", "float_ppk": "#f59e0b", "dgps": "#7c3aed", "observation": "#16a34a"}
METHOD_COLORS = ["#dc2626", "#0891b2", "#db2777", "#65a30d", "#7c3aed", "#ea580c", "#0d9488", "#be185d", "#4b5563"]
R_EARTH = 6378137.0


@dataclass
class Track:
    id: str
    label: str
    t: np.ndarray  # epoch s (UTC)
    lat: np.ndarray
    lon: np.ndarray
    h: np.ndarray
    speed: np.ndarray | None = None
    color: str = "#2563eb"

    def __len__(self) -> int:
        return len(self.t)


def _gnss_curves():
    import gnss_curves
    return gnss_curves


def available_gnss(session: Path) -> list[str]:
    return list(_gnss_curves().available_curves(Path(session)))


def fusion_dir(session: Path) -> Path:
    return Path(session) / "fusion"


SOURCE_LABELS = {"bestnav": "Receiver", "observation": "Observation", "fixed_ppk": "PPK fixed", "float_ppk": "PPK float", "dgps": "DGPS"}
SOURCE_GROUP = {"bestnav": "receiver", "observation": "observation", "fixed_ppk": "ppk", "float_ppk": "ppk", "dgps": "ppk"}
SOURCE_HUE = {"bestnav": 215, "observation": 140, "fixed_ppk": 290, "float_ppk": 30, "dgps": 265}
IMU_TRACKS = {"imu:raw": ("imu_raw.csv", "IMU raw (tīrā integrēšana)", "#0e7490"),
              "imu:constrained": ("imu_constrained.csv", "IMU + ZUPT/NHC (bez GNSS)", "#0891b2")}


def _hsl(h: float, s: float, l: float) -> str:
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _method_label(key: str) -> str:
    try:
        from fusion_methods import METHODS
        return METHODS[key].label
    except Exception:
        return key


def fusion_files(session: Path) -> list[tuple[str, Path]]:
    """(id bez 'fusion:', fails): braucienu fusion/ un vecie ierakstu imu/compare_*/ rezultāti."""
    session = Path(session)
    out: list[tuple[str, Path]] = []
    fd = fusion_dir(session)
    if fd.is_dir():
        out += [(f"fusion/{p.stem}", p) for p in sorted(fd.glob("*__*.csv"))]
    imu = session / "imu"
    if imu.is_dir():
        for d in sorted(imu.glob("compare_*")):
            out += [(f"imu/{d.name}/{p.stem}", p) for p in sorted(d.glob("*__*.csv"))]
    return out


def catalog(session: Path) -> list[dict]:
    """Visas pieejamās trajektorijas sesijai, ar grupu (receiver/observation/ppk/kalman/imu) un krāsu."""
    session = Path(session)
    items = [{"id": f"gnss:{s}", "kind": "gnss", "group": SOURCE_GROUP.get(s, "other"), "source": s,
              "source_label": SOURCE_LABELS.get(s, s), "label": SOURCE_LABELS.get(s, s),
              "color": COLORS.get(s, "#000")} for s in available_gnss(session)]
    method_order = []
    try:
        from fusion_methods import METHODS
        method_order = list(METHODS)
    except Exception:
        pass
    for rel, p in fusion_files(session):
        src, _, method = p.stem.partition("__")
        mi = method_order.index(method) if method in method_order else 0
        hue = SOURCE_HUE.get(src, 0)
        items.append({"id": f"fusion:{rel}", "kind": "fusion", "group": "kalman", "source": src,
                      "source_label": SOURCE_LABELS.get(src, src), "method": method, "method_label": _method_label(method),
                      "label": f"{SOURCE_LABELS.get(src, src)} + {_method_label(method)}",
                      "origin": "compare" if rel.startswith("imu/") else "trip",
                      "color": _hsl(hue, 0.7, 0.28 + 0.045 * mi)})
    for tid, (fname, label, color) in IMU_TRACKS.items():
        if (fusion_dir(session) / fname).is_file():
            items.append({"id": tid, "kind": "imu", "group": "imu", "source": "imu", "source_label": "IMU", "label": label, "color": color})
    return items


def _parse_iso(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_track(session: Path, track_id: str) -> Track:
    kind, _, name = track_id.partition(":")
    if kind == "gnss":
        try:
            pts = _gnss_curves().load_curve(Path(session), name)
        except SystemExit as exc:
            raise ValueError(str(exc)) from None
        from gnss_curves import has_doppler, speed_series
        sp = speed_series(pts) if has_doppler(pts) else np.array([p.speed_mps for p in pts])
        return Track(track_id, name, np.array([p.time.timestamp() for p in pts]), np.array([p.lat for p in pts]),
                     np.array([p.lon for p in pts]), np.array([p.height for p in pts]), sp, COLORS.get(name, "#000"))
    if kind in ("fusion", "imu"):
        session = Path(session)
        if kind == "imu":
            if track_id not in IMU_TRACKS:
                raise ValueError(f"Nezināma IMU trajektorija: {track_id}")
            path = fusion_dir(session) / IMU_TRACKS[track_id][0]
            label = IMU_TRACKS[track_id][1]
            color = IMU_TRACKS[track_id][2]
        else:
            rel = name if "/" in name else f"fusion/{name}"  # vecais id bez mapes
            path = (session / f"{rel}.csv").resolve()
            if ".." in rel or "\\" in rel or session.resolve() not in path.parents:
                raise ValueError("Nederīgs trajektorijas id")
            label = Path(rel).stem.replace("__", " + ")
            color = "#dc2626"
        if not path.is_file():
            raise ValueError(f"Nav rezultāta: {track_id}")
        t, lat, lon, h, ve, vn = [], [], [], [], [], []
        with path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                t.append(_parse_iso(r["time"])); lat.append(float(r["lat"])); lon.append(float(r["lon"]))
                h.append(float(r["height_m"])); ve.append(float(r["ve_mps"])); vn.append(float(r["vn_mps"]))
        ve, vn = np.array(ve), np.array(vn)
        return Track(track_id, label, np.array(t), np.array(lat), np.array(lon), np.array(h), np.hypot(ve, vn), color)
    raise ValueError(f"Nezināms trajektorijas veids: {track_id}")


def to_geojson(tr: Track, max_vertices: int = 6000, video_start: float | None = None) -> dict:
    n = len(tr)
    idx = np.arange(n) if n <= max_vertices else np.unique(np.linspace(0, n - 1, max_vertices).astype(int))

    def iso(e):
        return datetime.fromtimestamp(float(e), timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    props = {"kind": "path", "id": tr.id, "label": tr.label, "color": tr.color, "points": int(len(idx)),
             "times": [iso(tr.t[i]) for i in idx]}
    if tr.speed is not None:
        props["speed_mps"] = [round(float(tr.speed[i]), 3) for i in idx]
    if video_start is not None:
        props["video_times"] = [round(float(tr.t[i] - video_start), 3) for i in idx]
    return {"type": "Feature", "properties": props,
            "geometry": {"type": "LineString",
                         "coordinates": [[float(tr.lon[i]), float(tr.lat[i]), float(tr.h[i])] for i in idx]}}


def position_at(tr: Track, t: float) -> dict | None:
    if not len(tr) or t < tr.t[0] or t > tr.t[-1]:
        return None
    out = {"t": t, "lat": float(np.interp(t, tr.t, tr.lat)), "lon": float(np.interp(t, tr.t, tr.lon)),
           "height_m": float(np.interp(t, tr.t, tr.h))}
    if tr.speed is not None:
        out["speed_mps"] = float(np.interp(t, tr.t, tr.speed))
    return out


def xy(lat, lon, lat0, lon0):
    return ((np.asarray(lon) - lon0) * math.cos(math.radians(lat0)) * math.pi / 180 * R_EARTH,
            (np.asarray(lat) - lat0) * math.pi / 180 * R_EARTH)


def compare(tracks: list[Track]) -> dict:
    """Pirmā trajektorija = atskaite; pārējām horizontālais attālums līdz tai kopējā laika posmā."""
    if len(tracks) < 2:
        raise ValueError("Salīdzināšanai vajag vismaz 2 trajektorijas.")
    ref = tracks[0]
    lat0, lon0 = float(ref.lat[0]), float(ref.lon[0])
    rx, ry = xy(ref.lat, ref.lon, lat0, lon0)
    rows = []
    for tr in tracks[1:]:
        m = (ref.t >= tr.t[0]) & (ref.t <= tr.t[-1])
        if m.sum() < 2:
            rows.append({"id": tr.id, "error": "nepārklājas ar atskaiti"})
            continue
        x, y = xy(np.interp(ref.t[m], tr.t, tr.lat), np.interp(ref.t[m], tr.t, tr.lon), lat0, lon0)
        d = np.hypot(x - rx[m], y - ry[m])
        rows.append({"id": tr.id, "label": tr.label, "points": int(m.sum()), "rms_m": float(np.sqrt(np.mean(d ** 2))),
                     "mean_m": float(d.mean()), "p95_m": float(np.percentile(d, 95)), "max_m": float(d.max())})
    return {"reference": ref.id, "rows": rows}
