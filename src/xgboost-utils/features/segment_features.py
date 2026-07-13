import numpy as np
import pandas as pd

from .feature_utils import (
    count_wiggles,
    zero_cross_rate,
    jerk_rms,
    peak_shape,
    percentiles,
)


PHASE_BOUNDARIES = {
    "entry": (0.00, 0.30),
    "apex":  (0.30, 0.70),
    "exit":  (0.70, 1.00),
}


def _phase_slice(a_seg, phase):
    lo, hi = PHASE_BOUNDARIES[phase]
    n = len(a_seg)
    i_lo = int(np.floor(lo * n))
    i_hi = int(np.ceil(hi * n))
    i_hi = max(i_hi, i_lo + 2)
    i_hi = min(i_hi, n)
    return a_seg[i_lo:i_hi]


def _phase_features(a_seg, g_seg, phase, is_curve, curve_sign):
    sub = _phase_slice(a_seg, phase)
    if len(sub) < 3:
        return {}

    t = sub[:, 0]
    ax, ay, az = sub[:, 1], sub[:, 2], sub[:, 3]
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.01
    if is_curve:
        ay = ay * curve_sign

    g_lat_vert = np.sqrt(ay ** 2 + az ** 2)

    out = {
        f"{phase}_az_max": float(np.max(az)),
        f"{phase}_az_mean": float(np.mean(az)),
        f"{phase}_az_std": float(np.std(az)),
        f"{phase}_ay_abs_p95": float(np.percentile(np.abs(ay), 95)),
        f"{phase}_ay_signed_mean": float(np.mean(ay)),
        f"{phase}_ax_p95_abs": float(np.percentile(np.abs(ax), 95)),
        f"{phase}_ax_mean": float(np.mean(ax)),
        f"{phase}_ax_jerk_rms": jerk_rms(ax, dt),
        f"{phase}_ay_jerk_rms": jerk_rms(ay, dt),
        f"{phase}_ay_zero_cross_rate": zero_cross_rate(ay, dt),
        f"{phase}_g_lat_vert_p95": float(np.percentile(g_lat_vert, 95)),
    }

    if g_seg is not None and len(g_seg) >= 3:
        gt = g_seg[:, 0]
        t_start = sub[0, 0]
        t_end = sub[-1, 0]
        gmask = (gt >= t_start) & (gt <= t_end)
        g_sub = g_seg[gmask]
        if len(g_sub) >= 3:
            gx, gy, gz = g_sub[:, 1], g_sub[:, 2], g_sub[:, 3]
            if is_curve:
                gz = gz * curve_sign
            g_dt = float(np.median(np.diff(g_sub[:, 0])))
            g_mag = np.sqrt(gx ** 2 + gy ** 2 + gz ** 2)
            out.update({
                f"{phase}_gyro_mag_peak": float(np.max(g_mag)),
                f"{phase}_gyro_mag_mean": float(np.mean(g_mag)),
                f"{phase}_gyro_z_peak_abs": float(np.max(np.abs(gz))),
                f"{phase}_gyro_z_sign_flips_per_s": zero_cross_rate(gz, g_dt),
                f"{phase}_gyro_jerk_rms": jerk_rms(g_mag, g_dt),
            })

    return out


