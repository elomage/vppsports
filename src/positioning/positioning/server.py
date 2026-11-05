"""JSON API (stdlib ThreadingHTTPServer) ar video Range straumēšanu. Noklusējums: http://127.0.0.1:8766"""
from __future__ import annotations

import io
import json
import uuid
import mimetypes
import re
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import fusion, imu_sync, jobs, pipeline, recordings, splitter, store, tracks, video, workspace
from .paths import OUT_DIR, session_dir

from viewer_server import ViewerHandler  # esošais viewer (statiskas lapas + vecie /api/*)

ID = r"([\w.\-]+)"
CHUNK = 1 << 20


def _trip_session(trip_id: str) -> Path:
    return OUT_DIR / store.get_trip(trip_id)["session"]


def _tracks(trip_id: str, ids: list[str]) -> list[tracks.Track]:
    s = _trip_session(trip_id)
    return [tracks.load_track(s, i) for i in ids]


def _ids(q: dict, default: str = "") -> list[str]:
    return [x for x in (q.get("tracks", [default])[0]).split(",") if x]


# ---- GET -------------------------------------------------------------------------------------------------------
def get_routes(path: str, q: dict):
    if path == "/api/recordings":
        return {"ok": True, "recordings": recordings.list_recordings()}
    if path == "/api/jobs":
        return {"ok": True, "jobs": jobs.listing()}
    if path == "/api/fusion/methods":
        return {"ok": True, "methods": fusion.methods()}
    if m := re.fullmatch(rf"/api/jobs/{ID}", path):
        return {"ok": True, "job": jobs.get(m[1])}
    if path == "/api/sessions":
        return {"ok": True, "sessions": recordings.session_tree()}
    if m := re.fullmatch(rf"/api/sessions/{ID}/catalog", path):
        return {"ok": True, **recordings.session_catalog(m[1])}
    if m := re.fullmatch(rf"/api/sessions/{ID}/presses", path):
        return {"ok": True, **workspace.presses(m[1])}
    if m := re.fullmatch(rf"/api/sessions/{ID}/tracks", path):
        ids = _ids(q)
        if not ids:
            raise ValueError("Norādi trajektorijas (?tracks=a,b).")
        s = session_dir(m[1])
        mx = int(q.get("max", ["6000"])[0])
        return {"ok": True, "features": [tracks.to_geojson(tracks.load_track(s, i), mx) for i in ids]}
    if path == "/api/imu-config":
        return {"ok": True, **workspace.imu_config()}
    if m := re.fullmatch(rf"/api/recordings/{ID}/files", path):
        return {"ok": True, **workspace.inventory(m[1])}
    if m := re.fullmatch(rf"/api/recordings/{ID}/overview", path):
        return {"ok": True, **recordings.overview(m[1], float(q.get("step_s", ["1"])[0]))}
    if m := re.fullmatch(rf"/api/recordings/{ID}/trips", path):
        return {"ok": True, "trips": store.list_trips(m[1])}
    if m := re.fullmatch(rf"/api/recordings/{ID}/xdk", path):
        return {"ok": True, **imu_sync.parent_links(m[1])}
    if m := re.fullmatch(rf"/api/trips/{ID}", path):
        return {"ok": True, "trip": store.get_trip(m[1])}
    if m := re.fullmatch(rf"/api/trips/{ID}/catalog", path):
        return {"ok": True, "tracks": tracks.catalog(_trip_session(m[1]))}
    if m := re.fullmatch(rf"/api/trips/{ID}/tracks", path):
        ids = _ids(q) or [t["id"] for t in tracks.catalog(_trip_session(m[1]))]
        mx = int(q.get("max", ["6000"])[0])
        feats = [tracks.to_geojson(t, mx) for t in _tracks(m[1], ids)]
        return {"ok": True, "tracks": {"type": "FeatureCollection", "features": feats}}
    if m := re.fullmatch(rf"/api/trips/{ID}/compare", path):
        ids = _ids(q)
        return {"ok": True, **tracks.compare(_tracks(m[1], ids))}
    if m := re.fullmatch(rf"/api/trips/{ID}/rinex", path):
        return {"ok": True, "files": [p.name for p in pipeline.rinex_files(m[1])]}
    if m := re.fullmatch(rf"/api/trips/{ID}/sync", path):
        trip = store.get_trip(m[1])
        return {"ok": True, "sync": trip.get("sync")}
    if m := re.fullmatch(rf"/api/trips/{ID}/fusion", path):
        return {"ok": True, "runs": fusion.list_runs(m[1])}
    if m := re.fullmatch(rf"/api/trips/{ID}/video", path):
        return {"ok": True, "video": video.get_video(m[1])}
    if m := re.fullmatch(rf"/api/trips/{ID}/video/position", path):
        return {"ok": True, **video.position(m[1], float(q["t"][0]), q.get("track", ["gnss:bestnav"])[0])}
    if m := re.fullmatch(rf"/api/trips/{ID}/video/tracks", path):
        return {"ok": True, **video.video_geojson(m[1], _ids(q, "gnss:bestnav"))}
    return None


