#!/usr/bin/env python3
"""Build a local web viewer for switching between GNSS recordings."""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from session_paths import OUT_DIR, find_receiver_csv
from gnss_track_utils import (
    Match,
    TrackPoint,
    attach_ppk_quality,
    load_ppk_quality,
    load_track,
    match_tracks,
    pct,
)


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return cleaned or "recording"


def finite_pair(point: TrackPoint) -> bool:
    return math.isfinite(point.lat) and math.isfinite(point.lon)


def point_properties(point: TrackPoint, index: int) -> dict[str, Any]:
    props: dict[str, Any] = {
        "track": point.label,
        "index": index + 1,
        "time": point.time.isoformat() if point.time else "",
    }
    if point.height is not None:
        props["height_m"] = round(point.height, 3)
    if point.heading is not None:
        props["heading_deg"] = round(point.heading, 2)
    if point.speed_mps is not None:
        props["speed_mps"] = round(point.speed_mps, 3)
    for key in ("Q", "ns", "ratio", "position_type", "satellites_used"):
        if point.raw.get(key) not in (None, ""):
            props[key] = point.raw[key]
    return props


def point_time_iso(point: TrackPoint) -> str:
    return point.time.isoformat() if point.time else ""


def sampled_path_points(points: list[TrackPoint], max_path_points: int | None) -> list[TrackPoint]:
    path_points = [point for point in points if finite_pair(point)]
    if max_path_points is None or len(path_points) <= max_path_points:
        return path_points
    step = max(1, math.ceil(len(path_points) / max_path_points))
    sampled = path_points[::step]
    if sampled[-1] is not path_points[-1]:
        sampled.append(path_points[-1])
    return sampled


def track_geojson(points: list[TrackPoint], color: str, sample_every: int, max_path_points: int | None = None) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    if points:
        path_points = sampled_path_points(points, max_path_points)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[point.lon, point.lat] for point in path_points],
            },
            "properties": {
                "kind": "path",
                "label": points[0].label,
                "color": color,
                "points": len(points),
                "times": [point_time_iso(point) for point in path_points],
            },
        })

        marker_indexes = sorted({0, len(points) - 1, *range(0, len(points), max(1, sample_every))})
        for index in marker_indexes:
            point = points[index]
            if not finite_pair(point):
                continue
            props = point_properties(point, index)
            props["kind"] = "point"
            props["color"] = color
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [point.lon, point.lat]},
                "properties": props,
            })

    return {"type": "FeatureCollection", "features": features}


def heading_endpoint(lat: float, lon: float, heading_deg: float, length_m: float) -> tuple[float, float]:
    radius_m = 6_371_000.0
    bearing = math.radians(heading_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    angular = length_m / radius_m
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def headings_geojson(points: list[TrackPoint], color: str, sample_every: int, length_m: float) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    step = max(1, sample_every)
    for index, point in enumerate(points[::step]):
        if point.heading is None or not finite_pair(point):
            continue
        end_lat, end_lon = heading_endpoint(point.lat, point.lon, point.heading, length_m)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [point.lon, point.lat],
                    [end_lon, end_lat],
                ],
            },
            "properties": {
                "kind": "heading",
                "index": index + 1,
                "track": point.label,
                "time": point_time_iso(point),
                "heading_deg": round(point.heading, 2),
                "color": color,
            },
        })
    return {"type": "FeatureCollection", "features": features}


def match_color(horizontal_m: float) -> str:
    if horizontal_m < 0.25:
        return "#2ca02c"
    if horizontal_m < 1.0:
        return "#f2c94c"
    if horizontal_m < 3.0:
        return "#f2994a"
    return "#d62728"


def shifted_point_time_iso(point: TrackPoint, offset_s: float) -> str:
    if point.time is None:
        return ""
    return (point.time + timedelta(seconds=offset_s)).isoformat()


