"""Vienībtesti ar sintētiskiem N4 BIN datiem. Palaišana: python -m unittest discover -s src/positioning/tests"""
import importlib
import json
import os
import struct
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

GPS_EPOCH = 315964800.0
WEEK = 2400
T0 = GPS_EPOCH + WEEK * 604800 + 100 - 18  # UTC epoch pirmajai paketei


def n4(msg_id: int, week: int, tow_ms: int, payload: bytes) -> bytes:
    from positioning.binpackets import unicore_crc
    head = bytearray(24)
    head[0:3] = b"\xaa\x44\xb5"
    struct.pack_into("<H", head, 4, msg_id)
    struct.pack_into("<H", head, 6, len(payload))
    struct.pack_into("<H", head, 10, week)
    struct.pack_into("<I", head, 12, tow_ms)
    head[21] = 18
    body = bytes(head) + payload
    return body + struct.pack("<I", unicore_crc(body))


def make_bin() -> bytes:
    out = bytearray(b"$devicename,COM2*64\r\n")  # ASCII preamble
    out += n4(106, 1, 5, struct.pack("<I", 7) + b"\x00" * 20)  # GPS ephemeris pirms-fiksa (week=1), PRN 7
    out += n4(109, WEEK, 100000, struct.pack("<I", 11) + b"\x00" * 20)  # GAL ephemeris PRN 11, t=0
    for s in range(0, 100):  # 100 s, 1 Hz BESTNAVXYZ (240)
        out += n4(240, WEEK, 100000 + s * 1000, b"\x00" * 112)
        if s == 60:  # GPS PRN 7 jaunāka ephemeris t=60 (pirms loga 70..90)
            out += n4(106, WEEK, 100000 + 60_000, struct.pack("<I", 7) + b"\x01" * 20)
    out += b"\xaa\x44\xb5\x00"  # nepilns gals
    return bytes(out)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["POSITIONING_OUT"] = self.tmp.name
        for m in [m for m in sys.modules if m.startswith("positioning")]:
            del sys.modules[m]
        self.p = importlib.import_module("positioning")
        rec = Path(self.tmp.name) / "rec1" / "original"
        rec.mkdir(parents=True)
        (rec / "LOG00001.BIN").write_bytes(make_bin())

    def tearDown(self):
        self.tmp.cleanup()


class BinTests(Base):
    def test_crc_matches_reference(self):
        from positioning.binpackets import unicore_crc
        import converting.to_rinex.rinex305_toolkit.rinex305_toolkit.rinex305_conversion_full as rx
        data = bytes(range(200))
        self.assertEqual(unicore_crc(data), rx.crc32_novatel(data))

    def test_index(self):
        from positioning import splitter
        idx = splitter.get_index("rec1")
        self.assertEqual(len(idx.pos), 103)  # 1+1+100+1
        self.assertEqual(idx.leap, 18)
        self.assertTrue(idx.utc[0] != idx.utc[0])  # week=1 -> nan
        self.assertAlmostEqual(idx.time_range()[0], T0, places=3)


