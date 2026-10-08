"""Fusion run bookkeeping: result metrics, trajectories for plotting, and merging DB runs with older files."""

from __future__ import annotations

import bisect
import csv
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import fusion_db

USED_STATUSES = {"used", "downweighted", "reacquired"}


def parse_report(path: Path) -> dict[str, str]:
    report: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep:
                report[key] = value
    return report


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _thin(rows: list, limit: int) -> list:
    if len(rows) <= limit:
        return rows
    step = len(rows) / limit
    return [rows[int(i * step)] for i in range(limit)]


EARTH_RADIUS_M = 6378137.0  # same flat-earth constant as imu_kalman.enu_to_llh


def _origin(row: dict[str, str]) -> list[float] | None:
    """[lat, lon] of the local east/north origin, recovered from one row (inverse of enu_to_llh)."""
    try:
        lat, lon, east, north = (float(row[k]) for k in ("lat", "lon", "east_m", "north_m"))
    except (KeyError, ValueError):
        return None
    lat0 = lat - math.degrees(north / EARTH_RADIUS_M)
    lon0 = lon - math.degrees(east / (EARTH_RADIUS_M * max(0.1, math.cos(math.radians(lat0)))))
    return [round(lat0, 9), round(lon0, 9)]


def gnss_log_path(imu_dir: Path, kalman_name: str) -> Path:
    return imu_dir / f"fusion_gnss_{Path(kalman_name).stem}.csv"


def trajectory(imu_dir: Path, kalman_name: str, fused_limit: int = 4000, gnss_limit: int = 8000) -> dict[str, Any]:
    """Thinned fused path and the per-point GNSS status for plotting (east/north metres)."""
    kalman = imu_dir / Path(kalman_name).name
    if not kalman.is_file():
        raise ValueError("Kalman rezultāta fails nav atrasts.")
    all_rows = _read(kalman)
    fused = _thin(all_rows, fused_limit)
    log = gnss_log_path(imu_dir, kalman.name)
    gnss = _thin(_read(log), gnss_limit) if log.is_file() else []
    return {
        "origin": _origin(all_rows[0]) if all_rows else None,
        "fused": [[float(r["east_m"]), float(r["north_m"]), r.get("gnss_status", "")] for r in fused],
        "gnss": [[float(r["east_m"]), float(r["north_m"]), r["status"], r["time"]] for r in gnss],
    }


def result_metrics(imu_dir: Path, kalman_name: str) -> dict[str, float]:
    """How the fused path relates to the GNSS points it accepted, and its length."""
    kalman = imu_dir / Path(kalman_name).name
    rows = _read(kalman)
    if len(rows) < 2:
        return {}
    times = [datetime.fromisoformat(r["time"]).timestamp() for r in rows]
    east = [float(r["east_m"]) for r in rows]
    north = [float(r["north_m"]) for r in rows]
    metrics: dict[str, float] = {"duration_s": round(times[-1] - times[0], 1)}
    step = max(1, round(len(rows) / max(1.0, times[-1] - times[0])))  # about 1 point per second
    metrics["path_length_m"] = round(sum(
        math.hypot(east[i] - east[i - step], north[i] - north[i - step]) for i in range(step, len(rows), step)
    ), 1)
    log = gnss_log_path(imu_dir, kalman.name)
    if log.is_file():
        distances = []
        for entry in _read(log):
            if entry["status"] not in USED_STATUSES:
                continue
            t = datetime.fromisoformat(entry["time"]).timestamp()
            i = min(len(times) - 1, max(0, bisect.bisect_left(times, t)))
            if i > 0 and abs(times[i - 1] - t) < abs(times[i] - t):
                i -= 1
            distances.append(math.hypot(east[i] - float(entry["east_m"]), north[i] - float(entry["north_m"])))
        if distances:
            distances.sort()
            metrics["gnss_rms_m"] = round(math.sqrt(sum(d * d for d in distances) / len(distances)), 3)
            metrics["gnss_p95_m"] = round(distances[min(len(distances) - 1, int(0.95 * len(distances)))], 3)
    return metrics


def store_run(
    imu_dir: Path,
    recording: str,
    source: str,
    imu_path: Path,
    outputs: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Save one finished run (its report lives next to its output: <kalman stem>_report.txt)."""
    report_name = f"{Path(outputs['kalman']).stem}_report.txt"
    metrics = {**parse_report(imu_dir / report_name), **result_metrics(imu_dir, outputs["kalman"])}
    # What the GUI needs to restore this run later (outage windows in GUI time, offset from the source start).
    metrics["gui_outages"] = payload.get("gui_outages") or []
    metrics["offset_s"] = payload.get("offset_s")
    log = gnss_log_path(imu_dir, outputs["kalman"])
    run = fusion_db.add_run({
        "recording": recording,
        "source": source,
        "imu_path": str(imu_path),
        "imu_name": imu_path.name,
        "name": str(payload.get("run_name") or "").strip(),
        "notes": str(payload.get("run_notes") or "").strip(),
        "imu_start_utc": str(payload.get("imu_start_utc") or ""),
        "profile": str(payload.get("imu_processing_profile") or payload.get("accel_bias_profile") or ""),
        "settings": list(payload.get("fusion_set") or []),
        "outages": list(payload.get("gnss_outage") or []),
        "metrics": metrics,
        "kalman_file": outputs["kalman"],
        "dead_file": outputs.get("dead", ""),
        "corrected_file": outputs.get("corrected", ""),
        "gnss_log_file": log.name if log.is_file() else "",
        "report_file": report_name if (imu_dir / report_name).is_file() else "",
    })
    if not run["name"]:
        run = fusion_db.update_run(run["id"], {"name": f"Aprēķins #{run['id']}"}) or run
    return run


def list_runs(imu_dir: Path, recording: str, legacy_sources: dict[str, str]) -> list[dict[str, Any]]:
    """DB runs of the recording plus older kalman_*.csv files that have no DB row (read-only).

    legacy_sources maps the run label in a file name (fixed, bestnav ...) to a source name.
    """
    runs = [{**run, "uid": f"db:{run['id']}", "legacy": False} for run in fusion_db.list_runs(recording)]
    known = {run["kalman_file"] for run in runs}
    if imu_dir.is_dir():
        for path in sorted(imu_dir.glob("kalman_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.name in known:
                continue
            parts = path.stem.split("_")
            runs.append({
                "uid": f"file:{path.name}", "legacy": True, "id": None, "recording": recording,
                "source": legacy_sources.get(parts[1], parts[1]) if len(parts) > 1 else "",
                "imu_name": "", "name": path.name, "notes": "",
                "created_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "settings": [], "outages": [], "metrics": {}, "kalman_file": path.name,
            })
    return runs


def delete_run_files(imu_dir: Path, run: dict[str, Any]) -> list[str]:
    removed = []
    for key in ("kalman_file", "dead_file", "corrected_file", "gnss_log_file", "report_file"):
        name = Path(run.get(key) or "").name
        path = imu_dir / name
        if name and path.is_file() and path.parent == imu_dir:
            path.unlink()
            removed.append(name)
    return removed
