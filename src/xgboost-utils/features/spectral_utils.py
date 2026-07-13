from __future__ import annotations
import numpy as np
from scipy.signal import welch


SPECTRAL_BANDS = {
    "low": (0.5, 3.0),
    "mid": (3.0, 5.0),
    "high": (5.0, 15.0),
}


def _estimate_fs(t):
    if t is None or len(t) < 2:
        return None
    dt = np.diff(t)
    dt = dt[dt > 0]
    if len(dt) == 0:
        return None
    median_dt = float(np.median(dt))
    if median_dt <= 0:
        return None
    return 1.0 / median_dt


def _safe_welch(sig, fs):
    sig = np.asarray(sig, dtype=float)
    sig = sig[np.isfinite(sig)]
    if len(sig) < 16 or fs is None or fs <= 0:
        return None, None
    nperseg = min(len(sig), 128)
    try:
        f, pxx = welch(sig - sig.mean(), fs=fs, nperseg=nperseg)
        if pxx.sum() <= 0 or not np.isfinite(pxx).all():
            return None, None
        return f, pxx
    except Exception:
        return None, None


def spectral_stats(sig, t, prefix=""):
    fs = _estimate_fs(t)
    out = {
        f"{prefix}dom_freq": np.nan,
        f"{prefix}spectral_centroid": np.nan,
        f"{prefix}spectral_entropy": np.nan,
    }
    for band in SPECTRAL_BANDS:
        out[f"{prefix}band_{band}_energy"] = np.nan

    f, pxx = _safe_welch(sig, fs)
    if f is None:
        return out

    total_power = float(pxx.sum())
    if total_power <= 0:
        return out

    out[f"{prefix}dom_freq"] = float(f[int(np.argmax(pxx))])
    out[f"{prefix}spectral_centroid"] = float((f * pxx).sum() / total_power)

    pxx_norm = pxx / total_power
    pxx_norm = pxx_norm[pxx_norm > 0]
    out[f"{prefix}spectral_entropy"] = float(-(pxx_norm * np.log(pxx_norm)).sum())

    for band, (lo, hi) in SPECTRAL_BANDS.items():
        mask = (f >= lo) & (f < hi)
        out[f"{prefix}band_{band}_energy"] = float(pxx[mask].sum() / total_power)

    return out


def segment_spectral_features(acc, gyro, start_idx, end_idx):
    out = {}
    if acc is None or end_idx <= start_idx:
        return out

    t = acc[start_idx:end_idx, 0]
    ax, ay, az = acc[start_idx:end_idx, 1], acc[start_idx:end_idx, 2], acc[start_idx:end_idx, 3]
    a_mag = np.sqrt(ax ** 2 + ay ** 2 + az ** 2)

    out.update(spectral_stats(ax, t, prefix="ax_"))
    out.update(spectral_stats(ay, t, prefix="ay_"))
    out.update(spectral_stats(az, t, prefix="az_"))
    out.update(spectral_stats(a_mag, t, prefix="amag_"))

    if gyro is not None and len(gyro) >= end_idx and end_idx > start_idx:
        gz = gyro[start_idx:end_idx, 3]
        out.update(spectral_stats(gz, t, prefix="gz_"))

    return out