import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt
import sys
import argparse

# Pattern to parse data lines
pattern = re.compile(r"Raw\s*=\s*(-?\d+)\s*,\s*Time\s*=\s*(\d+)")

def load_data(path):
    """Load data from file and return DataFrame with time in seconds."""
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
    df["time_s"] = df["time_s"] - df["time_s"].iloc[0]  # Start from 0
    return df

def apply_bandpass_filter(data, highpass_cutoff=0.05, lowpass_cutoff=5.0, order=4):
    """Apply band-pass filter (0.05-5 Hz to remove drift and noise)."""
    if len(data) <= 1:
        return None

    sampling_rate = len(data) / (data["time_s"].iloc[-1] - data["time_s"].iloc[0])
    nyquist = 0.5 * sampling_rate

    if highpass_cutoff >= nyquist or lowpass_cutoff >= nyquist:
        return None
    if highpass_cutoff >= lowpass_cutoff:
        return None
    if len(data) <= 3 * (order + 1):
        return None

    try:
        # Apply high-pass first (remove drift)
        normal_cutoff_hp = highpass_cutoff / nyquist
        b_hp, a_hp = butter(order, normal_cutoff_hp, btype='high', analog=False)
        result = filtfilt(b_hp, a_hp, data['raw'].values)

        # Then apply low-pass (remove high-freq noise)
        normal_cutoff_lp = lowpass_cutoff / nyquist
        b_lp, a_lp = butter(order, normal_cutoff_lp, btype='low', analog=False)
        result = filtfilt(b_lp, a_lp, result)

        return pd.Series(result, index=data.index)
    except Exception as e:
        print(f"Error applying filter: {e}")
        return None

def create_window_by_time_range(data, ride_time, start_time, end_time):
    """Create a window based on absolute time range."""
    window_indices = np.where((ride_time.values >= start_time) & (ride_time.values <= end_time))[0]

    if len(window_indices) == 0:
        return data, ride_time

    start_idx = window_indices[0]
    end_idx = window_indices[-1] + 1

    return data.iloc[start_idx:end_idx].reset_index(drop=True), \
           ride_time.iloc[start_idx:end_idx].reset_index(drop=True)

def main():
    parser = argparse.ArgumentParser(
        description='Compare two rides across all 8 channels with band-pass filtering',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 compare_rides_all_channels.py 55/output1.txt 56/output1.txt              # Compare channels 1-8
  python3 compare_rides_all_channels.py ride1.txt ride2.txt --start 40 --end 130   # With time window
  python3 compare_rides_all_channels.py 55/output6.txt 56/output6.txt --before 10 --after 50  # Custom window
        """
    )

    parser.add_argument('ride1', nargs='?', default="/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/55/output1.txt",
                       help='Path to first ride file (default: 55/output1.txt)')
    parser.add_argument('ride2', nargs='?', default="/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/56/output1.txt",
                       help='Path to second ride file (default: 56/output1.txt)')

    parser.add_argument('--window-mode', type=str, default='all', choices=['all', 'time'],
                       help='Window mode: "all" shows full ride, "time" uses custom time range (default: all)')
    parser.add_argument('--start', type=float, default=None,
                       help='Start time in seconds for time window')
    parser.add_argument('--end', type=float, default=None,
                       help='End time in seconds for time window')
    parser.add_argument('--before', type=int, default=10,
                       help='Seconds before peak to include (alternative to --start/--end)')
    parser.add_argument('--after', type=int, default=50,
                       help='Seconds after peak to include (alternative to --start/--end)')

    args = parser.parse_args()

    ride1_path = args.ride1
    ride2_path = args.ride2
    window_mode = args.window_mode
    start_time = args.start
    end_time = args.end

    ride1_display = ride1_path.replace("/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/", "")
    ride2_display = ride2_path.replace("/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/", "")

    print(f"Comparing rides across all channels:")
    print(f"  Ride 1: {ride1_display}")
    print(f"  Ride 2: {ride2_display}")

    # Load both rides
    print("\nLoading rides...")
    ride1_raw = load_data(ride1_path)
    ride2_raw = load_data(ride2_path)

    if ride1_raw.empty or ride2_raw.empty:
        print("Error loading data files")
        return

    print(f"Ride 1: {len(ride1_raw)} samples, duration: {ride1_raw['time_s'].iloc[-1]:.1f}s")
    print(f"Ride 2: {len(ride2_raw)} samples, duration: {ride2_raw['time_s'].iloc[-1]:.1f}s")

    # Apply band-pass filter
    print("\nApplying band-pass filter (0.05 - 5.0 Hz)...")
    ride1_filtered = apply_bandpass_filter(ride1_raw)
    ride2_filtered = apply_bandpass_filter(ride2_raw)

    if ride1_filtered is None or ride2_filtered is None:
        print("Error applying filter")
        return

    # Apply windowing if requested
    if window_mode == 'time' and start_time is not None and end_time is not None:
        print(f"\nApplying time window: {start_time}s to {end_time}s")
        ride1_filtered, ride1_raw_time = create_window_by_time_range(ride1_filtered, ride1_raw["time_s"], start_time, end_time)
        ride2_filtered, ride2_raw_time = create_window_by_time_range(ride2_filtered, ride2_raw["time_s"], start_time, end_time)
    else:
        ride1_raw_time = ride1_raw["time_s"]
        ride2_raw_time = ride2_raw["time_s"]

    # Create subplots (4 rows x 2 columns for 8 channels)
    print("\nCreating multi-channel comparison plot...")
    fig, axes = plt.subplots(4, 2, figsize=(16, 12))
    axes = axes.flatten()

    channel_names = {
        1: "Ch 1 (X-axis)",
        2: "Ch 2 (Y-axis)",
        3: "Ch 3 (Z-axis)",
        4: "Ch 4 (Temperature/Pitch)",
        5: "Ch 5 (Roll)",
        6: "Ch 6 (R2 - Steering)",
        7: "Ch 7 (Acceleration)",
        8: "Ch 8 (Info)"
    }

    # Plot each channel
    for ch in range(1, 9):
        ax = axes[ch - 1]

        # Plot ride 1
        ax.plot(ride1_raw_time.values, ride1_filtered.values,
               label=ride1_display, color='blue', linewidth=1.5, alpha=0.8)

        # Plot ride 2
        ax.plot(ride2_raw_time.values, ride2_filtered.values,
               label=ride2_display, color='red', linewidth=1.5, alpha=0.8)

        ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
        ax.set_ylabel('Raw Units', fontsize=10)
        ax.set_xlabel('Time (s)', fontsize=10)
        ax.set_title(channel_names[ch], fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best', fontsize=9)

    # Main title
    mode_text = f" | Time: {start_time}s to {end_time}s" if window_mode == 'time' and start_time and end_time else ""
    fig.suptitle(f'All Channels Comparison - Band-Pass Filter: 0.05 - 5.0 Hz{mode_text}',
                fontsize=14, fontweight='bold', y=0.995)

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    # Save figure
    output_path = "/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/ride_comparison_all_channels.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nPlot saved to: {output_path}")

    plt.show()

if __name__ == "__main__":
    main()
