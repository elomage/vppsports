import os
import numpy as np
import pandas as pd

from helper_functions import (
    RideDataLoader,
    scale_acc,
    detect_ride_start_x_axis,
    detect_ride_end,
    apply_savgol_axis,
    subtract_gyro_bias,
    estimate_gravity_robust,
    _log,

    auto_flip_signal, resample_signal,
)
from kalman_filter import apply_kalman_axis


def _apply_filter(signal, t, cfg):
    ftype = cfg.get("filter_type", "none")

    if ftype == "none":
        return signal

    if ftype == "kalman":
        return apply_kalman_axis(signal, t, cfg["q"], cfg["r"])

    if ftype == "savgol":
        return apply_savgol_axis(
            signal,
            cfg["savgol_window"],
            cfg["savgol_poly"]
        )

    return signal


def compute_filtered(acc, gyro=None, accel_filter=None, gyro_filter=None):
    if accel_filter is None:
        accel_filter = {"filter_type": "none"}
    if gyro_filter is None:
        gyro_filter = {"filter_type": "none"}

    t_acc = np.maximum.accumulate(np.array(acc[:, 0]))

    ax = scale_acc(acc[:, 1])
    ay = scale_acc(acc[:, 2])
    az = scale_acc(acc[:, 3])

    ax = _apply_filter(ax, t_acc, accel_filter)
    ay = _apply_filter(ay, t_acc, accel_filter)
    az = _apply_filter(az, t_acc, accel_filter)

    start_idx = detect_ride_start_x_axis(t_acc, ax)
    fs = 1.0 / np.mean(np.diff(t_acc))

    grav_x, grav_y, grav_z = estimate_gravity_robust(ax, ay, az, start_idx, fs)

    ax = ax - grav_x
    ay = ay - grav_y
    az = az - grav_z

    ax, ay, az, _ = auto_flip_signal(ax, ay, az)

    t_gyro = None
    gx = gy = gz = None

    if gyro is not None and len(gyro) > 0:
        t_gyro = np.maximum.accumulate(np.array(gyro[:, 0]))
        gx = _apply_filter(gyro[:, 1], t_gyro, gyro_filter)
        gy = _apply_filter(gyro[:, 2], t_gyro, gyro_filter)
        gz = _apply_filter(gyro[:, 3], t_gyro, gyro_filter)

        g_start = np.searchsorted(t_gyro, t_acc[start_idx])
        g_fs = 1.0 / np.mean(np.diff(t_gyro))
        gx, gy, gz = subtract_gyro_bias(gx, gy, gz, g_start, g_fs)

    mag = np.sqrt(ax**2 + ay**2 + az**2)

    return t_acc, ax, ay, az, t_gyro, gx, gy, gz


def detect_indices(t, ax, ay, az, tg, gx, gy, gz):
    start = detect_ride_start_x_axis(t, ax)
    end = detect_ride_end(t, az)

    return start, end


def trim_single_ride(
        acc,
        gyro=None,
        accel_params=None,
        gyro_params=None,
        resample_gyro_to_accel=True,
):
    t, ax, ay, az, tg, gx, gy, gz = compute_filtered(
        acc,
        gyro,
        accel_params,
        gyro_params
    )

    start, end = detect_indices(t, ax, ay, az, tg, gx, gy, gz)
    t_zero = t[start]

    acc_trim = np.column_stack([
        t[start:end] - t_zero,
        ax[start:end],
        ay[start:end],
        az[start:end]
    ])

    gyro_trim = None

    if gyro is not None and gx is not None:
        if resample_gyro_to_accel:
            t_target = t[start:end]
            gx_resampled = resample_signal(tg, gx, t_target)
            gy_resampled = resample_signal(tg, gy, t_target)
            gz_resampled = resample_signal(tg, gz, t_target)

            gyro_trim = np.column_stack([
                t_target - t_zero,
                gx_resampled,
                gy_resampled,
                gz_resampled
            ])
        else:
            g_start = np.searchsorted(tg, t[start], side="left")
            g_end = np.searchsorted(tg, t[end - 1], side="right")

            gyro_trim = np.column_stack([
                tg[g_start:g_end] - t_zero,
                gx[g_start:g_end],
                gy[g_start:g_end],
                gz[g_start:g_end]
            ])

    return acc_trim, gyro_trim