def build_segment_dataset(acc, gyro, seg_obj, ride_id):
    rows = []
    t_all = acc[:, 0]
    n_total = len(seg_obj.segments)
    ride_total_time = float(t_all[-1] - t_all[0]) if len(t_all) > 1 else 1.0

    for i, s in enumerate(seg_obj.segments):
        sl = slice(s.start_idx, min(s.end_idx + 1, len(acc)))
        a_seg = acc[sl]
        if len(a_seg) < 2:
            continue

        t_seg = a_seg[:, 0]
        ax, ay, az = a_seg[:, 1], a_seg[:, 2], a_seg[:, 3]
        dt = float(np.median(np.diff(t_seg))) if len(t_seg) > 1 else 0.01
        dur = float(s.duration) if s.duration > 0 else max(dt * len(t_seg), 1e-6)

        is_curve = "curve" in s.kind
        curve_sign = -1.0 if s.kind == "curve_r" else 1.0
        if is_curve:
            ay = ay * curve_sign

        az_p = percentiles(az)
        ay_abs_p = percentiles(np.abs(ay))
        ay_signed_p = percentiles(ay)
        peak_pos, peak_fwhm = peak_shape(az - np.min(az))
        g_total = np.sqrt(ax ** 2 + ay ** 2 + az ** 2)

        row = {
            "ride_id": ride_id,
            "seg_idx": i,
            "kind": s.kind,
            "is_curve": int(is_curve),
            "is_straight": int(s.kind == "straight"),
            "is_start": int(s.kind == "start"),

            "ride_position": i / max(n_total - 1, 1),
            "time_since_start": float(t_seg[0] - t_all[0]),
            "frac_ride_elapsed": float(t_seg[0] - t_all[0]) / ride_total_time,

            "duration": dur,

            "az_max": float(np.max(az)),
            "az_min": float(np.min(az)),
            "az_mean": float(np.mean(az)),
            "az_std": float(np.std(az)),
            "az_iqr": az_p["p75"] - az_p["p25"],
            "az_p95": az_p["p95"],
            "az_integral": float(np.trapezoid(np.maximum(az - np.median(az), 0), dx=dt)),

            "ay_abs_avg": float(np.mean(np.abs(ay))),
            "ay_abs_p95": ay_abs_p["p95"],
            "ay_signed_mean": float(np.mean(ay)),
            "ay_signed_p95": ay_signed_p["p95"],
            "ay_signed_min": float(np.min(ay)),
            "ay_inward_fraction": float(np.mean(ay > 0)) if is_curve else np.nan,
            "ay_zero_cross_rate": zero_cross_rate(ay, dt),

            "ax_std": float(np.std(ax)),
            "ax_p95_abs": float(np.percentile(np.abs(ax), 95)),
            "ax_zero_cross_rate": zero_cross_rate(ax, dt),

            "ax_jerk_rms": jerk_rms(ax, dt),
            "ay_jerk_rms": jerk_rms(ay, dt),
            "az_jerk_rms": jerk_rms(az, dt),

            "az_peak_position": peak_pos,
            "az_fwhm_ratio": peak_fwhm,

            "g_total_max": float(np.max(g_total)),
            "g_total_mean": float(np.mean(g_total)),
            "g_lat_vert_p95": float(np.percentile(np.sqrt(ay ** 2 + az ** 2), 95)),

            "wiggle_count": count_wiggles(ax),
        }

        g_seg_for_phases = None
        if gyro is not None:
            gmask = (gyro[:, 0] >= s.t_start) & (gyro[:, 0] <= s.t_end)
            g_seg = gyro[gmask]
            if len(g_seg) >= 2:
                g_seg_for_phases = g_seg
                gx, gy, gz = g_seg[:, 1], g_seg[:, 2], g_seg[:, 3]
                g_dt = float(np.median(np.diff(g_seg[:, 0])))
                if is_curve:
                    gz = gz * curve_sign
                g_mag = np.sqrt(gx ** 2 + gy ** 2 + gz ** 2)
                gz_int_signed = float(np.trapezoid(gz, dx=g_dt))
                gz_int_abs = float(np.trapezoid(np.abs(gz), dx=g_dt))
                clean_ratio = abs(gz_int_signed) / max(gz_int_abs, 1e-9)
                row.update({
                    "gyro_mag_peak": float(np.max(g_mag)),
                    "gyro_mag_mean": float(np.mean(g_mag)),
                    "gyro_mag_integral": float(np.trapezoid(g_mag, dx=g_dt)),
                    "gyro_z_peak_abs": float(np.max(np.abs(gz))),
                    "gyro_z_integral_abs": gz_int_abs,
                    "gyro_z_integral_signed": gz_int_signed,
                    "gyro_z_clean_ratio": clean_ratio,
                    "gyro_z_sign_flips_per_s": zero_cross_rate(gz, g_dt),
                    "gyro_x_peak_abs": float(np.max(np.abs(gx))),
                    "gyro_y_peak_abs": float(np.max(np.abs(gy))),
                    "gyro_jerk_rms": jerk_rms(g_mag, g_dt),
                })
            else:
                for k in ["gyro_mag_peak", "gyro_mag_mean", "gyro_mag_integral",
                          "gyro_z_peak_abs", "gyro_z_integral_abs", "gyro_z_integral_signed",
                          "gyro_z_clean_ratio", "gyro_z_sign_flips_per_s",
                          "gyro_x_peak_abs", "gyro_y_peak_abs", "gyro_jerk_rms"]:
                    row[k] = np.nan

        if is_curve and len(a_seg) >= 9:
            for phase in PHASE_BOUNDARIES:
                row.update(_phase_features(a_seg, g_seg_for_phases, phase, is_curve, curve_sign))

        rows.append(row)

    return pd.DataFrame(rows)