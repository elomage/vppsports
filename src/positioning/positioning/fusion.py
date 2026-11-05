"""GNSS avots × Kalman metode matrica braucienam (izmanto esošo fusion_compare.py)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from . import store, tracks
from .paths import OUT_DIR, PYTHON, script

Log = Callable[[str], None]


def methods() -> list[dict]:
    from fusion_methods import METHODS
    return [{"key": m.key, "label": m.label, "description": m.description, "uses_imu": m.use_imu} for m in METHODS.values()]


def run_matrix(trip_id: str, sources: list[str] | None = None, method_keys: list[str] | None = None,
               jobs: int = 4, static: str = "auto", fusion_set: list[str] | None = None,
               outage_test: bool | None = None, log: Log | None = None) -> dict:
    from fusion_methods import METHODS
    from gnss_curves import CURVE_ORDER, load_curve
    trip = store.get_trip(trip_id)
    sync = trip.get("sync")
    if not sync:
        raise ValueError("Braucienam nav iestatīta IMU sinhronizācija (sync).")
    session = OUT_DIR / trip["session"]
    available = tracks.available_gnss(session)
    wanted = [s for s in CURVE_ORDER if s in available and (not sources or s in sources)]
    bad = [s for s in (sources or []) if s not in available]
    if bad:
        raise ValueError(f"GNSS avoti nav pieejami: {', '.join(bad)} (pieejami: {', '.join(available)})")
    if not wanted:
        raise ValueError("Nav neviena GNSS avota (vispirms apstrādā braucienu: csv/rinex/ppk).")
    mk = method_keys or list(METHODS)
    unknown = [m for m in mk if m not in METHODS]
    if unknown:
        raise ValueError(f"Nezināmas metodes: {', '.join(unknown)}")
    xdk = session / "imu" / sync["xdk"]
    if not xdk.is_file():
        raise ValueError("Brauciena izgrieztais XDK fails nav atrasts; atkārto sync.")
    first = load_curve(session, wanted[0])[0].time.timestamp()
    out_dir = tracks.fusion_dir(session)
    if out_dir.is_dir():  # vecie rezultāti tiek aizstāti
        for p in out_dir.glob("*__*.csv"):
            p.unlink()
    cmd = [PYTHON, script("fusion_compare.py"), str(session), "--xdk", str(xdk), "--curves", ",".join(wanted),
           "--methods", ",".join(mk), "--time-offset-s", repr(sync["xdk_clock0_utc"] - first), "--static", static,
           "--jobs", str(jobs), "--out-dir", str(out_dir), "--no-register"]
    if outage_test is not None:
        cmd.append("--outage-test" if outage_test else "--no-outage-test")
    for item in fusion_set or []:
        cmd += ["--fusion-set", item]
    if log:
        log("$ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if log:
        for line in (r.stdout + r.stderr).splitlines()[-60:]:
            log(line)
    if r.returncode != 0:
        raise ValueError(f"fusion_compare kļūda: {(r.stderr or r.stdout)[-600:]}")
    store.update_trip(trip_id, status={"fusion": store.now()})
    return {"ok": True, "runs": list_runs(trip_id)}


def list_runs(trip_id: str) -> list[dict]:
    session = OUT_DIR / store.get_trip(trip_id)["session"]
    summary = tracks.fusion_dir(session) / "summary.json"
    if not summary.is_file():
        return []
    rows = json.loads(summary.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        r = dict(r)
        r["id"] = f"fusion:{r.get('curve')}__{r.get('method')}"
        r["available"] = (tracks.fusion_dir(session) / f"{r.get('curve')}__{r.get('method')}.csv").is_file()
        out.append(r)
    return out


# ---------------------------------------------------------------- IMU raw pozīcija no XDK
RAW_VARIANTS = {"imu:raw": ("imu_raw.csv", "ekf_free"), "imu:constrained": ("imu_constrained.csv", "ekf_full")}


def imu_raw(session: Path | str, source: str | None = None, log: Log | None = None) -> dict:
    """IMU-only trajektorija no XDK: sākuma stāvoklis (pozīcija, ātrums, virziens) no pirmajām GNSS epohām,
    pēc tam GNSS netiek izmantots. `imu:raw` = tīrā integrēšana, `imu:constrained` = ar ZUPT/NHC ierobežojumiem."""
    import imu_links
    from fusion_compare import write_track_csv
    from fusion_methods import METHODS, run_method
    from gnss_curves import CURVE_ORDER, has_doppler, is_stationary, load_curve
    from gnss_xdk_fusion import XdkFusionConfig
    from xdk_imu import find_offset, load_xdk
    session = Path(session)
    link = imu_links.resolve_xdk(session)
    if link is None:
        raise ValueError("Ierakstam nav piesaistīts XDK žurnāls.")
    avail = tracks.available_gnss(session)
    source = source or next((s for s in CURVE_ORDER if s in avail), None)
    if source not in avail:
        raise ValueError(f"GNSS avots nav pieejams: {source}")
    points = load_curve(session, source)
    xdk = load_xdk(link.xdk)
    sync = link.entry.get("sync") or {}
    clock0 = sync.get("xdk_clock0_utc")
    if clock0 is None:  # nav pogas sinhronizācijas: mēģina pēc kustības
        try:
            clock0 = points[0].time.timestamp() + find_offset(xdk, points).offset_s
        except ValueError as exc:
            raise ValueError(f"Nav XDK sinhronizācijas (poga vai kustība): {exc}") from None
    offset = float(clock0) - points[0].time.timestamp()
    static = is_stationary(points)
    base = XdkFusionConfig.load(None, {"assume_stationary": static})
    start = max(0.0, offset + float(xdk.t[0])) + 3.0  # 3 s sākotnējai izlīdzināšanai, tad tikai IMU
    out_dir = tracks.fusion_dir(session)
    out_dir.mkdir(parents=True, exist_ok=True)
    done = {}
    for tid, (fname, mkey) in RAW_VARIANTS.items():
        if log:
            log(f"IMU raw: {tid} ({mkey}), avots {source}, XDK {link.name}")
        track = run_method(METHODS[mkey], points, xdk, source, base, offset, [(start, 1e9)])
        write_track_csv(out_dir / fname, track)
        done[tid] = {"rows": len(track.times), "file": fname}
    return {"ok": True, "source": source, "xdk": link.name, "variants": done}