def process_directory(
        accel_dir,
        gyro_dir=None,
        output_dir="trimmed_rides",
        accel_params=None,
        gyro_params=None,
        save_gyro=True,
        progress_callback=None,
):
    base_out = os.path.join(output_dir, "trimmed_rides")
    accel_out = os.path.join(base_out, "accel")
    gyro_out = os.path.join(base_out, "gyro")

    os.makedirs(accel_out, exist_ok=True)
    os.makedirs(gyro_out, exist_ok=True)

    _log(f"[INFO] Output folder: {base_out}")

    acc_loader = RideDataLoader(accel_dir)
    acc_rides = dict(acc_loader.load_rides())

    gyro_rides = {}
    if gyro_dir is not None:
        gyro_loader = RideDataLoader(gyro_dir)
        gyro_rides = dict(gyro_loader.load_rides())

    all_keys = sorted(set(acc_rides.keys()) | set(gyro_rides.keys()))
    total = sum(1 for k in all_keys if acc_rides.get(k) is not None)

    _log(f"[INFO] Found {total} rides to process")

    processed = 0
    skipped = 0

    for idx, name in enumerate(all_keys, start=1):
        acc = acc_rides.get(name)
        gyro = gyro_rides.get(name)

        if acc is None:
            _log(f"[WARN] ({idx}/{len(all_keys)}) {name} — no accel data, skipping")
            skipped += 1
            continue

        _log(f"[INFO] ({idx}/{len(all_keys)}) Processing {name} ...")

        try:
            acc_trim, gyro_trim = trim_single_ride(
                acc,
                gyro,
                accel_params,
                gyro_params,
            )
        except Exception as e:
            _log(f"[ERROR] ({idx}/{len(all_keys)}) {name} — trimming failed: {e}")
            skipped += 1
            if progress_callback:
                progress_callback(idx, total)
            continue

        if acc_trim is None or len(acc_trim) == 0:
            _log(f"[WARN] ({idx}/{len(all_keys)}) {name} — trimmed result is empty, skipping")
            skipped += 1
            if progress_callback:
                progress_callback(idx, total)
            continue

        duration = acc_trim[-1, 0] - acc_trim[0, 0]

        try:
            pd.DataFrame(acc_trim, columns=["time", "ax", "ay", "az"]).to_csv(
                os.path.join(accel_out, f"{name}"),
                index=False,
                float_format="%.6f"
            )
        except Exception as e:
            _log(f"[ERROR] ({idx}/{len(all_keys)}) {name} — failed to save accel: {e}")
            skipped += 1
            if progress_callback:
                progress_callback(idx, total)
            continue

        gyro_saved = False
        if save_gyro and gyro_trim is not None and len(gyro_trim) > 0:
            try:
                pd.DataFrame(gyro_trim, columns=["time", "gx", "gy", "gz"]).to_csv(
                    os.path.join(gyro_out, f"{name}"),
                    index=False,
                    float_format="%.6f"
                )
                gyro_saved = True
            except Exception as e:
                _log(f"[WARN] ({idx}/{len(all_keys)}) {name} — failed to save gyro: {e}")

        gyro_note = " + gyro" if gyro_saved else ""
        _log(f"[OK]   ({idx}/{len(all_keys)}) {name} — {duration:.1f}s saved (accel{gyro_note})")

        processed += 1

        if progress_callback:
            progress_callback(processed + skipped, total)

    _log(f"[INFO] Done — {processed} saved, {skipped} skipped")
    return processed
