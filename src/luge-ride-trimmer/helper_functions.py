import os

from scipy.interpolate import interp1d
from scipy.signal import savgol_filter

SENSOR_SCALE = 19.5 / 1_000_000.0

_log_callback = None


def set_log_callback(fn):
    global _log_callback
    _log_callback = fn


def _log(msg):
    if _log_callback is not None:
        _log_callback(msg)
    else:
        print(msg)


def _load_single_file(filepath):
    data = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) != 4:
                    continue
                try:
                    timestamp, x, y, z = map(float, parts)
                    data.append([timestamp, x, y, z])
                except ValueError:
                    continue
    except IOError as e:
        _log(f"[ERROR] Could not read file {filepath}: {e}")
        return None

    if len(data) == 0:
        _log(f"[WARN] File is empty or has no valid rows: {os.path.basename(filepath)}")
        return None

    return np.array(data)


class RideDataLoader:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.rides = []

    def load_rides(self):
        rides = []

        if not os.path.isdir(self.data_dir):
            _log(f"[ERROR] Directory not found: {self.data_dir}")
            self.rides = rides
            return rides

        files = sorted(os.listdir(self.data_dir))
        txt_files = [f for f in files if f.endswith(".txt")]

        if not txt_files:
            _log(f"[WARN] No .txt files found in: {self.data_dir}")
            self.rides = rides
            return rides

        for filename in txt_files:
            filepath = os.path.join(self.data_dir, filename)
            ride_data = _load_single_file(filepath)

            if ride_data is not None:
                rides.append((filename, ride_data))
            else:
                _log(f"[WARN] Skipping {filename} — no valid data")

        _log(f"[INFO] Loaded {len(rides)} / {len(txt_files)} rides from {os.path.basename(self.data_dir)}")
        self.rides = rides
        return rides


def scale_acc(raw_acc, threshold=100.0):
    raw_acc = np.asarray(raw_acc)

    if np.max(np.abs(raw_acc)) < threshold:
        return raw_acc
    return raw_acc * SENSOR_SCALE


def prepare_time(t):
    t = t.copy()

    if np.max(t) > 1e6:
        t = t / 1_000_000.0

    t = t - t[0]
    t = np.maximum.accumulate(t)

    return t


def rms(x):
    return np.sqrt(np.mean(x ** 2))


def detect_ride_start_x_axis(t, ax, window_sec=0.5):
    dt = np.diff(t)
    dt[dt <= 0] = np.mean(dt)

    jerk_x = np.diff(ax) / dt
    mean_dt = np.mean(dt)

    window_size = max(5, int(window_sec / mean_dt))

    if window_size >= len(ax):
        return 0

    var_signal = np.array([
        np.var(ax[i:i + window_size])
        for i in range(len(ax) - window_size)
    ])

    jerk_energy = np.array([
        np.mean(np.abs(jerk_x[i:i + window_size]))
        for i in range(len(jerk_x) - window_size)
    ])

    min_len = min(len(var_signal), len(jerk_energy))
    combined = var_signal[:min_len] + jerk_energy[:min_len]

    indices = np.where(combined > np.percentile(combined, 90))[0]

    return indices[0] if len(indices) > 0 else 0


import numpy as np

def detect_ride_end(
        t, az,
        min_run_duration=40.0,
        curve_threshold=0.8,
        finish_buffer=0.5
):
    t = np.asarray(t, dtype=float)
    az_abs = np.abs(np.asarray(az, dtype=float))
    n = len(t)
    fs = 1.0 / np.median(np.diff(t))

    w = max(2, int(0.2 * fs))
    az_s = np.convolve(az_abs, np.ones(w)/w, mode='same')

    search_start = int(min_run_duration * fs)
    high_g_indices = np.where(az_s[search_start:] > curve_threshold)[0]

    if len(high_g_indices) == 0:
        high_g_indices = np.where(az_s[search_start:] > 1.0)[0]
        if len(high_g_indices) == 0:
            return n - 1

    last_peak_idx = high_g_indices[-1] + search_start

    precise_exit = last_peak_idx
    for i in range(last_peak_idx, n):
        if az_s[i] < 0.4:
            precise_exit = i
            break

    final_idx = precise_exit + int(finish_buffer * fs)

    return int(np.clip(final_idx, 0, n - 1))


def resample_signal(t_src, signal, t_target):
    if len(t_src) < 2:
        return np.zeros_like(t_target)

    f = interp1d(t_src, signal, bounds_error=False, fill_value="extrapolate")
    return f(t_target)


def apply_savgol_axis(signal, window=11, poly=3):
    signal = np.asarray(signal)

    if len(signal) < window:
        return signal

    if window % 2 == 0:
        window += 1

    if window >= len(signal):
        return signal

    return savgol_filter(signal, window_length=window, polyorder=poly, mode='interp')


