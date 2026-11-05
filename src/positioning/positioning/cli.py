"""python -m positioning <komanda>: split | process | sync | fuse | video | list | serve"""
from __future__ import annotations

import argparse
import json
import sys

from . import fusion, imu_sync, pipeline, recordings, server, splitter, video


def _p(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="positioning")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="garie ieraksti")
    s = sub.add_parser("split", help="izveido braucienu laika logā")
    s.add_argument("recording"); s.add_argument("start"); s.add_argument("end"); s.add_argument("--name", default="")
    s = sub.add_parser("process", help="CSV/RINEX/PPK braucienam")
    s.add_argument("trip"); s.add_argument("--steps", default="csv,rinex,observation_single")
    s.add_argument("--base", default="auto"); s.add_argument("--ppk-mode", default="all")
    s = sub.add_parser("sync", help="IMU sinhronizācija braucienam")
    s.add_argument("trip"); s.add_argument("xdk")
    s.add_argument("--method", default="button", choices=["button", "manual", "pairs", "yaw", "suggest"])
    s.add_argument("--clock0-utc"); s.add_argument("--shift-s", type=float)
    s.add_argument("--pair", action="append", default=[], help="GNSS_UTC=XDK_T_S, atkārtojams")
    s = sub.add_parser("fuse", help="GNSS avots × Kalman metode")
    s.add_argument("trip"); s.add_argument("--sources"); s.add_argument("--methods"); s.add_argument("--jobs", type=int, default=4)
    s = sub.add_parser("video", help="video nobīde")
    s.add_argument("trip"); s.add_argument("--path"); s.add_argument("--start-utc")
    s.add_argument("--video-t", type=float); s.add_argument("--utc"); s.add_argument("--shift-s", type=float)
    s = sub.add_parser("serve", help="HTTP API")
    s.add_argument("--host", default="localhost"); s.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            _p(recordings.list_recordings())
        elif a.cmd == "split":
            _p(splitter.split(a.recording, a.start, a.end, a.name))
        elif a.cmd == "process":
            r = pipeline.process(a.trip, a.steps.split(","), a.base, a.ppk_mode, log=print)
            return 0 if r["ok"] else 1
        elif a.cmd == "sync":
            if a.method == "suggest":
                _p(imu_sync.suggest(a.trip, a.xdk))
            else:
                pairs = [{"gnss_utc": x.split("=")[0], "xdk_t_s": float(x.split("=")[1])} for x in a.pair]
                _p(imu_sync.set_sync(a.trip, a.method, a.xdk, a.clock0_utc, pairs or None, a.shift_s))
        elif a.cmd == "fuse":
            r = fusion.run_matrix(a.trip, a.sources.split(",") if a.sources else None,
                                  a.methods.split(",") if a.methods else None, a.jobs, log=print)
            _p(r["runs"])
        elif a.cmd == "video":
            _p(video.set_video(a.trip, a.path, a.start_utc, a.video_t, a.utc, shift_s=a.shift_s))
        elif a.cmd == "serve":
            server.serve(a.host, a.port)
    except (ValueError, SystemExit) as exc:
        print(f"Kļūda: {exc}", file=sys.stderr)
        return 2
    return 0