def matches_geojson(matches: list[Match], every_n: int, ppk_time_offset_s: float) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    step = max(1, every_n)
    for index, match in enumerate(matches[::step]):
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [match.regular.lon, match.regular.lat],
                    [match.ppk.lon, match.ppk.lat],
                ],
            },
            "properties": {
                "kind": "match",
                "index": index + 1,
                "horizontal_m": round(match.horizontal_m, 3),
                "distance_3d_m": round(match.distance_3d_m, 3),
                "east_m": round(match.east_m, 3),
                "north_m": round(match.north_m, 3),
                "up_m": round(match.up_m, 3),
                "time_delta_s": round(match.time_delta_s, 3),
                "time": point_time_iso(match.regular),
                "ppk_time": shifted_point_time_iso(match.ppk, ppk_time_offset_s),
                "color": match_color(match.horizontal_m),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def bounds_for(points: list[TrackPoint]) -> list[list[float]] | None:
    usable = [point for point in points if finite_pair(point)]
    if not usable:
        return None
    return [
        [min(point.lat for point in usable), min(point.lon for point in usable)],
        [max(point.lat for point in usable), max(point.lon for point in usable)],
    ]


def time_extent_for(points: list[TrackPoint]) -> list[str] | None:
    times = [point.time for point in points if point.time is not None]
    if not times:
        return None
    return [min(times).isoformat(), max(times).isoformat()]


def optional_regular_csv(session_dir: Path) -> Path | None:
    try:
        return find_receiver_csv(session_dir)
    except SystemExit:
        return None


def load_optional_regular_track(session_dir: Path) -> list[TrackPoint]:
    regular_csv = optional_regular_csv(session_dir)
    if regular_csv is None:
        return []
    try:
        return load_track(
            regular_csv,
            "Receiver",
            time_candidates=["utc", "timestamp", "time", "datetime", "date_time"],
            heading_candidates=["heading_deg", "heading", "true_heading_deg", "direction"],
        )
    except SystemExit as exc:
        print(f"Skipping receiver layer for {session_dir.name}: {exc}")
        return []


def load_optional_track(path: Path, label: str) -> list[TrackPoint]:
    if not path.is_file():
        return []
    try:
        return load_track(
            path,
            label,
            time_candidates=["time", "utc", "timestamp", "datetime", "date_time"],
            heading_candidates=["direction", "heading_deg", "heading", "true_heading_deg"],
        )
    except SystemExit as exc:
        print(f"Skipping {label} layer for {path.parent.parent.name}: {exc}")
        return []


def shifted_track_times(points: list[TrackPoint], offset_s: float) -> list[TrackPoint]:
    if not points or offset_s == 0:
        return points
    offset = timedelta(seconds=offset_s)
    return [
        replace(point, time=point.time + offset if point.time is not None else None)
        for point in points
    ]


def newest_matching_csv(directory: Path, pattern: str) -> Path | None:
    if not directory.is_dir():
        return None
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def stats_for(
    regular: list[TrackPoint],
    ppk: list[TrackPoint],
    float_ppk: list[TrackPoint],
    dgps: list[TrackPoint],
    observation_single: list[TrackPoint],
    kalman: list[TrackPoint],
    imu_dead_reckoning: list[TrackPoint],
    matches: list[Match],
    float_matches: list[Match],
    dgps_matches: list[Match],
) -> dict[str, Any]:
    q_counts: dict[str, int] = {}
    for point in ppk:
        q = point.raw.get("Q")
        if q:
            q_counts[q] = q_counts.get(q, 0) + 1

    stats: dict[str, Any] = {
        "receiver_points": len(regular),
        "ppk_points": len(ppk),
        "float_points": len(float_ppk),
        "dgps_points": len(dgps),
        "observation_single_points": len(observation_single),
        "kalman_points": len(kalman),
        "imu_dead_reckoning_points": len(imu_dead_reckoning),
        "matches": len(matches),
        "float_matches": len(float_matches),
        "dgps_matches": len(dgps_matches),
        "ppk_quality": q_counts,
    }
    if matches:
        horizontals = [match.horizontal_m for match in matches]
        distances = [match.distance_3d_m for match in matches]
        stats.update({
            "horizontal_median_m": round(statistics.median(horizontals), 3),
            "horizontal_p95_m": round(pct(horizontals, 0.95), 3),
            "distance_3d_median_m": round(statistics.median(distances), 3),
        })
    return stats


def load_recording(session_dir: Path, ppk_time_offset_s: float, max_time_delta_s: float) -> tuple[dict[str, Any], dict[str, Any]]:
    ppk_csv = session_dir / "ppk" / "solution.csv"
    float_csv = session_dir / "ppk" / "solution_float.csv"
    dgps_csv = session_dir / "ppk" / "solution_dgps.csv"
    single_csv = session_dir / "ppk" / "observation_single.csv"
    imu_dir = session_dir / "imu"
    kalman_csv = newest_matching_csv(imu_dir, "kalman_*.csv")
    imu_dead_reckoning_csv = newest_matching_csv(imu_dir, "imu_dead_reckoning_*.csv")
    solution_pos = session_dir / "ppk" / "solution.pos"
    float_pos = session_dir / "ppk" / "solution_float.pos"
    dgps_pos = session_dir / "ppk" / "solution_dgps.pos"

    regular = load_optional_regular_track(session_dir)
    ppk: list[TrackPoint] = []
    if ppk_csv.is_file():
        ppk = load_track(
            ppk_csv,
            "PPK fixed",
            time_candidates=["time", "utc", "timestamp", "datetime", "date_time"],
            heading_candidates=["direction", "heading_deg", "heading", "true_heading_deg"],
        )
        attach_ppk_quality(ppk, load_ppk_quality(solution_pos))

    float_ppk: list[TrackPoint] = []
    if float_csv.is_file():
        float_ppk = load_track(
            float_csv,
            "PPK float",
            time_candidates=["time", "utc", "timestamp", "datetime", "date_time"],
            heading_candidates=["direction", "heading_deg", "heading", "true_heading_deg"],
        )
        attach_ppk_quality(float_ppk, load_ppk_quality(float_pos))

    dgps: list[TrackPoint] = []
    if dgps_csv.is_file():
        dgps = load_track(
            dgps_csv,
            "PPK DGPS",
            time_candidates=["time", "utc", "timestamp", "datetime", "date_time"],
            heading_candidates=["direction", "heading_deg", "heading", "true_heading_deg"],
        )
        attach_ppk_quality(dgps, load_ppk_quality(dgps_pos))

    observation_single: list[TrackPoint] = []
    if single_csv.is_file():
        observation_single = load_track(
            single_csv,
            "Observation single",
            time_candidates=["time", "utc", "timestamp", "datetime", "date_time"],
            heading_candidates=["direction", "heading_deg", "heading", "true_heading_deg"],
        )

    kalman = load_optional_track(kalman_csv, "Kalman GNSS+IMU") if kalman_csv else []
    imu_dead_reckoning = load_optional_track(imu_dead_reckoning_csv, "IMU diagnostic") if imu_dead_reckoning_csv else []

    matches = match_tracks(regular, ppk, ppk_time_offset_s, max_time_delta_s) if regular and ppk else []
    float_matches = match_tracks(regular, float_ppk, ppk_time_offset_s, max_time_delta_s) if regular and float_ppk else []
    dgps_matches = match_tracks(regular, dgps, ppk_time_offset_s, max_time_delta_s) if regular and dgps else []
    ppk = shifted_track_times(ppk, ppk_time_offset_s)
    float_ppk = shifted_track_times(float_ppk, ppk_time_offset_s)
    dgps = shifted_track_times(dgps, ppk_time_offset_s)
    observation_single = shifted_track_times(observation_single, ppk_time_offset_s)
    all_points = regular + ppk + float_ppk + dgps + observation_single + kalman + imu_dead_reckoning
    bounds = bounds_for(all_points)
    if bounds is None:
        raise SystemExit(f"No usable coordinates found in {session_dir}")

    layers = {
        "receiver": track_geojson(regular, "#1f77b4", sample_every=25),
        "ppk": track_geojson(ppk, "#d62728", sample_every=25),
        "float": track_geojson(float_ppk, "#9467bd", sample_every=25),
        "dgps": track_geojson(dgps, "#ff7f0e", sample_every=25),
        "observation": track_geojson(observation_single, "#2ca02c", sample_every=25),
        "kalman": track_geojson(kalman, "#111827", sample_every=250, max_path_points=5000),
        "imu_dead_reckoning": track_geojson(imu_dead_reckoning, "#00a6a6", sample_every=250, max_path_points=5000),
        "matches": matches_geojson(matches, every_n=3, ppk_time_offset_s=ppk_time_offset_s),
        "float_matches": matches_geojson(float_matches, every_n=3, ppk_time_offset_s=ppk_time_offset_s),
        "dgps_matches": matches_geojson(dgps_matches, every_n=3, ppk_time_offset_s=ppk_time_offset_s),
        "receiver_headings": headings_geojson(regular, "#1f77b4", sample_every=25, length_m=1.5),
        "ppk_headings": headings_geojson(ppk, "#d62728", sample_every=25, length_m=1.5),
        "float_headings": headings_geojson(float_ppk, "#9467bd", sample_every=25, length_m=1.5),
        "dgps_headings": headings_geojson(dgps, "#ff7f0e", sample_every=25, length_m=1.5),
        "observation_headings": headings_geojson(observation_single, "#2ca02c", sample_every=25, length_m=1.5),
    }
    summary = {
        "id": safe_id(session_dir.name),
        "name": session_dir.name,
        "bounds": bounds,
        "time_extent": time_extent_for(all_points),
        "stats": stats_for(
            regular,
            ppk,
            float_ppk,
            dgps,
            observation_single,
            kalman,
            imu_dead_reckoning,
            matches,
            float_matches,
            dgps_matches,
        ),
        "available": {
            "receiver": bool(regular),
            "ppk": bool(ppk),
            "float": bool(float_ppk),
            "dgps": bool(dgps),
            "observation": bool(observation_single),
            "kalman": bool(kalman),
            "imu_dead_reckoning": bool(imu_dead_reckoning),
            "matches": bool(matches),
            "float_matches": bool(float_matches),
            "dgps_matches": bool(dgps_matches),
            "receiver_headings": bool(layers["receiver_headings"]["features"]),
            "ppk_headings": bool(layers["ppk_headings"]["features"]),
            "float_headings": bool(layers["float_headings"]["features"]),
            "dgps_headings": bool(layers["dgps_headings"]["features"]),
            "observation_headings": bool(layers["observation_headings"]["features"]),
        },
    }
    return summary, {"recording": summary["name"], "layers": layers}


def build_viewer(out_dir: Path, output_dir: Path, ppk_time_offset_s: float, max_time_delta_s: float, esri_native_zoom: int) -> int:
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    recordings: list[dict[str, Any]] = []

    for session_dir in sorted(path for path in out_dir.iterdir() if path.is_dir()):
        try:
            summary, payload = load_recording(session_dir, ppk_time_offset_s, max_time_delta_s)
        except SystemExit as exc:
            print(f"Skipping {session_dir.name}: {exc}")
            continue
        filename = f"{summary['id']}.json"
        summary["data"] = f"data/{filename}"
        (data_dir / filename).write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        recordings.append(summary)
        print(f"Added {session_dir.name}")

    manifest = {
        "recordings": recordings,
        "settings": {
            "esri_native_zoom": esri_native_zoom,
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output_dir / "index.html").write_text(viewer_html(esri_native_zoom), encoding="utf-8")
    return len(recordings)


def viewer_html(esri_native_zoom: int) -> str:
    template = Path(__file__).with_name("recording_viewer_template.html").read_text(encoding="utf-8")
    return template.replace("__ESRI_NATIVE_ZOOM__", str(esri_native_zoom))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a browser viewer for all generated GNSS recordings.")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR, help="Directory containing recording folders.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "viewer", help="Viewer output directory.")
    parser.add_argument("--max-time-delta-s", type=float, default=0.15)
    parser.add_argument(
        "--ppk-time-offset-s",
        type=float,
        default=-18.0,
        help="Offset PPK times for matching. RTKLIB output is GPST and receiver CSV is UTC, so default is -18.",
    )
    parser.add_argument(
        "--esri-native-zoom",
        type=int,
        default=19,
        help="Highest Esri imagery zoom level to request in the viewer.",
    )
    args = parser.parse_args()

    count = build_viewer(
        out_dir=args.out_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        ppk_time_offset_s=args.ppk_time_offset_s,
        max_time_delta_s=args.max_time_delta_s,
        esri_native_zoom=args.esri_native_zoom,
    )
    print(f"Built viewer with {count} recordings: {args.output_dir.resolve() / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