# ---- POST ------------------------------------------------------------------------------------------------------
def post_routes(path: str, b: dict, method: str = "POST"):
    if path == "/api/trips":
        trip = splitter.split(b["recording"], b["start_utc"], b["end_utc"], b.get("name", ""))
        return {"ok": True, "trip": trip}
    if m := re.fullmatch(rf"/api/recordings/{ID}/video", path):
        keys = ("start_utc", "video_t", "utc", "lat", "lon", "shift_s", "track")
        return {"ok": True, "video": video.set_rec_video(m[1], b.get("file", ""), **{k: b[k] for k in keys if k in b})}
    if m := re.fullmatch(rf"/api/recordings/{ID}/link", path):
        return {"ok": True, **workspace.auto_link(m[1], b.get("xdk"), b.get("xdk_sync"), b.get("gnss_sync"),
                                                  bool(b.get("make_default", True)), b.get("note", ""))}
    if method == "DELETE" and (m := re.fullmatch(rf"/api/recordings/{ID}/files", path)):
        workspace.remove_file(m[1], b.get("kind", ""), b.get("name", ""))
        return {"ok": True, **workspace.inventory(m[1])}
    if m := re.fullmatch(rf"/api/recordings/{ID}/xdk", path):
        return {"ok": True, "entry": imu_sync.attach_to_parent(m[1], b["xdk"], b.get("xdk_sync"), b.get("gnss_sync"), b.get("note", ""))}
    if m := re.fullmatch(rf"/api/trips/{ID}", path):
        tid = m[1]
        if method == "DELETE":
            session = _trip_session(tid)
            store.remove_trip(tid)
            if b.get("delete_files", True):
                splitter.delete_trip_session(session.name)
            return {"ok": True, "removed": tid}
        changes = {k: b[k] for k in ("name",) if k in b}
        return {"ok": True, "trip": store.update_trip(tid, **changes)}
    if m := re.fullmatch(rf"/api/sessions/{ID}/imu-raw", path):
        sname = m[1]
        session_dir(sname)
        job = jobs.submit("imu-raw", lambda log: fusion.imu_raw(OUT_DIR / sname, b.get("source"), log), session=sname)
        return {"ok": True, "job": {k: v for k, v in job.items() if k != "log"}}
    if m := re.fullmatch(rf"/api/trips/{ID}/process", path):
        tid = m[1]
        store.get_trip(tid)
        job = jobs.submit("process", lambda log: pipeline.process(
            tid, b.get("steps"), b.get("base", "auto"), b.get("ppk_mode", "all"), b.get("obs_source", "auto"), log), trip=tid)
        return {"ok": True, "job": {k: v for k, v in job.items() if k != "log"}}
    if m := re.fullmatch(rf"/api/trips/{ID}/sync/suggest", path):
        return {"ok": True, **imu_sync.suggest(m[1], b["xdk"])}
    if m := re.fullmatch(rf"/api/trips/{ID}/sync", path):
        return {"ok": True, "sync": imu_sync.set_sync(
            m[1], b.get("method", "manual"), b["xdk"], b.get("xdk_clock0_utc"), b.get("pairs"), b.get("shift_s"), b.get("note", ""))}
    if m := re.fullmatch(rf"/api/trips/{ID}/fusion", path):
        tid = m[1]
        store.get_trip(tid)
        job = jobs.submit("fusion", lambda log: fusion.run_matrix(
            tid, b.get("sources"), b.get("methods"), int(b.get("jobs", 4)), b.get("static", "auto"),
            b.get("fusion_set"), b.get("outage_test"), log), trip=tid)
        return {"ok": True, "job": {k: v for k, v in job.items() if k != "log"}}
    if m := re.fullmatch(rf"/api/trips/{ID}/video", path):
        keys = ("path", "start_utc", "video_t", "utc", "lat", "lon", "shift_s", "track", "duration_s")
        args = {k: b[k] for k in keys if k in b}
        if b.get("file"):  # ieraksta video/ mapē augšupielādēts fails
            args["path"] = str(session_dir(store.parent_of(m[1])) / "video" / workspace.clean_name(b["file"]))
        return {"ok": True, "video": video.set_video(m[1], **args)}
    return None


# ---- handler ---------------------------------------------------------------------------------------------------
API_PREFIXES = ("/api/sessions", "/api/recordings", "/api/trips", "/api/jobs", "/api/fusion/", "/api/imu-config")
MAX_UPLOAD = 64 * 1024 ** 3


def _mine(path: str) -> bool:
    return path.startswith(API_PREFIXES)


