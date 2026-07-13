import pandas as pd
import numpy as np


CURVE_BASE_METRICS = [
    "az_max", "az_min", "az_mean", "az_std", "az_iqr", "az_p95",
    "ay_abs_avg", "ay_abs_p95", "ay_signed_mean", "ay_signed_p95",
    "ay_signed_min", "ay_inward_fraction", "ay_zero_cross_rate",
    "ax_std", "ax_p95_abs", "ax_zero_cross_rate",
    "ax_jerk_rms", "ay_jerk_rms", "az_jerk_rms",
    "az_peak_position", "az_fwhm_ratio",
    "g_total_max", "g_total_mean", "g_lat_vert_p95",
]

CURVE_GYRO_METRICS = [
    "gyro_mag_peak", "gyro_mag_mean",
    "gyro_z_peak_abs", "gyro_z_clean_ratio", "gyro_z_sign_flips_per_s",
    "gyro_x_peak_abs", "gyro_y_peak_abs", "gyro_jerk_rms",
]

PHASE_PREFIXES = ("entry_", "apex_", "exit_")

PHASE_METRICS_BASE = [
    "az_max", "az_mean", "az_std", "az_p95",
    "ay_abs_p95", "ay_zero_cross_rate",
    "ax_std", "ax_p95_abs",
    "ax_jerk_rms", "ay_jerk_rms", "az_jerk_rms",
    "g_total_max", "g_lat_vert_p95",
    "gyro_mag_mean", "gyro_mag_peak",
    "gyro_z_peak_abs", "gyro_z_sign_flips_per_s",
]

DURATION_DEPENDENT = {
    "az_integral", "wiggle_count",
    "gyro_mag_integral", "gyro_z_integral_abs", "gyro_z_integral_signed",
}

MIN_GROUP_SIZE_FOR_BUCKET_Z = 5


def build_curve_dataset(seg_df_all_rides, track_lookup):
    curves_only = seg_df_all_rides[
        seg_df_all_rides["kind"].astype(str).str.contains("curve")
    ].copy()
    if curves_only.empty:
        return pd.DataFrame()

    curves_only = curves_only.sort_values(["ride_id", "seg_idx"]).reset_index(drop=True)

    drop_cols = list(DURATION_DEPENDENT & set(curves_only.columns))
    for prefix in PHASE_PREFIXES:
        for col in curves_only.columns:
            if col.startswith(prefix):
                base = col[len(prefix):]
                if base in DURATION_DEPENDENT:
                    drop_cols.append(col)
    curves_only = curves_only.drop(columns=drop_cols, errors="ignore")

    prev_features = ["az_max", "ay_abs_p95", "ax_jerk_rms", "g_lat_vert_p95", "g_total_max"]
    if "gyro_z_clean_ratio" in curves_only.columns:
        prev_features.append("gyro_z_clean_ratio")

    grouped = seg_df_all_rides.sort_values(["ride_id", "seg_idx"]).groupby("ride_id")
    prev_rows = []
    for ride_id, g in grouped:
        g = g.reset_index(drop=True)
        prev_seg = None
        for _, row in g.iterrows():
            if "curve" in str(row["kind"]):
                entry = {"ride_id": ride_id, "seg_idx": row["seg_idx"]}
                prev_kind_str = "none"
                if prev_seg is not None:
                    prev_kind_str = str(prev_seg.get("kind", "none"))
                entry["prev_kind"] = prev_kind_str
                entry["prev_duration"] = (
                    prev_seg.get("duration", np.nan) if prev_seg is not None else np.nan
                )
                is_prev_curve = "curve" in prev_kind_str
                is_prev_straight = "straight" in prev_kind_str
                for f in prev_features:
                    val = prev_seg.get(f, np.nan) if prev_seg is not None else np.nan
                    entry[f"prev_straight_{f}"] = val if is_prev_straight else np.nan
                    entry[f"prev_curve_{f}"] = val if is_prev_curve else np.nan
                entry["prev_is_straight"] = int(is_prev_straight)
                entry["prev_is_curve"] = int(is_prev_curve)
                prev_rows.append(entry)
            prev_seg = row.to_dict()

    prev_df = pd.DataFrame(prev_rows)
    if not prev_df.empty:
        curves_only = curves_only.merge(prev_df, on=["ride_id", "seg_idx"], how="left")

    curves_only["track_id"] = curves_only["ride_id"].map(track_lookup)

    def _safe_z(series):
        s = series.std()
        if not np.isfinite(s) or s < 1e-9:
            return pd.Series(np.nan, index=series.index)
        return (series - series.mean()) / s

    bucket_sizes = curves_only.groupby(
        ["track_id"]
    )["duration"].transform("count")

    z_bucket = curves_only.groupby(
        ["track_id"]
    )["duration"].transform(_safe_z)

    z_track = curves_only.groupby("track_id")["duration"].transform(_safe_z)

    use_bucket = (bucket_sizes >= MIN_GROUP_SIZE_FOR_BUCKET_Z) & z_bucket.notna()
    curves_only["dur_z"] = np.where(use_bucket, z_bucket, z_track)
    curves_only["dur_z_source"] = np.where(use_bucket, "bucket", "track_fallback")

    return curves_only