import re
import numpy as np
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt, welch
import os

pattern = re.compile(r"Raw\s*=\s*(-?\d+)\s*,\s*Time\s*=\s*(\d+)")

def load_data(path):
    raw_vals = []
    time_us = []
    if not os.path.exists(path): return pd.DataFrame()
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                raw_vals.append(int(m.group(1)))
                time_us.append(int(m.group(2)))
    if not raw_vals: return pd.DataFrame()
    df = pd.DataFrame({"time_us": time_us, "raw": raw_vals})
    df["time_s"] = df["time_us"] / 1_000_000.0
    df["time_s"] = df["time_s"] - df["time_s"].iloc[0]
    return df

def find_noise_floor(ride_dir, ch):
    file_path = os.path.join(ride_dir, f"output{ch}.txt")
    print(f"Analyzing {file_path} for noise floor...")
    df = load_data(file_path)
    if df.empty: return
    fs = len(df) / (df['time_s'].iloc[-1] - df['time_s'].iloc[0])

    # Apply 0.05 Hz high-pass to remove thermal drift
    nyquist = 0.5 * fs
    b, a = butter(4, 0.05 / nyquist, btype='high')
    filtered_data = filtfilt(b, a, df['raw'].values)

    f, psd = welch(filtered_data, fs=fs, nperseg=2048)
    
    plt.figure(figsize=(12, 7))
    plt.loglog(f, psd, color='blue', label='Signal PSD')
    plt.axvspan(0.5, 5, color='green', alpha=0.1, label='Steering Band')
    plt.axvspan(5, 50, color='orange', alpha=0.1, label='Structural Vibrations')
    plt.title(f"Wide-Band PSD (Filtered 0.05Hz) - Ch {ch}")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("PSD")
    plt.grid(True, which='both', alpha=0.3)
    plt.legend()
    
    print("\nPSD Value Distribution (High-Pass Filtered):")
    sample_freqs = [0.5, 1, 5, 10, 20, 50, 100, 200, 300]
    for sf in sample_freqs:
        idx = np.abs(f - sf).argmin()
        print(f"  {f[idx]:>5.1f} Hz: {psd[idx]:.2e}")

    plt.savefig("noise_floor_analysis.png")
    plt.show()
    
def main():
    parser = argparse.ArgumentParser(
    description='Using Welch method and frequency density find the noise floor frequency for further analysis',
    formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--ride', nargs='?', default="/testFile/55/", help='Path to ride file')
    
    args = parser.parse_args()
    ride_path = args.ride
    
    find_noise_floor(ride_path, 2)

if __name__ == "__main__":
    main()
