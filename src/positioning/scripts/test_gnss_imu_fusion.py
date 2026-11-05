import math
import unittest
from datetime import datetime, timedelta, timezone

import numpy as np

from gnss_imu_fusion import G0, FusionConfig, parse_outages, run_fusion, scan_alignment
from imu_kalman import GnssSample, ImuSample

T0 = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
STATIC_S = 3.0
DURATION_S = 40.0
GNSS_HZ = 10.0
IMU_HZ = 200.0
BIAS = 0.1


def truth(t: float):
    """Stand still for STATIC_S, then accelerate with a speed ripple on a slowly curving path."""
    moving = max(0.0, t - STATIC_S)
    speed = 0.0 if t < STATIC_S else min(6.0, 1.5 * moving) + 1.5 * math.sin(0.4 * moving)
    return speed, 0.04 * moving


def make_track(dt=0.001):
    times = np.arange(0.0, DURATION_S + dt, dt)
    east = np.zeros_like(times)
    north = np.zeros_like(times)
    speed = np.zeros_like(times)
    heading = np.zeros_like(times)
    for i in range(1, len(times)):
        speed[i], heading[i] = truth(times[i])
        east[i] = east[i - 1] + speed[i] * math.sin(heading[i]) * dt
        north[i] = north[i - 1] + speed[i] * math.cos(heading[i]) * dt
    return times, east, north, speed, heading


def build(seed=1, outliers=(), sigma=0.05, hill=0.0):
    rng = np.random.default_rng(seed)
    times, east, north, speed, heading = make_track()
    accel = np.gradient(speed, times)
    path = np.cumsum(speed) * 0.001
    # Rolling terrain: height = hill * sin(path / 40); gradient = hill / 40 * cos(path / 40).
    height = 10.0 + hill * np.sin(path / 40.0)
    grade = (hill / 40.0) * np.cos(path / 40.0)
    sin_pitch = grade / np.sqrt(1.0 + grade * grade)
    points = []
    gnss_t = np.arange(0.0, DURATION_S, 1.0 / GNSS_HZ)
    truth_at = {}
    for index, t in enumerate(gnss_t):
        i = int(round(t / 0.001))
        e, n = east[i] + rng.normal(0, sigma), north[i] + rng.normal(0, sigma)
        if index in outliers:
            e += 12.0
            n -= 9.0
        truth_at[index] = (east[i], north[i])
        points.append(GnssSample(
            T0 + timedelta(seconds=float(t)), 57.0, 24.0, float(height[i]) + rng.normal(0, 0.02), e, n,
            float(speed[i]), math.degrees(heading[i]) % 360.0,
        ))
    samples = []
    for t in np.arange(0.0, DURATION_S, 1.0 / IMU_HZ):
        i = int(round(t / 0.001))
        lateral = speed[i] * 0.04 * math.cos(0.0)
        s = ImuSample(
            float(t),
            float(accel[i] + BIAS + (G0 * sin_pitch[i] if speed[i] > 0 else 0.0) + rng.normal(0, 0.05)),
            float(lateral + rng.normal(0, 0.05)),
            float(9.80665 + rng.normal(0, 0.05)),
            T0 + timedelta(seconds=float(t)),
        )
        samples.append(s)
    return points, samples, truth_at, (times, east, north)


def error_series(result, times, east, north):
    errs = []
    for k, time in enumerate(result.times):
        i = min(len(times) - 1, int(round((time - T0).total_seconds() / 0.001)))
        errs.append(math.hypot(result.east[k] - east[i], result.north[k] - north[i]))
    return np.array(errs)