class SplitTests(Base):
    def test_split_window_and_ephemeris_carry(self):
        from positioning import splitter, store
        from positioning.binpackets import iter_pkts
        trip = splitter.split("rec1", T0 + 70, T0 + 90)
        self.assertEqual(trip["packets"], 20)
        # PRN 7 GPS pirms loga (pirms-fiksa), PRN 7 no t=60 (pirms loga, jaunākā) -> viens pārnests; GAL 11 -> pārnests
        self.assertEqual(trip["ephemeris_carried"], 2)
        data = (Path(self.tmp.name) / trip["session"] / "original" / "LOG00001.BIN").read_bytes()
        pk = list(iter_pkts(data))  # CRC derīgs arī pārrakstītajām
        self.assertEqual(len(pk), 22)
        carried = [p for p in pk if p.msg_id in (106, 109)]
        self.assertTrue(all(p.valid_time for p in carried))  # nedēļa labota no 1 uz derīgu
        gps = [p for p in carried if p.msg_id == 106][0]
        self.assertEqual(data[gps.pos + 24 + 4], 1)  # jaunākā (t=60) versija, nevis week=1 versija
        self.assertEqual(store.get_trip(trip["id"])["parent"], "rec1")
        self.assertEqual(store.list_trips("rec1")[0]["id"], trip["id"])

    def test_second_trip_gets_next_id_and_overlap_warning(self):
        from positioning import splitter
        a = splitter.split("rec1", T0 + 10, T0 + 30)
        b = splitter.split("rec1", T0 + 20, T0 + 40)
        self.assertTrue(a["id"].endswith("__t01") and b["id"].endswith("__t02"))
        self.assertTrue(any("Pārklājas" in w for w in b["warnings"]))

    def test_empty_window_rejected(self):
        from positioning import splitter
        with self.assertRaises(ValueError):
            splitter.split("rec1", T0 + 500, T0 + 600)
        with self.assertRaises(ValueError):
            splitter.split("rec1", T0 + 50, T0 + 40)

    def test_path_traversal_rejected(self):
        from positioning.paths import session_dir
        with self.assertRaises(ValueError):
            session_dir("../x")


class SyncTests(Base):
    def test_pairs(self):
        from positioning import imu_sync
        c0, spread = imu_sync.clock0_from_pairs([{"gnss_utc": 1000.0, "xdk_t_s": 10.0}, {"gnss_utc": 1020.01, "xdk_t_s": 30.0}])
        self.assertAlmostEqual(c0, 990.005, places=3)
        self.assertAlmostEqual(spread, 10.0, places=3)

    def test_trim_csv(self):
        from positioning import imu_sync
        src = Path(self.tmp.name) / "x.csv"
        src.write_text("t_ms,ax\n" + "".join(f"{i * 1000},1\n" for i in range(10)))
        dst = Path(self.tmp.name) / "y.csv"
        self.assertEqual(imu_sync.trim_xdk_csv(src, dst, 2.0, 4.0), 3)
        self.assertEqual(dst.read_text().splitlines()[0], "t_ms,ax")


