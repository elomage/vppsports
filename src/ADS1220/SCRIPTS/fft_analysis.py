import re
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# This pattern is the same as in your other scripts
pattern = re.compile(r"Raw\s*=\s*(-?\d+)\s*,\s*Time\s*=\s*(\d+)")

def load_data(path):
    """Loads raw values and timestamps into a pandas DataFrame."""
    raw_vals = []
    time_us = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                raw_vals.append(int(m.group(1)))
                time_us.append(int(m.group(2)))
    if not raw_vals:
        return pd.DataFrame()
        
    df = pd.DataFrame({"time_us": time_us, "raw": raw_vals})
    df["time_s"] = df["time_us"] / 1_000_000.0
    return df

def analyze_fft(df):
    """Performs FFT on the raw data and plots the spectrum."""
    if len(df) < 2:
        print("Not enough data points for FFT analysis.")
        return

    # --- Calculate Sampling Rate ---
    # The FFT assumes a constant sampling rate. We use the average rate.
    sampling_interval_s = df['time_s'].diff().mean()
    sampling_rate_hz = 1.0 / sampling_interval_s
    
    print("--- FFT Analysis ---")
    print(f"Average Sampling Rate: {sampling_rate_hz:.2f} Hz")
    print("--------------------")

    # --- Perform FFT ---
    N = len(df['raw'])
    # Subtract the mean (DC offset) to make the 0 Hz component less dominant
    signal = df['raw'].values - df['raw'].mean()
    
    # Compute the FFT
    yf = np.fft.fft(signal)
    # Compute the frequency bins
    xf = np.fft.fftfreq(N, 1 / sampling_rate_hz)

    # --- Plotting ---
    # We only plot the positive frequencies (the first half of the array)
    positive_mask = xf >= 0
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Calculate magnitude (amplitude) and normalize
    magnitude = 2.0/N * np.abs(yf[positive_mask])
    
    ax.plot(xf[positive_mask], magnitude)
    ax.set_title("Frequency Spectrum (FFT)")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Amplitude")
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    
    # Optional: Use a logarithmic scale for the y-axis to see smaller components
    # ax.set_yscale('log')
    
    return fig, ax


def main():
    ap = argparse.ArgumentParser(description="Perform FFT analysis on ADS1220 log data.")
    ap.add_argument("input", help="Path to data file containing lines: 'Raw=N, Time=T, time in us'")
    ap.add_argument("--save", help="Optional path to save the FFT plot (e.g., fft_plot.png)")
    ap.add_argument("--show", action="store_true", help="Show interactive plot window")
    args = ap.parse_args()

    df = load_data(args.input)
    if df.empty:
        print("No data parsed. Check file format.")
        return

    fig, ax = analyze_fft(df)
    
    plt.tight_layout()
    if args.save:
        plt.savefig(args.save, dpi=150)
        print(f"Saved FFT plot to {args.save}")
    if args.show or not args.save:
        plt.show()


if __name__ == "__main__":
    main()