class FusionTests(unittest.TestCase):
    def test_outliers_are_rejected_and_trajectory_stays_accurate(self):
        outliers = {80, 81, 150, 220, 300}
        points, samples, _, (times, east, north) = build(outliers=outliers)
        cfg = FusionConfig(gnss_sigma_m=0.05)
        result = run_fusion(points, samples, "fixed_ppk", cfg)
        self.assertGreaterEqual(result.info["gnss_rejected"], len(outliers))
        errors = error_series(result, times, east, north)
        self.assertLess(float(np.sqrt(np.mean(errors**2))), 0.15)
        self.assertLess(float(errors.max()), 0.6)

    def test_outage_error_is_reported_and_bounded(self):
        points, samples, _, _ = build()
        cfg = FusionConfig(gnss_sigma_m=0.05)
        result = run_fusion(points, samples, "fixed_ppk", cfg, outages=[(15.0, 20.0)])
        self.assertGreater(result.info["outage_points"], 40)
        self.assertLess(result.info["outage_rmse_m"], 1.5)

    def test_imu_beats_gnss_only_during_outage(self):
        points, samples, _, _ = build()
        with_imu = run_fusion(points, samples, "fixed_ppk", FusionConfig(gnss_sigma_m=0.05), outages=[(15.0, 20.0)])
        # Same filter with a useless IMU (accelerometer says "no acceleration").
        flat = [ImuSample(s.seconds, 0.0, 0.0, 9.80665, s.time) for s in samples]
        without_imu = run_fusion(points, flat, "fixed_ppk", FusionConfig(gnss_sigma_m=0.05), outages=[(15.0, 20.0)])
        self.assertLess(with_imu.info["outage_rmse_m"], without_imu.info["outage_rmse_m"])

    def test_slope_compensation_removes_gravity_from_forward_accel(self):
        points, samples, _, _ = build(hill=10.0)
        axis = {"forward_axis": [1.0, 0.0, 0.0]}
        on = run_fusion(points, samples, "fixed_ppk", FusionConfig(gnss_sigma_m=0.05, **axis), outages=[(15.0, 20.0)])
        off = run_fusion(points, samples, "fixed_ppk", FusionConfig(gnss_sigma_m=0.05, slope_compensation=False, **axis), outages=[(15.0, 20.0)])
        self.assertLess(on.info["outage_rmse_m"], 1.0)
        self.assertLess(on.info["outage_rmse_m"], off.info["outage_rmse_m"])

    def test_unrelated_imu_is_ignored_and_result_stays_gnss_accurate(self):
        points, samples, _, (times, east, north) = build()
        rng = np.random.default_rng(7)
        junk = [ImuSample(x.seconds, float(rng.normal(0, 2.0)), float(rng.normal(0, 2.0)), 9.80665, x.time) for x in samples]
        result = run_fusion(points, junk, "fixed_ppk", FusionConfig(gnss_sigma_m=0.05))
        self.assertEqual(result.info["imu_used"], 0)
        self.assertLess(float(np.sqrt(np.mean(error_series(result, times, east, north) ** 2))), 0.3)

    def test_forward_axis_is_estimated(self):
        points, samples, _, _ = build()
        result = run_fusion(points, samples, "fixed_ppk", FusionConfig(gnss_sigma_m=0.05))
        axis = [float(v) for v in result.info["forward_axis"].split(",")]
        self.assertGreater(axis[0], 0.9)
        self.assertGreater(float(result.info["forward_axis_r2"]), 0.3)

    def test_zupt_holds_velocity_at_zero_while_static(self):
        points, samples, _, _ = build()
        result = run_fusion(points, samples, "fixed_ppk", FusionConfig(gnss_sigma_m=0.05))
        static_rows = [i for i, t in enumerate(result.times) if 0.5 < (t - T0).total_seconds() < STATIC_S - 0.5]
        self.assertGreater(len(static_rows), 50)
        self.assertTrue(result.zupt[static_rows].all())
        self.assertLess(float(np.max(np.hypot(result.ve[static_rows], result.vn[static_rows]))), 0.05)

    def test_bias_state_converges(self):
        # With a known axis the bias state is purely the accelerometer offset (an estimated axis also
        # folds its small residual gravity leakage into the bias).
        points, samples, _, _ = build()
        result = run_fusion(points, samples, "fixed_ppk", FusionConfig(gnss_sigma_m=0.05, forward_axis=[1.0, 0.0, 0.0]))
        self.assertLess(abs(float(np.median(result.bias[len(result.bias) // 2:])) - BIAS), 0.08)

    def test_manual_forward_axis_is_used(self):
        points, samples, _, _ = build()
        cfg = FusionConfig(gnss_sigma_m=0.05, forward_axis=[2.0, 0.0, 0.0])
        result = run_fusion(points, samples, "fixed_ppk", cfg)
        self.assertEqual(result.info["forward_axis"], "1.0000,0.0000,0.0000")
        self.assertEqual(result.info["forward_axis_r2"], "")


class AlignmentScanTests(unittest.TestCase):
    def test_scan_finds_known_offset(self):
        points, samples, _, _ = build()
        shifted = [ImuSample(x.seconds + 7.0, x.ax_mps2, x.ay_mps2, x.az_mps2) for x in samples]
        result = scan_alignment(points, shifted, min_overlap_s=20.0)
        best = result["peaks"][0]
        self.assertAlmostEqual(best["offset_s"], -7.0, delta=0.3)
        self.assertGreater(best["axis"][0], 0.9)
        self.assertGreater(best["score"], 0.9)

    def test_scan_on_unrelated_imu_scores_low(self):
        points, samples, _, _ = build()
        rng = np.random.default_rng(3)
        junk = [ImuSample(x.seconds, float(rng.normal(0, 1)), float(rng.normal(0, 1)), 9.80665) for x in samples]
        self.assertLess(scan_alignment(points, junk, min_overlap_s=20.0)["peaks"][0]["score"], 0.3)


class ConfigTests(unittest.TestCase):
    def test_overrides_beat_file_and_none_is_ignored(self):
        cfg = FusionConfig.load(None, {"gnss_sigma_m": 0.2, "outlier_gate_sigma": None, "unknown_key": 1})
        self.assertEqual(cfg.gnss_sigma_m, 0.2)
        self.assertEqual(cfg.outlier_gate_sigma, 3.5)

    def test_sigma_priority(self):
        cfg = FusionConfig(gnss_sigma_by_position_type={"SINGLE": 2.5})
        self.assertEqual(cfg.sigma_for("fixed_ppk", None, None), 0.05)
        self.assertEqual(cfg.sigma_for("bestnav", "single", None), 2.5)
        self.assertEqual(cfg.sigma_for("bestnav", "SINGLE", 0.7), 0.7)
        cfg.gnss_sigma_m = 0.4
        self.assertEqual(cfg.sigma_for("bestnav", "SINGLE", 0.7), 0.4)

    def test_parse_outages(self):
        self.assertEqual(parse_outages(["10:15", "20.5:22"]), [(10.0, 15.0), (20.5, 22.0)])
        with self.assertRaises(SystemExit):
            parse_outages(["5:5"])
        with self.assertRaises(SystemExit):
            parse_outages(["abc"])


if __name__ == "__main__":
    unittest.main()
