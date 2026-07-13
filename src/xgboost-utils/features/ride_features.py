import pandas as pd
import numpy as np
from .feature_utils import safe
from .features_naming import FEATURE_FULL_NAMES, FEATURE_FULL_NAMES_LV, PREFIX_NAMES_LV, STAT_NAMES_LV


def map_name(prefix, metric, stat="", lang="lv"):
    if lang == "lv":
        p_label = PREFIX_NAMES_LV.get(prefix, prefix.replace("_", " ").title())
        m_label = FEATURE_FULL_NAMES_LV.get(metric, metric)
        s_label = f" ({STAT_NAMES_LV.get(stat, stat)})" if stat else ""
    else:
        p_label = prefix.replace("_", " ").title()
        m_label = FEATURE_FULL_NAMES.get(metric, metric)
        s_label = f" ({stat.title()})" if stat else ""

    return f"{p_label}: {m_label}{s_label}"


def _one_stat(df, metric, prefix, stat):
    if len(df) == 0 or metric not in df.columns:
        return {map_name(prefix, metric, stat): np.nan}
    s = df[metric].dropna()
    if len(s) == 0:
        return {map_name(prefix, metric, stat): np.nan}
    if stat == "mean":
        val = float(s.mean())
    elif stat == "p90":
        val = float(s.quantile(0.90))
    elif stat == "max":
        val = float(s.max())
    elif stat == "std":
        val = float(s.std()) if len(s) > 1 else 0.0
    else:
        val = np.nan
    return {map_name(prefix, metric, stat): val}


def _safe_get(seg, key):
    if seg is None or key not in seg or pd.isna(seg[key]):
        return None
    return seg[key]


def _estimate_dt(arr):
    if arr is None or len(arr) < 2:
        return None
    diffs = np.diff(arr[:, 0])
    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return None
    return float(np.median(diffs))


def _ride_wide_signal_features(acc, gyro):
    feats = {}
    if acc is None or len(acc) < 10:
        return feats

    ax, ay, az = acc[:, 1], acc[:, 2], acc[:, 3]
    g_mag = np.sqrt(ax ** 2 + ay ** 2 + az ** 2)

    feats["Ride: g_mag Mean"] = float(np.mean(g_mag))
    feats["Ride: g_mag P95"] = float(np.percentile(g_mag, 95))
    feats["Ride: g_mag Max"] = float(np.max(g_mag))
    feats["Ride: az Mean"] = float(np.mean(az))
    feats["Ride: az P95"] = float(np.percentile(az, 95))
    feats["Ride: ax Mean"] = float(np.mean(ax))
    feats["Ride: ax Abs Mean"] = float(np.mean(np.abs(ax)))
    feats["Ride: ay Abs P95"] = float(np.percentile(np.abs(ay), 95))

    half = len(ax) // 2
    quarter = len(ax) // 4
    feats["Ride: ax First Half Sum"] = float(np.sum(ax[:half]))
    feats["Ride: ax First Quarter Mean"] = float(np.mean(ax[:quarter])) if quarter else np.nan

    dt = _estimate_dt(acc)
    if dt is not None and dt > 0:
        jerk = np.diff(ax) / dt
        feats["Ride: Jerk RMS"] = float(np.sqrt(np.mean(jerk ** 2)))
    else:
        feats["Ride: Jerk RMS"] = np.nan

    if gyro is not None and len(gyro) > 10:
        gz = gyro[:, 3]
        feats["Ride: gz Abs Mean"] = float(np.mean(np.abs(gz)))
        feats["Ride: gz P95 Abs"] = float(np.percentile(np.abs(gz), 95))
        gyro_dt = _estimate_dt(gyro) or dt
        if gyro_dt and gyro_dt > 0:
            sign_flips = int(np.sum(np.diff(np.sign(gz)) != 0))
            feats["Ride: gz Sign Flips Per S"] = float(sign_flips / (len(gz) * gyro_dt))
        else:
            feats["Ride: gz Sign Flips Per S"] = np.nan

    return feats


def build_ride_dataset(seg_df, total_time, ride_id, acc=None, gyro=None):
    if (seg_df is None or len(seg_df) == 0) and acc is None:
        return pd.DataFrame()

    ride_row = {
        "ride_id": ride_id,
        "target_time": total_time,
    }

    ride_row.update(_ride_wide_signal_features(acc, gyro))

    if seg_df is not None and len(seg_df) > 0:
        curves = seg_df[seg_df["kind"].str.contains("curve")].copy()
        straights = seg_df[seg_df["kind"] == "straight"]
        start_rows = seg_df[seg_df["kind"] == "start"]
        start_seg = start_rows.iloc[0] if len(start_rows) else None

        ride_row["Start: Push Impulse"] = safe(_safe_get(start_seg, "ax_p95_abs"))

        ride_row.update(_one_stat(curves, "ay_abs_p95", "curve", "p90"))
        ride_row.update(_one_stat(curves, "ax_jerk_rms", "curve", "mean"))

        if "gyro_z_sign_flips_per_s" in curves.columns and len(curves):
            ride_row["Curve: Steering Wobble Rate"] = float(
                curves["gyro_z_sign_flips_per_s"].mean()
            )
        else:
            ride_row["Curve: Steering Wobble Rate"] = np.nan

        if "gyro_z_sign_flips_per_s" in straights.columns and len(straights):
            ride_row["Straight: Steering Wobble Rate"] = float(
                straights["gyro_z_sign_flips_per_s"].mean()
            )
        else:
            ride_row["Straight: Steering Wobble Rate"] = np.nan

        if "ay_abs_p95" in curves.columns and len(curves) >= 2:
            ride_row["Curve: Lateral Load Consistency"] = float(curves["ay_abs_p95"].std())
        else:
            ride_row["Curve: Lateral Load Consistency"] = np.nan

        if "ax_jerk_rms" in curves.columns and "ax_jerk_rms" in straights.columns \
                and len(curves) and len(straights):
            ride_row["Overall: Curve vs Straight Jerk Gap"] = (
                    float(curves["ax_jerk_rms"].mean()) - float(straights["ax_jerk_rms"].mean())
            )
        else:
            ride_row["Overall: Curve vs Straight Jerk Gap"] = np.nan

    return pd.DataFrame([ride_row])