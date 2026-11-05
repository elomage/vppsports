#!/usr/bin/env python3
"""Fuse one GNSS recording with one XDK log in every combination of GNSS curve x fusion method, and compare.

Usage (an XDK log attached to the recording with attach_xdk.py is used by default):
  python scripts/fusion_compare.py 20261103_231217Z_LOG00005

Or with SD card folders gnss/ and xdk/ side by side, log number 5:
  python scripts/fusion_compare.py 20261103_231217Z_LOG00005 \\
      --data-dir ../../../our_data/sinhron_test_2026_11_02 --log 5

or with explicit files:
  python scripts/fusion_compare.py <recording> --xdk LOG_005.CSV --gnss-sync SYNC00005.CSV --xdk-sync SYNC_005.CSV

The XDK clock is aligned with the SYNC button presses (--sync button, the default when both SYNC files are
given) or with the yaw-rate correlation (--sync yaw). Both are always computed and compared in the report.

Outputs go to out/<recording>/imu/compare_<xdk log>/:
  <curve>__<method>.csv   one fused trajectory per combination
  summary.csv / .json     metrics of every combination
  report.html             side-by-side plot of all trajectories and the metrics table
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import imu_links
from fusion_methods import METHODS, FusedTrack, run_method
from gnss_curves import CURVE_ORDER, DERIVED_SPEED_SIGMA_MPS, available_curves, derived_velocity, has_doppler, is_stationary, load_curve, speed_series
from gnss_xdk_fusion import XdkFusionConfig
from session_paths import find_original_bin, output_subdir, resolve_session_dir
from sync_button import ButtonSync, compute_button_sync, sync_files_for
from xdk_imu import find_offset, load_xdk

EARTH_R = 6378137.0
_CACHE: dict[Any, Any] = {}


# ---------------------------------------------------------------- geometry / metrics
def enu_to_llh(east: np.ndarray, north: np.ndarray, ref: tuple[float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    lat = ref[0] + np.degrees(north / EARTH_R)
    lon = ref[1] + np.degrees(east / (EARTH_R * max(0.1, math.cos(math.radians(ref[0])))))
    return lat, lon


def to_common(lat: np.ndarray, lon: np.ndarray, origin: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    north = np.radians(np.asarray(lat) - origin[0]) * EARTH_R
    east = np.radians(np.asarray(lon) - origin[1]) * EARTH_R * max(0.1, math.cos(math.radians(origin[0])))
    return east, north


def track_common_xy(track: FusedTrack, origin: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    lat, lon = enu_to_llh(track.east, track.north, track.ref)
    return to_common(lat, lon, origin)


def path_length(t: np.ndarray, e: np.ndarray, n: np.ndarray, rate_hz: float = 2.0) -> float:
    grid = np.arange(t[0], t[-1], 1.0 / rate_hz)
    return float(np.sum(np.hypot(np.diff(np.interp(grid, t, e)), np.diff(np.interp(grid, t, n)))))


def acceleration_roughness(t: np.ndarray, e: np.ndarray, n: np.ndarray, rate_hz: float = 10.0) -> float:
    """RMS of the second difference of the position (m/s^2): a smooth trajectory has little of it."""
    grid = np.arange(t[0], t[-1], 1.0 / rate_hz)
    ee, nn = np.interp(grid, t, e), np.interp(grid, t, n)
    a = np.hypot(np.diff(ee, 2), np.diff(nn, 2)) * rate_hz**2
    return float(np.sqrt(np.mean(a**2))) if len(a) else math.nan


def rms_distance(track_t, track_e, track_n, ref_t, ref_e, ref_n) -> float:
    mask = (ref_t >= track_t[0]) & (ref_t <= track_t[-1])
    if mask.sum() < 3:
        return math.nan
    d = np.hypot(np.interp(ref_t[mask], track_t, track_e) - ref_e[mask], np.interp(ref_t[mask], track_t, track_n) - ref_n[mask])
    return float(np.sqrt(np.mean(d**2)))


def track_metrics(track: FusedTrack, curves: dict[str, dict[str, Any]], origin: tuple[float, float], static: bool) -> dict[str, Any]:
    t = track.times
    e, n = track_common_xy(track, origin)
    info = track.info
    epochs = max(1, int(info.get("gnss_epochs", 0) or 0))
    m: dict[str, Any] = {
        "rows": len(t),
        "duration_s": float(t[-1] - t[0]),
        "path_m": path_length(t, e, n),
        "accel_roughness_mps2": acceleration_roughness(t, e, n),
        "gnss_epochs": int(info.get("gnss_epochs", 0) or 0),
        "gnss_used_pct": 100.0 * float(info.get("gnss_used", 0) or 0) / epochs,
        "gnss_rejected": int(info.get("gnss_rejected", 0) or 0),
        "nhc_active": info.get("nhc_active"),
        "zupt_updates": info.get("zupt_updates"),
        "forward_axis_r2": info.get("forward_axis_r2"),
        "imu_used": info.get("imu_used", info.get("uses_imu")),
    }
    if static:
        cx, cy = float(np.median(e)), float(np.median(n))
        d = np.hypot(e - cx, n - cy)
        m["spread_rms_m"] = float(np.sqrt(np.mean(d**2)))
        m["spread_max_m"] = float(d.max())
        m["vel_rms_mps"] = float(np.sqrt(np.mean(track.ve**2 + track.vn**2)))
        k = max(3, len(t) // 10)
        m["drift_m"] = float(math.hypot(e[-k:].mean() - e[:k].mean(), n[-k:].mean() - n[:k].mean()))
    for name, curve in curves.items():
        m[f"vs_{name}_rms_m"] = rms_distance(t, e, n, curve["t"], curve["e"], curve["n"])
        if curve["speed"] is not None:
            mask = (curve["t"] >= t[0]) & (curve["t"] <= t[-1])
            if mask.sum() >= 3:
                speed = np.hypot(np.interp(curve["t"][mask], t, track.ve), np.interp(curve["t"][mask], t, track.vn))
                m[f"speed_vs_{name}_doppler_rms_mps"] = float(np.sqrt(np.mean((speed - curve["speed"][mask]) ** 2)))
    return m


# ---------------------------------------------------------------- outage windows
def choose_outages(points, offset_s: float, xdk_t: np.ndarray, count: int, length_s: float, min_speed: float = 3.0) -> list[tuple[float, float]]:
    """Windows (seconds after the first GNSS point) of steady driving to withhold GNSS from."""
    t = np.array([(p.time - points[0].time).total_seconds() for p in points])
    speed = speed_series(points)
    lo = max(t[0], offset_s + float(xdk_t[0])) + 20.0
    hi = min(t[-1], offset_s + float(xdk_t[-1])) - 20.0 - length_s
    starts = []
    for s in np.arange(lo, hi, 1.0):
        inside = (t >= s) & (t <= s + length_s)
        if inside.sum() >= 3 and np.all(speed[inside] >= min_speed):
            starts.append(float(s))
    if not starts:
        return []
    picks: list[float] = []
    for q in np.linspace(0.15, 0.85, count):
        s = starts[min(len(starts) - 1, int(q * len(starts)))]
        if all(abs(s - other) >= length_s + 20.0 for other in picks):
            picks.append(s)
    return [(s, s + length_s) for s in sorted(picks)]


# ---------------------------------------------------------------- worker
def _cached(key, factory):
    if key not in _CACHE:
        _CACHE[key] = factory()
    return _CACHE[key]


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    try:
        session = Path(job["session"])
        points = _cached(("curve", job["session"], job["curve"]), lambda: load_curve(session, job["curve"]))
        xdk = _cached(("xdk", job["xdk"]), lambda: load_xdk(Path(job["xdk"])))
        config = dict(job["config"])
        if derived_velocity(points):  # the velocity was derived from positions: far less precise than a Doppler one
            config.setdefault("gnss_speed_sigma_mps", DERIVED_SPEED_SIGMA_MPS)
        base = XdkFusionConfig.load(None, config)
        offset = (job["clock0_utc"] - points[0].time.timestamp()) if job["clock0_utc"] is not None else job["offset_s"]
        track = run_method(METHODS[job["method"]], points, xdk, job["curve"], base, offset, [tuple(o) for o in job["outages"]])
        return {"job": job, "track": track, "offset_s": offset}
    except (Exception, SystemExit) as exc:  # one failing combination must not stop the others
        return {"job": job, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------- output
def write_track_csv(path: Path, track: FusedTrack) -> None:
    lat, lon = enu_to_llh(track.east, track.north, track.ref)
    fields = ["time", "lat", "lon", "height_m", "east_m", "north_m", "up_m", "ve_mps", "vn_mps", "vu_mps",
              "heading_deg", "pitch_deg", "roll_deg", "sigma_e_m", "sigma_n_m", "gnss_status", "zupt"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for i in range(len(track.times)):
            w.writerow([
                datetime.fromtimestamp(track.times[i], timezone.utc).isoformat(),
                f"{lat[i]:.10f}", f"{lon[i]:.10f}", f"{track.ref[2] + track.up[i]:.3f}",
                f"{track.east[i]:.3f}", f"{track.north[i]:.3f}", f"{track.up[i]:.3f}",
                f"{track.ve[i]:.4f}", f"{track.vn[i]:.4f}", f"{track.vu[i]:.4f}",
                "" if track.heading_deg is None else f"{track.heading_deg[i]:.2f}",
                "" if track.pitch_deg is None else f"{track.pitch_deg[i]:.2f}",
                "" if track.roll_deg is None else f"{track.roll_deg[i]:.2f}",
                f"{track.sigma_e[i]:.4f}", f"{track.sigma_n[i]:.4f}",
                track.gnss_status[i], "1" if track.zupt[i] else "0",
            ])


def write_summary(out_dir: Path, rows: list[dict[str, Any]]) -> None:
    (out_dir / "summary.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    keys: list[str] = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()})



def method_settings(method: str) -> list[str]:
    """The settings that make a method differ from the defaults, in the form the runs table shows ('key=value')."""
    spec = METHODS[method]
    items = [f"{k}={json.dumps(v)}" for k, v in spec.overrides.items()]
    items += [f"{k}\u00d7{factor:g}" for k, factor in spec.scale.items()]
    if spec.smooth:
        items.append("smooth=true")
    if spec.legacy:
        items.append("filter=accelerometer-only 2-D")
    if not spec.use_imu:
        items.append("imu=off")
    return items


def register_runs(
    session_dir: Path,
    xdk_path: Path,
    tracks: dict[tuple[str, str], FusedTrack],
    outage_info: dict[tuple[str, str], dict[str, Any]],
    offsets: dict[str, float],
    stamp: str,
) -> int:
    """Store every curve x method result as an ordinary fusion run (the files and DB rows the GUI's runs list reads),
    so they can be compared on the normal map. Runs of an earlier fusion_compare of the same XDK log are replaced."""
    import fusion_db
    import fusion_runs

    imu_dir = output_subdir(session_dir, "imu")
    marker = f"fusion_compare:{xdk_path.name}"
    for old in fusion_db.list_runs(session_dir.name):
        if marker in (old.get("notes") or ""):
            fusion_runs.delete_run_files(imu_dir, old)
            fusion_db.delete_run(old["id"])
    count = 0
    for (curve, method), track in tracks.items():
        stem = f"kalman_{curve.replace('_ppk', '')}_{xdk_path.stem}_{stamp}_{method}"
        write_track_csv(imu_dir / f"{stem}.csv", track)
        epoch0 = float(track.info.get("gnss_log_epoch0_utc", track.times[0]))
        with (imu_dir / f"fusion_gnss_{stem}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time", "status", "innovation_sigma", "sigma_m", "east_m", "north_m"])
            for e in track.gnss_log:
                w.writerow([
                    datetime.fromtimestamp(epoch0 + float(e["time_s"]), timezone.utc).isoformat(), e["status"],
                    f"{float(e['innovation_sigma']):.2f}", f"{float(e['sigma_m']):.3f}", f"{float(e['east_m']):.3f}", f"{float(e['north_m']):.3f}",
                ])
        info = dict(track.info)
        oi = outage_info.get((curve, method)) or {}
        for key in ("outage_rmse_m", "outage_max_m", "outage_points", "outage_smoothed_rmse_m", "outage_smoothed_max_m", "outage_ref_sigma_m"):
            if key in oi:
                info[key] = oi[key]
        lines = [f"recording={session_dir}", f"xdk_csv={xdk_path}", f"gnss_source={curve}", f"fusion_method={method}",
                 *[f"fusion_{k}={v}" for k, v in info.items() if k != "gnss_log_epoch0_utc"]]
        (imu_dir / f"{stem}_report.txt").write_text("\n".join(lines), encoding="utf-8")
        fusion_runs.store_run(
            imu_dir, session_dir.name, curve, xdk_path, {"kalman": f"{stem}.csv"},
            {
                "run_name": f"{curve} \u00b7 {METHODS[method].label}",
                "run_notes": f"{marker}; {METHODS[method].description}",
                "fusion_set": method_settings(method),
                "offset_s": offsets.get(curve),
                "gnss_outage": [],
            },
        )
        count += 1
    return count


def print_table(rows: list[dict[str, Any]], static: bool) -> None:
    if static:
        cols = [("spread_rms_m", "spread rms m"), ("spread_max_m", "max m"), ("vel_rms_mps", "vel rms m/s"), ("path_m", "path m")]
    else:
        cols = [("outage_rmse_m", "outage rmse m"), ("outage_smoothed_rmse_m", "smoothed"), ("accel_roughness_mps2", "rough m/s2"), ("path_m", "path m"), ("gnss_used_pct", "gnss used %")]
    print(f"{'curve':12} {'method':16}" + "".join(f"{label:>15}" for _, label in cols))
    for row in rows:
        cells = []
        for key, _ in cols:
            v = row.get(key)
            cells.append(f"{v:15.3f}" if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)) else f"{'-':>15}")
        print(f"{row['curve']:12} {row['method']:16}" + "".join(cells))


def parse_set(items: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"--fusion-set needs KEY=VALUE, got {item!r}")
        try:
            out[key.strip()] = json.loads(value)
        except json.JSONDecodeError:
            out[key.strip()] = value
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Fuse GNSS curves with an XDK log in every method and compare.")
    parser.add_argument("recording", help="out/ recording folder (name or path)")
    parser.add_argument("--data-dir", type=Path, help="Folder with gnss/ and xdk/ SD card copies; with --log gives all files")
    parser.add_argument("--log", type=int, help="Log number in --data-dir")
    parser.add_argument("--xdk", type=Path, help="XDK CSV log")
    parser.add_argument("--gnss-sync", type=Path, help="GNSS SYNCnnnnn.CSV")
    parser.add_argument("--xdk-sync", type=Path, help="XDK SYNC_nnn.CSV")
    parser.add_argument("--curves", default="all", help=f"Comma list of {', '.join(CURVE_ORDER)} or all (those the recording has)")
    parser.add_argument("--methods", default="all", help=f"Comma list of {', '.join(METHODS)} or all")
    parser.add_argument("--sync", choices=["auto", "button", "yaw"], default="auto", help="XDK clock alignment (auto: button when both SYNC files are given, else yaw)")
    parser.add_argument("--time-offset-s", type=float, help="Manual: seconds after the first point of the first curve at which the XDK clock reads 0")
    parser.add_argument("--static", choices=["auto", "yes", "no"], default="auto", help="Is the XDK stationary? auto: from the receiver Doppler speed")
    parser.add_argument("--outage-test", action=argparse.BooleanOptionalAction, default=None, help="Withhold GNSS in driving windows and measure the error (default: on when moving)")
    parser.add_argument("--outage-count", type=int, default=3)
    parser.add_argument("--outage-length-s", type=float, default=10.0)
    parser.add_argument("--fusion-set", action="append", default=[], metavar="KEY=VALUE", help="Override an XdkFusionConfig field for every method")
    parser.add_argument("--jobs", type=int, default=4, help="Parallel worker processes")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--register", action=argparse.BooleanOptionalAction, default=True,
                        help="Also store every curve x method as an ordinary fusion run, so they show up in the GUI's runs list and map (default on)")
    args = parser.parse_args()

    session_dir = resolve_session_dir(args.recording)
    xdk_path, gnss_sync, xdk_sync = args.xdk, args.gnss_sync, args.xdk_sync
    if args.data_dir:
        if args.log is None:
            parser.error("--data-dir needs --log")
        _, g_sync, x_log, x_sync = sync_files_for(args.data_dir / "gnss", args.data_dir / "xdk", args.log)
        xdk_path, gnss_sync, xdk_sync = xdk_path or x_log, gnss_sync or g_sync, xdk_sync or x_sync
    link = imu_links.resolve_xdk(session_dir, Path(xdk_path).name if xdk_path else None)
    if xdk_path and not Path(xdk_path).is_file() and link is not None:
        xdk_path = link.xdk  # a bare name of a log linked to this recording
    if not xdk_path:
        if link is None:
            parser.error("no XDK log: give --xdk, --data-dir with --log, or attach one with scripts/attach_xdk.py")
        xdk_path = link.xdk
        print(f"Using the {'default ' if link.is_default else ''}XDK log linked to this recording: {link.name}")
    if link is not None and Path(xdk_path).resolve() == link.xdk.resolve():
        gnss_sync, xdk_sync = gnss_sync or link.gnss_sync, xdk_sync or link.xdk_sync  # the SYNC files stored with the link
    xdk_path = Path(xdk_path).resolve()
    out_dir = args.out_dir or output_subdir(session_dir, "imu") / f"compare_{xdk_path.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- inputs
    paths = available_curves(session_dir)
    wanted = list(paths) if args.curves == "all" else [c.strip() for c in args.curves.split(",")]
    for c in wanted:
        if c not in paths:
            raise SystemExit(f"GNSS curve {c!r} is not available for {session_dir.name}; available: {', '.join(paths)}")
    method_keys = list(METHODS) if args.methods == "all" else [m.strip() for m in args.methods.split(",")]
    for m in method_keys:
        if m not in METHODS:
            raise SystemExit(f"Unknown method {m!r}; known: {', '.join(METHODS)}")
    print(f"Recording {session_dir.name}; curves: {', '.join(wanted)}; XDK {xdk_path.name}")
    curve_points = {c: load_curve(session_dir, c) for c in wanted}
    xdk = load_xdk(xdk_path)
    first_curve = wanted[0]
    origin = (curve_points[first_curve][0].lat, curve_points[first_curve][0].lon)

    # ---- is it standing still?
    doppler_curves = [c for c in wanted if has_doppler(curve_points[c])]
    if args.static == "auto":
        static = is_stationary(curve_points[doppler_curves[0] if doppler_curves else first_curve])
    else:
        static = args.static == "yes"
    print(f"Motion: {'STATIONARY' if static else 'moving'}")

    # ---- time alignment
    clock0: dict[str, float | None] = {"button": None, "yaw": None}
    button: ButtonSync | None = None
    if gnss_sync and xdk_sync and Path(gnss_sync).is_file() and Path(xdk_sync).is_file():
        button = compute_button_sync(Path(gnss_sync), Path(xdk_sync), find_original_bin(session_dir))
        clock0["button"] = button.xdk_clock0_utc
        print(f"SYNC button: XDK clock 0 = {button.xdk_clock0.isoformat()} ({len(button.pairs)} pairs, spread {button.spread_ms:.0f} ms, {button.confidence})")
    yaw_info = None
    if not static:
        ref_points = curve_points[doppler_curves[0] if doppler_curves else first_curve]
        try:
            found = find_offset(xdk, ref_points)
            clock0["yaw"] = ref_points[0].time.timestamp() + found.offset_s
            yaw_info = {"correlation": found.correlation, "second": found.second_correlation, "confidence": found.confidence}
            print(f"Yaw-rate: XDK clock 0 = {datetime.fromtimestamp(clock0['yaw'], timezone.utc).isoformat()} (corr {found.correlation:.2f}, {found.confidence})")
        except ValueError as exc:
            print(f"Yaw-rate alignment not possible: {exc}")
    mode = args.sync
    if args.time_offset_s is not None:
        chosen = curve_points[first_curve][0].time.timestamp() + args.time_offset_s
        mode = "manual"
    elif mode == "auto":
        mode = "button" if clock0["button"] is not None else "yaw"
    if mode != "manual":
        chosen = clock0[mode]
        if chosen is None:
            raise SystemExit(f"--sync {mode} is not available (button needs both SYNC files; yaw needs motion).")
    sync_diff_ms = None if clock0["button"] is None or clock0["yaw"] is None else (clock0["button"] - clock0["yaw"]) * 1000.0
    print(f"Using the {mode} alignment" + ("" if sync_diff_ms is None else f"; button vs yaw-rate differ by {sync_diff_ms:+.0f} ms"))

    # ---- jobs
    config = {"assume_stationary": static, **parse_set(args.fusion_set)}
    do_outage = (not static) if args.outage_test is None else args.outage_test
    outages_utc: list[tuple[float, float]] = []
    if do_outage and not static:
        ref_points = curve_points[first_curve]
        rel = choose_outages(ref_points, chosen - ref_points[0].time.timestamp(), xdk.t, args.outage_count, args.outage_length_s)
        outages_utc = [(ref_points[0].time.timestamp() + a, ref_points[0].time.timestamp() + b) for a, b in rel]
        print("GNSS outage windows: " + (", ".join(f"{datetime.fromtimestamp(a, timezone.utc):%H:%M:%S}-{datetime.fromtimestamp(b, timezone.utc):%H:%M:%S}" for a, b in outages_utc) or "none found"))
    jobs = []
    for curve in wanted:
        t0 = curve_points[curve][0].time.timestamp()
        for method in method_keys:
            base_job = {"session": str(session_dir), "curve": curve, "method": method, "xdk": str(xdk_path),
                        "clock0_utc": chosen, "offset_s": None, "config": config}
            jobs.append({**base_job, "outages": [], "kind": "full"})
            if outages_utc:
                jobs.append({**base_job, "outages": [(a - t0, b - t0) for a, b in outages_utc], "kind": "outage"})
    print(f"{len(jobs)} runs ({len(wanted)} curves x {len(method_keys)} methods{' x 2 with GNSS outages' if outages_utc else ''}), {args.jobs} workers")

    results: list[dict[str, Any]] = []
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            for i, res in enumerate(pool.map(run_job, jobs), 1):
                results.append(res)
                print(f"  [{i}/{len(jobs)}] {res['job']['curve']} / {res['job']['method']} / {res['job']['kind']}" + (f"  FAILED {res['error']}" if "error" in res else ""), flush=True)
    else:
        for i, job in enumerate(jobs, 1):
            res = run_job(job)
            results.append(res)
            print(f"  [{i}/{len(jobs)}] {job['curve']} / {job['method']} / {job['kind']}" + (f"  FAILED {res['error']}" if "error" in res else ""), flush=True)

    # ---- metrics
    curve_data: dict[str, dict[str, Any]] = {}
    for c, pts in curve_points.items():
        lat = np.array([p.lat for p in pts])
        lon = np.array([p.lon for p in pts])
        ce, cn = to_common(lat, lon, origin)
        curve_data[c] = {
            "t": np.array([p.time.timestamp() for p in pts]), "e": ce, "n": cn,
            "speed": speed_series(pts) if has_doppler(pts) else None,
        }
    outage_info: dict[tuple[str, str], dict[str, Any]] = {}
    full_tracks: dict[tuple[str, str], FusedTrack] = {}
    curve_offsets: dict[str, float] = {}
    for res in results:
        if "error" not in res and res["job"]["kind"] == "outage":
            outage_info[(res["job"]["curve"], res["job"]["method"])] = res["track"].info
    rows: list[dict[str, Any]] = []
    plot_tracks: dict[str, dict[str, Any]] = {}
    for res in results:
        job = res["job"]
        if job["kind"] != "full":
            continue
        if "error" in res:
            rows.append({"curve": job["curve"], "method": job["method"], "error": res["error"]})
            continue
        track: FusedTrack = res["track"]
        full_tracks[(job["curve"], job["method"])] = track
        curve_offsets[job["curve"]] = res["offset_s"]
        write_track_csv(out_dir / f"{job['curve']}__{job['method']}.csv", track)
        row: dict[str, Any] = {"curve": job["curve"], "method": job["method"], "label": METHODS[job["method"]].label}
        row.update(track_metrics(track, curve_data, origin, static))
        oi = outage_info.get((job["curve"], job["method"]))
        if oi:
            for key in ("outage_rmse_m", "outage_max_m", "outage_points", "outage_smoothed_rmse_m", "outage_smoothed_max_m", "outage_ref_sigma_m"):
                if key in oi:
                    row[key] = oi[key]
        rows.append(row)
        e, n = track_common_xy(track, origin)
        step = max(1, int(round(len(e) / max(1.0, (track.times[-1] - track.times[0]) * 5.0))))
        plot_tracks[f"{job['curve']}|{job['method']}"] = {"e": np.round(e[::step], 2).tolist(), "n": np.round(n[::step], 2).tolist()}

    write_summary(out_dir, rows)
    meta = {
        "recording": session_dir.name, "xdk": xdk_path.name, "static": static, "sync_mode": mode,
        "sync_diff_ms": sync_diff_ms, "yaw": yaw_info,
        "clock0_utc": datetime.fromtimestamp(chosen, timezone.utc).isoformat(),
        "button": None if button is None else asdict(button),
        "outages": [[datetime.fromtimestamp(a, timezone.utc).isoformat(), datetime.fromtimestamp(b, timezone.utc).isoformat()] for a, b in outages_utc],
        "config": config,
        "methods": {k: {"label": METHODS[k].label, "description": METHODS[k].description} for k in method_keys},
        "curves": wanted,
    }
    gnss_plot = {c: {"e": np.round(d["e"], 2).tolist(), "n": np.round(d["n"], 2).tolist()} for c, d in curve_data.items()}
    (out_dir / "run_config.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    from fusion_report import build_report
    build_report(out_dir / "report.html", meta, rows, plot_tracks, gnss_plot)
    print()
    print_table([r for r in rows if "error" not in r], static)
    failed = [r for r in rows if "error" in r]
    for r in failed:
        print(f"FAILED {r['curve']} / {r['method']}: {r['error']}")
    print(f"\nWrote {len(rows) - len(failed)} trajectories, summary.csv and report.html to {out_dir}")
    if args.register and full_tracks:
        registered = register_runs(session_dir, xdk_path, full_tracks, outage_info, curve_offsets, datetime.now().strftime("%Y%m%d_%H%M%S"))
        print(f"Registered {registered} runs: they are in the runs list and on the map of the GUI (step 6)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