def normalize_ride_axes(ax, ay, az, pre_slice):
    ax = np.asarray(ax, dtype=float)
    ay = np.asarray(ay, dtype=float)
    az = np.asarray(az, dtype=float)

    grav_x = np.median(ax[pre_slice])
    grav_y = np.median(ay[pre_slice])
    grav_z = np.median(az[pre_slice])

    ax_norm = ax - grav_x
    ay_norm = ay - grav_y
    az_norm = az - grav_z
    grav_mag = np.sqrt(grav_x ** 2 + grav_y ** 2 + grav_z ** 2)

    if grav_mag > 0.1:
        ax_norm /= grav_mag
        ay_norm /= grav_mag
        az_norm /= grav_mag

    return ax_norm, ay_norm, az_norm, grav_mag


def normalize_gyro(gx, gy, gz, pre_slice):
    gx = np.asarray(gx, dtype=float)
    gy = np.asarray(gy, dtype=float)
    gz = np.asarray(gz, dtype=float)

    gx_bias = np.median(gx[pre_slice])
    gy_bias = np.median(gy[pre_slice])
    gz_bias = np.median(gz[pre_slice])

    return gx - gx_bias, gy - gy_bias, gz - gz_bias

def auto_flip_signal(ax, ay, az):
    ax = np.asarray(ax, dtype=float)
    ay = np.asarray(ay, dtype=float)
    az = np.asarray(az, dtype=float)

    baseline_z = np.median(az)
    max_deviation_z = np.max(az) - baseline_z
    min_deviation_z = baseline_z - np.min(az)

    if min_deviation_z > max_deviation_z:
        return ax * -1.0, ay * -1.0, az * -1.0, True

    return ax, ay, az, False

def estimate_gravity_robust(ax, ay, az, start_idx, fs,
                            search_window_sec=30.0,
                            sub_window_sec=2.0,
                            grav_min=0.85, grav_max=1.15):
    search_samples = int(search_window_sec * fs)
    sub_samples = int(sub_window_sec * fs)

    search_start = max(0, start_idx - search_samples)
    search_end = start_idx

    if search_end - search_start < sub_samples:
        gx = np.median(ax[:start_idx]) if start_idx > 0 else 0.0
        gy = np.median(ay[:start_idx]) if start_idx > 0 else 0.0
        gz = np.median(az[:start_idx]) if start_idx > 0 else 1.0
        return gx, gy, gz

    candidates = []
    step = max(1, sub_samples // 4)

    for i in range(search_start, search_end - sub_samples, step):
        s = slice(i, i + sub_samples)
        var = np.var(ax[s]) + np.var(ay[s]) + np.var(az[s])
        gx = np.median(ax[s])
        gy = np.median(ay[s])
        gz = np.median(az[s])
        mag = np.sqrt(gx*gx + gy*gy + gz*gz)
        candidates.append((var, mag, gx, gy, gz))

    valid = [c for c in candidates if grav_min <= c[1] <= grav_max]

    if valid:
        valid.sort(key=lambda c: c[0])
        _, mag, gx, gy, gz = valid[0]
        _log(f"[INFO] Gravitācija atrasta no fizikāli ticama loga: {mag:.3f}g")
        return gx, gy, gz

    candidates.sort(key=lambda c: c[0])
    _, mag, gx, gy, gz = candidates[0]
    _log(f"[WARN] Neviens logs ar gravitāciju 0.85–1.15g robežās; "
         f"izmantots zemākās dispersijas logs (mag={mag:.3f}g). "
         f"Brauciens var būt nepareizi mērogots.")
    return gx, gy, gz


def subtract_gyro_bias(gx, gy, gz, start_idx, fs,
                       search_window_sec=30.0, sub_window_sec=2.0):
    search_samples = int(search_window_sec * fs)
    sub_samples = int(sub_window_sec * fs)

    search_start = max(0, start_idx - search_samples)
    search_end = start_idx

    if search_end - search_start < sub_samples:
        bx = np.median(gx[:start_idx]) if start_idx > 0 else 0.0
        by = np.median(gy[:start_idx]) if start_idx > 0 else 0.0
        bz = np.median(gz[:start_idx]) if start_idx > 0 else 0.0
        return gx - bx, gy - by, gz - bz

    best_var = np.inf
    best_slice = slice(search_start, search_start + sub_samples)
    step = max(1, sub_samples // 4)

    for i in range(search_start, search_end - sub_samples, step):
        s = slice(i, i + sub_samples)
        var = np.var(gx[s]) + np.var(gy[s]) + np.var(gz[s])
        if var < best_var:
            best_var = var
            best_slice = s

    return (
        gx - np.median(gx[best_slice]),
        gy - np.median(gy[best_slice]),
        gz - np.median(gz[best_slice]),
    )


