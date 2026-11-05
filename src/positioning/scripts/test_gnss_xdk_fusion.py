import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from gnss_xdk_fusion import XdkFusionConfig, run_xdk_fusion
from imu_kalman import GnssSample
from xdk_imu import XdkData, find_offset, load_xdk

T0 = datetime(2026, 10, 21, 15, 0, 0, tzinfo=timezone.utc)
G = 9.80665
DURATION_S = 90.0
IMU_HZ = 200.0
GNSS_HZ = 2.0
XDK_START_S = 4.0  # the XDK clock starts this long after the first GNSS epoch
GYRO_BIAS = np.array([0.002, -0.004, 0.003])  # rad/s
ACC_BIAS = np.array([0.05, -0.03, 0.2])  # m/s^2


def truth(dt=0.005):
    """Stand still, drive a figure of S-curves, stop. Heading is clockwise from north."""
    t = np.arange(0.0, DURATION_S + dt, dt)
    speed = np.clip((t - 5.0) * 1.2, 0.0, 9.0) * np.clip((DURATION_S - 8.0 - t) * 0.8, 0.0, 1.0)
    yaw_rate = np.where(t > 12.0, 0.18 * np.sin(2 * math.pi * (t - 12.0) / 30.0), 0.0) * (speed > 1.0)
    heading = np.cumsum(yaw_rate) * dt
    east = np.cumsum(speed * np.sin(heading)) * dt
    north = np.cumsum(speed * np.cos(heading)) * dt
    return t, speed, yaw_rate, heading, east, north


def build(seed=3, pos_sigma=1.5):
    rng = np.random.default_rng(seed)
    t, speed, yaw_rate, heading, east, north = truth()
    accel_long = np.gradient(speed, t)
    # body axes: x forward, y left, z up; gyro z is counter-clockwise, so it is minus the heading rate
    gyro = np.column_stack([np.zeros_like(t), np.zeros_like(t), -yaw_rate]) + GYRO_BIAS
    acc = np.column_stack([accel_long, -speed * yaw_rate, np.full_like(t, G)]) + ACC_BIAS
    keep = (t >= XDK_START_S) & (np.arange(len(t)) % 1 == 0)
    xdk_t = t[keep] - XDK_START_S
    xdk = XdkData(
        name="synthetic",
        t=xdk_t,
        acc=acc[keep] + rng.normal(0, 0.05, (keep.sum(), 3)),
        gyro=gyro[keep] + rng.normal(0, 0.003, (keep.sum(), 3)),
        pressure_pa=np.zeros(keep.sum()),
    )
    points = []
    for gt in np.arange(0.0, DURATION_S, 1.0 / GNSS_HZ):
        i = int(round(gt / 0.005))
        h = heading[i]
        points.append(GnssSample(
            T0 + timedelta(seconds=float(gt)), 57.0, 24.0, 10.0,
            float(east[i] + rng.normal(0, pos_sigma)), float(north[i] + rng.normal(0, pos_sigma)),
            float(speed[i]), math.degrees(h) % 360.0,
            float(speed[i] * math.sin(h) + rng.normal(0, 0.05)), float(speed[i] * math.cos(h) + rng.normal(0, 0.05)),
            "SINGLE", None, 0.0,
        ))
    return xdk, points, (t, east, north)


class XdkFusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xdk, cls.points, cls.truth = build()
        cls.cfg = XdkFusionConfig.load(None, {"gnss_sigma_m": 1.5})

    def test_find_offset_recovers_clock_shift(self):
        found = find_offset(self.xdk, self.points)
        self.assertAlmostEqual(found.offset_s, XDK_START_S, delta=0.15)
        self.assertEqual(found.confidence, "high")

    def test_unrelated_ride_has_lower_correlation(self):
        other, _, _ = build(seed=9)
        other.gyro = other.gyro[::-1] * np.array([1.0, 1.0, 1.0])  # time-reversed turning: not the same ride
        self.assertLess(find_offset(other, self.points).correlation, find_offset(self.xdk, self.points).correlation)

    def test_fusion_tracks_truth_with_all_gnss(self):
        result = run_xdk_fusion(self.points, self.xdk, "bestnav", self.cfg, XDK_START_S)
        t, east, north = self.truth
        idx = np.array([int(round(((x - T0).total_seconds()) / 0.005)) for x in result.times])
        error = np.hypot(result.east - east[idx], result.north - north[idx])
        self.assertLess(float(np.sqrt(np.mean(error**2))), 1.2)
        self.assertEqual(result.info["gnss_rejected"], 0)

    def test_gyro_carries_the_track_through_an_outage(self):
        outage = [(30.0, 55.0)]
        fused = run_xdk_fusion(self.points, self.xdk, "bestnav", self.cfg, XDK_START_S, outage)
        baseline = run_xdk_fusion(self.points, self.xdk, "bestnav", self.cfg, XDK_START_S, outage, use_imu=False)
        self.assertGreater(fused.info["outage_points"], 40)
        self.assertLess(fused.info["outage_rmse_m"], 0.35 * baseline.info["outage_rmse_m"])
        self.assertLess(fused.info["outage_rmse_m"], 12.0)

    def test_outlier_is_rejected(self):
        points = list(self.points)
        bad = points[100]
        points[100] = GnssSample(bad.time, bad.lat, bad.lon, bad.height, bad.east + 40.0, bad.north - 30.0,
                                 bad.speed_mps, bad.heading_deg, bad.ve_mps, bad.vn_mps, bad.position_type, None, 0.0)
        result = run_xdk_fusion(points, self.xdk, "bestnav", self.cfg, XDK_START_S)
        self.assertGreaterEqual(result.info["gnss_rejected"], 1)


class XdkSmootherAndStationaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xdk, cls.points, cls.truth = build()
        cls.cfg = XdkFusionConfig.load(None, {"gnss_sigma_m": 1.5})

    def _rmse(self, result):
        t, east, north = self.truth
        idx = np.array([int(round(((x - T0).total_seconds()) / 0.005)) for x in result.times])
        return float(np.sqrt(np.mean(np.hypot(result.east - east[idx], result.north - north[idx]) ** 2)))

    def test_rts_is_at_least_as_good_as_the_forward_filter(self):
        forward = run_xdk_fusion(self.points, self.xdk, "bestnav", self.cfg, XDK_START_S)
        smoothed = run_xdk_fusion(self.points, self.xdk, "bestnav", self.cfg, XDK_START_S, smooth=True)
        self.assertEqual(len(forward.times), len(smoothed.times))
        self.assertLessEqual(self._rmse(smoothed), self._rmse(forward) * 1.02)
        self.assertTrue(smoothed.info["smoothed"])

    def test_rts_does_not_move_a_gnss_less_start_of_the_track_far(self):
        outage = [(30.0, 55.0)]
        forward = run_xdk_fusion(self.points, self.xdk, "bestnav", self.cfg, XDK_START_S, outage)
        smoothed = run_xdk_fusion(self.points, self.xdk, "bestnav", self.cfg, XDK_START_S, outage, smooth=True)
        self.assertLessEqual(smoothed.info["outage_smoothed_rmse_m"], forward.info["outage_rmse_m"] * 1.05)

    def test_vertical_outlier_keeps_the_horizontal_fix(self):
        points = list(self.points)
        bad = points[100]
        points[100] = GnssSample(bad.time, bad.lat, bad.lon, bad.height + 60.0, bad.east, bad.north,
                                 bad.speed_mps, bad.heading_deg, bad.ve_mps, bad.vn_mps, bad.position_type, None, 0.0)
        before = run_xdk_fusion(self.points, self.xdk, "bestnav", self.cfg, XDK_START_S)
        after = run_xdk_fusion(points, self.xdk, "bestnav", self.cfg, XDK_START_S)
        self.assertEqual(after.info["gnss_rejected"], before.info["gnss_rejected"])

    def test_stationary_recording_runs_and_stays_put(self):
        rng = np.random.default_rng(5)
        n = int(60 * IMU_HZ)
        t = np.arange(n) / IMU_HZ
        xdk = XdkData(
            name="still", t=t,
            acc=np.column_stack([np.zeros(n), np.zeros(n), np.full(n, G)]) + ACC_BIAS + rng.normal(0, 0.05, (n, 3)),
            gyro=np.zeros((n, 3)) + GYRO_BIAS + rng.normal(0, 0.003, (n, 3)),
            pressure_pa=np.zeros(n),
        )
        points = [
            GnssSample(T0 + timedelta(seconds=float(gt)), 57.0, 24.0, 10.0,
                       float(rng.normal(0, 1.5)), float(rng.normal(0, 1.5)), 0.0, 0.0,
                       float(rng.normal(0, 0.1)), float(rng.normal(0, 0.1)), "SINGLE", None, 0.0)
            for gt in np.arange(0.0, 60.0, 0.5)
        ]
        cfg = XdkFusionConfig.load(None, {"gnss_sigma_m": 1.5, "assume_stationary": True})
        result = run_xdk_fusion(points, xdk, "bestnav", cfg, 0.0, smooth=True)
        self.assertTrue(result.info["stationary"])
        self.assertGreater(result.zupt.sum(), 100)
        # the GNSS scatter is 1.5 m per axis; a filter that knows it is standing still averages it down
        self.assertLess(float(np.sqrt(np.mean(result.east**2 + result.north**2))), 1.0)
        self.assertLess(float(np.sqrt(np.mean(result.ve**2 + result.vn**2))), 0.1)


class XdkLoaderTests(unittest.TestCase):
    def test_units_and_stale_rows(self):
        text = "\n".join([
            "t_ms,ax,ay,az,gx,gy,gz,mx,my,mz,mag_r,temp_mC,press_Pa,hum_pct,light_mlux,batt_mV",
            "100,0,0,1000,610,0,0,0,0,0,0,0,0,0,0,0",
            "101,0,0,1000,610,0,0,0,0,0,0,0,0,0,0,0",  # stale repeat of the previous sample
            "105,500,0,1000,0,0,-1000,0,0,0,0,0,102000,0,0,0",
            "105,9,9,9,9,9,9,0,0,0,0,0,0,0,0,0",  # repeated timestamp
        ])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "LOG_001.CSV"
            path.write_text(text, encoding="utf-8")
            xdk = load_xdk(path)
        self.assertEqual(len(xdk.t), 2)
        self.assertAlmostEqual(xdk.acc[0, 2], G, places=4)
        self.assertAlmostEqual(xdk.acc[1, 0], 0.5 * G, places=4)
        self.assertAlmostEqual(math.degrees(xdk.gyro[0, 0]), 0.61, places=4)
        self.assertAlmostEqual(math.degrees(xdk.gyro[1, 2]), -1.0, places=4)
        self.assertAlmostEqual(xdk.duration_s, 0.005, places=6)


if __name__ == "__main__":
    unittest.main()