class VideoAndApiTests(Base):
    def _server(self):
        from positioning import server
        srv = server.make_server("127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def _req(self, url, body=None, headers=None, method=None):
        r = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                   headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_api_split_video_range(self):
        base = self._server()
        s, _, b = self._req(f"{base}/api/recordings")
        self.assertEqual(json.loads(b)["recordings"][0]["id"], "rec1")
        from positioning import store
        s, _, b = self._req(f"{base}/api/trips", {"recording": "rec1", "start_utc": store.iso(T0 + 10), "end_utc": store.iso(T0 + 50)})
        trip = json.loads(b)["trip"]
        tid = trip["id"]
        vid = Path(self.tmp.name) / "clip.mp4"
        vid.write_bytes(bytes(range(256)) * 4)
        s, _, b = self._req(f"{base}/api/trips/{tid}/video", {"path": str(vid), "start_utc": store.iso(T0 + 10), "duration_s": 40})
        self.assertTrue(json.loads(b)["ok"])
        s, h, b = self._req(f"{base}/api/trips/{tid}/video/stream", headers={"Range": "bytes=10-19"})
        self.assertEqual((s, len(b), h["Content-Range"]), (206, 10, "bytes 10-19/1024"))
        s, h, b = self._req(f"{base}/api/trips/{tid}/video/stream", headers={"Range": "bytes=-4"})
        self.assertEqual((s, b), (206, bytes(range(252, 256))))
        s, _, _ = self._req(f"{base}/api/trips/{tid}/video/stream", headers={"Range": "bytes=5000-"})
        self.assertEqual(s, 416)
        s, _, b = self._req(f"{base}/api/trips/{tid}/video", {"shift_s": 2.0})
        self.assertAlmostEqual(json.loads(b)["video"]["start_utc"], T0 + 12, places=3)
        s, _, b = self._req(f"{base}/api/trips/{tid}", {}, method="DELETE")
        self.assertTrue(json.loads(b)["ok"])
        self.assertFalse((Path(self.tmp.name) / tid).exists())

    def test_video_offset_from_location(self):
        import numpy as np
        from positioning import tracks, video
        t = tracks.Track("gnss:x", "x", np.array([100.0, 101.0, 102.0]), np.array([56.0, 56.001, 56.002]),
                         np.array([24.0, 24.0, 24.0]), np.zeros(3))
        self.assertAlmostEqual(tracks.position_at(t, 101.5)["lat"], 56.0015, places=6)
        self.assertIsNone(tracks.position_at(t, 200.0))
        cmp = tracks.compare([t, t])
        self.assertAlmostEqual(cmp["rows"][0]["rms_m"], 0.0, places=6)

    def test_unknown_and_bad_requests(self):
        base = self._server()
        self.assertEqual(self._req(f"{base}/api/nothing")[0], 404)
        self.assertEqual(self._req(f"{base}/api/trips/rec1__t99")[0], 400)
        self.assertEqual(self._req(f"{base}/api/trips", {"recording": "..", "start_utc": 0, "end_utc": 1})[0], 400)


class WorkspaceTests(Base):
    def _w(self, name, text):
        d = Path(self.tmp.name) / ".t"
        d.mkdir(exist_ok=True)
        f = d / name
        f.write_text(text, encoding="utf-8")
        return f

    def test_sniff_kinds(self):
        from positioning import workspace as w
        self.assertEqual(w.sniff(self._w("LOG_005.CSV", "t_ms,ax,ay,az\n1,2,3,4\n"))["kind"], "xdk")
        self.assertEqual(w.sniff(self._w("SYNC00005.CSV", "# log=0:/LOGS/LOG00006.BIN\nSYNC,100,1,5000\n")), {"kind": "sync", "side": "gnss"})
        self.assertEqual(w.sniff(self._w("SYNC_005.CSV", "SYNC,1000,1,50\n")), {"kind": "sync", "side": "xdk"})
        self.assertEqual(w.sniff(self._w("a.mp4", "x"))["kind"], "video")
        self.assertEqual(w.sniff(self._w("junk.csv", "hello\n"))["kind"], "unknown")

    def test_store_and_inventory(self):
        from positioning import workspace as w
        r = w.store_file("rec1", self._w("SYNC_005.CSV", "SYNC,1000,1,50\nSYNC,5000,2,90\n"), "SYNC_005.CSV")
        self.assertEqual((r["kind"], r["side"], r["presses"]), ("sync", "xdk", 2))
        w.store_file("rec1", self._w("LOG_005.CSV", "t_ms,ax,ay,az,gx,gy,gz\n1,1,1,1,1,1,1\n"), "../evil/LOG_005.CSV")
        w.store_file("rec1", self._w("c.mp4", "vid"), "c.mp4")
        inv = w.inventory("rec1")
        self.assertEqual([x["name"] for x in inv["xdk"]], ["LOG_005.CSV"])
        self.assertEqual(inv["sync"][0]["side"], "xdk")
        self.assertEqual(inv["video"][0]["name"], "c.mp4")
        self.assertTrue((Path(self.tmp.name) / "rec1" / "imu" / "LOG_005.CSV").is_file())  # ceļš netika izmantots
        w.remove_file("rec1", "sync", "SYNC_005.CSV")
        self.assertEqual(w.inventory("rec1")["sync"], [])
        with self.assertRaises(ValueError):
            w.store_file("rec1", self._w("junk.csv", "hello\n"), "junk.csv")

    def test_bin_only_as_new_recording_and_duplicate(self):
        from positioning import workspace as w
        with self.assertRaises(ValueError):
            w.store_file("rec1", self._w("x.bin", "1234"), "x.bin")
        src = Path(self.tmp.name) / "rec1" / "original" / "LOG00001.BIN"
        t = Path(self.tmp.name) / ".t" / "new.part"
        t.parent.mkdir(exist_ok=True)
        t.write_bytes(src.read_bytes())
        self.assertEqual(w.create_recording(t, "LOG00001.BIN"), {"id": "rec1", "duplicate": True})
        t.write_bytes(src.read_bytes() + bytes([0]))  # cits saturs -> jauns ieraksts
        r = w.create_recording(t, "LOG00009.BIN")
        self.assertFalse(r["duplicate"])
        self.assertTrue((Path(self.tmp.name) / r["id"] / "original" / "LOG00009.BIN").is_file())
        self.assertTrue((Path(self.tmp.name) / r["id"] / "sync").is_dir())

    def test_http_upload(self):
        base = VideoAndApiTests._server(self)
        data = (Path(self.tmp.name) / "rec1" / "original" / "LOG00001.BIN").read_bytes() + b"zz"
        req = urllib.request.Request(f"{base}/api/recordings/upload?name=LOG00002.BIN", data=data, method="POST")
        j = json.loads(urllib.request.urlopen(req).read())
        self.assertTrue(j["ok"] and not j["duplicate"])
        rid = j["id"]
        req = urllib.request.Request(f"{base}/api/recordings/{rid}/files?name=SYNC00002.CSV", method="POST",
                                     data=b"# log=0:/LOGS/LOG00003.BIN\nSYNC,100,1,5000\n")
        j = json.loads(urllib.request.urlopen(req).read())
        self.assertEqual(j["file"]["side"], "gnss")
        inv = json.loads(urllib.request.urlopen(f"{base}/api/recordings/{rid}/files").read())
        self.assertEqual(inv["sync"][0]["presses"], 1)
        cfg = json.loads(urllib.request.urlopen(f"{base}/api/imu-config").read())
        self.assertIn("bias_profiles", cfg)
        req = urllib.request.Request(f"{base}/api/recordings/{rid}/files?kind=sync&name=SYNC00002.CSV", method="DELETE")
        self.assertEqual(json.loads(urllib.request.urlopen(req).read())["sync"], [])
        self.assertEqual(urllib.request.urlopen(f"{base}/recordings.html").status, 200)  # viens serveris arī statiskām lapām


class CatalogTests(Base):
    def test_catalog_groups_and_load(self):
        from positioning import recordings, tracks
        sdir = Path(self.tmp.name) / "rec1"
        head = "time,lat,lon,height_m,east_m,north_m,up_m,ve_mps,vn_mps,vu_mps,heading_deg,pitch_deg,roll_deg,sigma_e_m,sigma_n_m,gnss_status,zupt\n"
        row = "2026-11-03T23:10:0{i}+00:00,56.9{i},24.1,10,0,0,0,1,0,0,,,,0,0,used,0\n"
        body = head + "".join(row.format(i=i) for i in range(3))
        for rel in ("fusion/bestnav__ekf_full.csv", "fusion/fixed_ppk__ekf_rts.csv", "fusion/imu_raw.csv", "imu/compare_LOG_1/bestnav__gnss_only.csv"):
            f = sdir / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(body, encoding="utf-8")
        cat = tracks.catalog(sdir)
        ids = {t["id"]: t for t in cat}
        self.assertEqual(ids["fusion:fusion/bestnav__ekf_full"]["group"], "kalman")
        self.assertEqual(ids["fusion:fusion/fixed_ppk__ekf_rts"]["source_label"], "PPK fixed")
        self.assertEqual(ids["fusion:imu/compare_LOG_1/bestnav__gnss_only"]["origin"], "compare")
        self.assertEqual(ids["imu:raw"]["group"], "imu")
        tr = tracks.load_track(sdir, "imu:raw")
        self.assertEqual(len(tr), 3)
        self.assertEqual(len(tracks.load_track(sdir, "fusion:fusion/bestnav__ekf_full")), 3)
        with self.assertRaises(ValueError):
            tracks.load_track(sdir, "fusion:../../x")
        tree = recordings.session_tree()
        self.assertEqual(tree[0]["id"], "rec1")


if __name__ == "__main__":
    unittest.main()
