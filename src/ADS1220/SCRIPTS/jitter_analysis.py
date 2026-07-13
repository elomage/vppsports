import re
import argparse
import pandas as pd
import matplotlib.pyplot as plt

# This pattern is the same as in your plotting script
pattern = re.compile(r"Raw\s*=\s*(-?\d+)\s*,\s*Time\s*=\s*(\d+)")

def load_timestamps(path):
    """Loads only the timestamps from the data file."""
    time_us = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                time_us.append(int(m.group(2)))
    if not time_us:
        return pd.DataFrame()
        
    df = pd.DataFrame({"time_us": time_us})
    return df

def analyze_jitter(df, target_interval_ms=1.5):
    """Calculates and prints jitter statistics."""
    if len(df) < 2:
        print("Not enough data points to analyze jitter.")
        return None

    # Calculate the difference between consecutive timestamps
    # and convert from microseconds (us) to milliseconds (ms)
    delta_t_ms = df['time_us'].diff() / 1000.0

    # --- Statistics ---
    mean_val = delta_t_ms.mean()
    std_val = delta_t_ms.std()
    max_val = delta_t_ms.max()
    min_val = delta_t_ms.min()
    
    print("--- Jitter Analysis ---")
    print(f"Target Interval: {target_interval_ms:.3f} ms ({(1/target_interval_ms)*1000:.0f} Hz)")
    print(f"Total Samples:     {len(df)}")
    print("-------------------------")
    print(f"Mean Interval:     {mean_val:.4f} ms")
    print(f"Std Deviation (σ): {std_val:.4f} ms")
    print(f"Max Interval:      {max_val:.4f} ms")
    print(f"Min Interval:      {min_val:.4f} ms")
    print("-------------------------")
    
    return delta_t_ms.dropna()


def main():
    ap = argparse.ArgumentParser(description="Analyze timestamp jitter from an ADS1220 log file.")
    ap.add_argument("input", help="Path to data file containing lines: 'Raw=N, Time=T, time in us'")
    ap.add_argument("--target_ms", type=float, default=1.5, help="Target sample interval in milliseconds (default: 0.5 for 2000 Hz)")
    ap.add_argument("--save", help="Optional path to save the histogram plot (e.g., jitter_hist.png)")
    ap.add_argument("--show", action="store_true", help="Show interactive plot window")
    args = ap.parse_args()

    df = load_timestamps(args.input)
    if df.empty:
        print("No data parsed. Check file format.")
        return

    delta_t_ms = analyze_jitter(df, args.target_ms)
    
    if delta_t_ms is None:
        return

    # --- Plotting ---
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(delta_t_ms, bins=50, alpha=0.8, label="Jitter Distribution")
    
    ax.axvline(delta_t_ms.mean(), color='red', linestyle='--', linewidth=2, label=f'Mean: {delta_t_ms.mean():.4f} ms')
    ax.axvline(args.target_ms, color='green', linestyle=':', linewidth=2, label=f'Target: {args.target_ms:.1f} ms')

    ax.set_title("Timestamp Jitter (Interval Between Samples)")
    ax.set_xlabel("Time Difference (ms)")
    ax.set_ylabel("Frequency (Count)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    plt.tight_layout()
    if args.save:
        plt.savefig(args.save, dpi=150)
        print(f"Saved histogram to {args.save}")
    if args.show or not args.save:
        plt.show()


if __name__ == "__main__":
    main()