import csv
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fusion_db
import fusion_runs


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch.object(fusion_db, "DB_PATH", self.root / "runs.sqlite")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.imu_dir = self.root / "session" / "imu"
        self.imu_dir.mkdir(parents=True)

    def make_files(self, stem="kalman_bestnav_ride_20260101_000000"):
        # fused path along +north at 10 m/s, 100 Hz for 10 s; GNSS 1 Hz, offset 1 m east
        fused = [{"time": f"2026-01-01T00:00:{i // 100:02d}.{(i % 100) * 10000:06d}+00:00",
                  "lat": f"{56.0 + math.degrees(i / 10 / 6378137.0):.9f}", "lon": "24.0",
                  "east_m": "0.0", "north_m": f"{i / 10:.1f}", "gnss_status": "used"} for i in range(1000)]
        write_csv(self.imu_dir / f"{stem}.csv", fused)
        log = [{"time": f"2026-01-01T00:00:{s:02d}+00:00", "status": "used" if s != 5 else "rejected",
                "innovation_sigma": "0.5", "sigma_m": "1.0", "east_m": "1.0", "north_m": f"{s * 10.0:.1f}"} for s in range(10)]
        write_csv(self.imu_dir / f"fusion_gnss_{stem}.csv", log)
        (self.imu_dir / f"{stem}_report.txt").write_text("fusion_gnss_epochs=10\nfusion_imu_used=1\n", encoding="utf-8")
        return f"{stem}.csv"

    def store(self, name="A", settings=("outlier_gate_sigma=2",)):
        kalman = self.make_files()
        return fusion_runs.store_run(
            self.imu_dir, "session", "bestnav", Path("ride.BIN"),
            {"kalman": kalman, "label": "bestnav"},
            {"run_name": name, "fusion_set": list(settings), "gnss_outage": ["1:2"], "imu_start_utc": "2026-01-01T00:00:00Z"},
        )

    def test_store_keeps_settings_metrics_and_per_run_report(self):
        run = self.store()
        self.assertEqual(run["settings"], ["outlier_gate_sigma=2"])
        self.assertEqual(run["outages"], ["1:2"])
        self.assertEqual(run["metrics"]["fusion_imu_used"], "1")
        self.assertEqual(run["report_file"], "kalman_bestnav_ride_20260101_000000_report.txt")

    def test_unnamed_run_gets_a_numbered_name(self):
        run = self.store(name="")
        self.assertEqual(run["name"], f"Aprēķins #{run['id']}")

    def test_gnss_residual_ignores_rejected_points(self):
        metrics = fusion_runs.result_metrics(self.imu_dir, self.make_files())
        self.assertAlmostEqual(metrics["gnss_rms_m"], 1.0, places=1)  # every accepted point is 1 m east
        self.assertAlmostEqual(metrics["path_length_m"], 100.0, delta=12.0)

    def test_several_runs_for_same_recording_are_listed_newest_first(self):
        first = self.store("first")
        second = self.store("second", settings=())
        listed = fusion_runs.list_runs(self.imu_dir, "session", {})
        self.assertEqual([r["name"] for r in listed], ["second", "first"])
        self.assertEqual(first["id"] + 1, second["id"])

    def test_legacy_files_without_db_row_are_listed_read_only(self):
        write_csv(self.imu_dir / "kalman_fixed_old_ride.csv", [{"time": "t", "east_m": "0", "north_m": "0"}])
        listed = fusion_runs.list_runs(self.imu_dir, "session", {"fixed": "fixed_ppk"})
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0]["legacy"])
        self.assertEqual(listed[0]["source"], "fixed_ppk")

    def test_update_and_delete_remove_row_and_files(self):
        run = self.store()
        updated = fusion_db.update_run(run["id"], {"name": "renamed", "notes": "n", "kalman_file": "hack"})
        self.assertEqual((updated["name"], updated["notes"]), ("renamed", "n"))
        self.assertEqual(updated["kalman_file"], run["kalman_file"])  # only name/notes are editable
        removed = fusion_runs.delete_run_files(self.imu_dir, run)
        self.assertIn(run["kalman_file"], removed)
        self.assertTrue(fusion_db.delete_run(run["id"]))
        self.assertIsNone(fusion_db.get_run(run["id"]))

    def test_trajectory_is_thinned(self):
        data = fusion_runs.trajectory(self.imu_dir, self.make_files(), fused_limit=100)
        self.assertEqual(len(data["fused"]), 100)
        self.assertEqual(data["gnss"][5][2], "rejected")

    def test_trajectory_origin_is_recovered_from_any_row(self):
        origin = fusion_runs.trajectory(self.imu_dir, self.make_files())["origin"]
        self.assertAlmostEqual(origin[0], 56.0, places=6)
        self.assertAlmostEqual(origin[1], 24.0, places=6)

    def test_trajectory_origin_is_none_without_coordinates(self):
        write_csv(self.imu_dir / "kalman_fixed_old.csv", [{"time": "t", "east_m": "0", "north_m": "0"}])
        self.assertIsNone(fusion_runs.trajectory(self.imu_dir, "kalman_fixed_old.csv")["origin"])

    def test_trajectory_rejects_missing_file(self):
        with self.assertRaises(ValueError):
            fusion_runs.trajectory(self.imu_dir, "kalman_nothing.csv")


if __name__ == "__main__":
    unittest.main()