class Handler(ViewerHandler):
    """Viens serveris: statiskās viewer lapas + vecie /api/* (ViewerHandler) + jaunie ierakstu/braucienu /api/*."""

    def send_response(self, code, message=None):
        self._has_cache_header = False
        super().send_response(code, message)

    def send_header(self, keyword, value):
        if keyword.lower() == "cache-control":
            self._has_cache_header = True
        super().send_header(keyword, value)

    def end_headers(self):
        if not getattr(self, "_has_cache_header", False):  # statiskie faili: vienmēr pārbauda, vai nav mainījušies
            super().send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _guard(self, fn):
        try:
            res = fn()
            if res is None:
                return self._json({"ok": False, "error": "Nezināms endpoint"}, 404)
            return self._json(res)
        except (ValueError, KeyError) as exc:
            return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}" if isinstance(exc, KeyError) else str(exc)}, 400)
        except SystemExit as exc:
            return self._json({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in (("Access-Control-Allow-Origin", "*"), ("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS"),
                     ("Access-Control-Allow-Headers", "Content-Type,Range")):
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if not _mine(u.path):
            return super().do_GET()
        q = parse_qs(u.query)
        if m := re.fullmatch(rf"/api/trips/{ID}/video/stream", u.path):
            return self._guard_stream(lambda: self._stream_video(m[1]))
        if m := re.fullmatch(rf"/api/recordings/{ID}/video/([^/]+)", u.path):
            return self._guard_stream(lambda: self._stream_file(session_dir(m[1]) / "video" / workspace.clean_name(m[2])))
        if m := re.fullmatch(rf"/api/trips/{ID}/rinex\.zip", u.path):
            return self._guard_stream(lambda: self._rinex_zip(m[1]))
        self._guard(lambda: get_routes(u.path, q))

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            raise ValueError("Nederīgs JSON ķermenis") from None

    def _receive(self) -> Path:
        """Raw ķermeni (augšupielādi) ieraksta pagaidu failā pa daļām, neielādējot atmiņā."""
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            raise ValueError("Tukšs fails.")
        if n > MAX_UPLOAD:
            raise ValueError("Fails ir pārāk liels.")
        tmpdir = OUT_DIR / ".uploads"
        tmpdir.mkdir(parents=True, exist_ok=True)
        tmp = tmpdir / f"{uuid.uuid4().hex}.part"
        left = n
        with tmp.open("wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(CHUNK, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            tmp.unlink(missing_ok=True)
            raise ValueError("Augšupielāde pārtraukta.")
        return tmp

    def _upload(self, u):
        q = parse_qs(u.query)
        name = q.get("name", [""])[0]
        if not name:
            raise ValueError("Norādi faila nosaukumu (?name=...).")
        if u.path == "/api/recordings/upload":
            tmp = self._receive()
            try:
                return {"ok": True, **workspace.create_recording(tmp, name)}
            finally:
                tmp.unlink(missing_ok=True)
        m = re.fullmatch(rf"/api/recordings/{ID}/files", u.path)
        session_dir(m[1])  # pārbauda, ka ieraksts eksistē, pirms saņem datus
        tmp = self._receive()
        try:
            return {"ok": True, "file": workspace.store_file(m[1], tmp, name, q.get("kind", ["auto"])[0]),
                    **{k: v for k, v in workspace.inventory(m[1]).items() if k in ("xdk", "sync", "video")}}
        finally:
            tmp.unlink(missing_ok=True)

    def _is_upload(self, path: str) -> bool:
        return path == "/api/recordings/upload" or (
            re.fullmatch(rf"/api/recordings/{ID}/files", path) is not None and "name=" in self.path)

    def _route_write(self, method: str):
        u = urlparse(self.path)
        if not _mine(u.path):
            return getattr(super(), f"do_{method}")()
        if method == "POST" and self._is_upload(u.path):
            return self._guard(lambda: self._upload(u))
        q = parse_qs(u.query)
        if method == "DELETE" and q:
            return self._guard(lambda: post_routes(u.path, {k: v[0] for k, v in q.items()}, "DELETE"))
        self._guard(lambda: post_routes(u.path, self._body(), method))

    def do_POST(self):
        self._route_write("POST")

    def do_PATCH(self):
        self._route_write("PATCH")

    def do_DELETE(self):
        self._route_write("DELETE")

    def _guard_stream(self, fn):
        try:
            fn()
        except (ValueError, KeyError) as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _rinex_zip(self, trip_id: str):
        files = pipeline.rinex_files(trip_id)
        if not files:
            raise ValueError("RINEX faili nav atrasti (palaid process → rinex).")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in files:
                z.write(p, p.name)
        data = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{trip_id}_rinex.zip"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _stream_video(self, trip_id: str):
        v = video.get_video(trip_id)
        if not v:
            raise ValueError("Braucienam nav piesaistīts video.")
        self._stream_file(Path(v["path"]))  # tikai piesaistītais fails, nekādi klienta ceļi

    def _stream_file(self, path: Path):
        if not path.is_file():
            raise ValueError("Fails nav atrasts.")
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
            if not m or (not m[1] and not m[2]):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            if m[1]:
                start = int(m[1])
                end = min(int(m[2]), size - 1) if m[2] else size - 1
            else:
                start = max(0, size - int(m[2]))
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(CHUNK, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)


def make_server(host: str = "localhost", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "localhost", port: int = 8765) -> None:
    srv = make_server(host, port)
    print(f"positioning API: http://{host}:{port}/api/recordings   (OUT = {OUT_DIR})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
