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

def apply_bandpass_filter(data, highpass_cutoff=0.05, lowpass_cutoff=50.0, order=4):
    """Apply band-pass filter (0.05-50 Hz to capture steering behavior including micro-corrections)."""
    if len(data) <= 1:
        return None

    # Calculate sampling rate from time differences
    sampling_rate = len(data) / (data["time_s"].iloc[-1] - data["time_s"].iloc[0])
    nyquist = 0.5 * sampling_rate

    if highpass_cutoff >= nyquist or lowpass_cutoff >= nyquist:
        print(f"Warning: Cutoff frequencies exceed Nyquist frequency ({nyquist:.2f} Hz)")
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

def find_peak_index(data, mode='negative'):
    """Find the index of the largest peak in the data."""
    if mode == 'negative':
        # Find the most negative value (G-force peak in turns)
        return np.argmin(data.values)
    else:
        return np.argmax(data.values)

def find_first_positive_threshold_crossing(data, ride_time, threshold=50000):
    """
    Find the START of the FIRST continuous segment ABOVE threshold.
    This is the first significant positive peak (braking/setup).
    Example: threshold=50000 finds first value of first segment above 50,000
    """
    # Look for data ABOVE threshold (positive peaks)
    indices = np.where(data.values > threshold)[0]

    if len(indices) == 0:
        print(f"Warning: No data found above threshold {threshold}")
        return 0, ride_time.iloc[0]

    # Find continuous segments above threshold
    gaps = np.where(np.diff(indices) > 100)[0]  # Gap > 100 samples = separate events

    if len(gaps) == 0:
        # All activity is continuous - use the first point
        first_crossing_idx = indices[0]
    else:
        # Use the FIRST continuous segment (earliest significant event)
        first_crossing_idx = indices[0]
        print(f"  Found first positive peak at index {first_crossing_idx}")

    first_crossing_time = ride_time.iloc[first_crossing_idx]

    return first_crossing_idx, first_crossing_time

def find_active_ride_window(data, threshold_percentile=40):
    """
    Detect the active ride window by finding where data magnitude exceeds threshold.
    Returns (start_idx, end_idx) of the active ride.
    """
    # Calculate magnitude (absolute values)
    magnitude = np.abs(data.values)

    # Find threshold based on percentile
    threshold = np.percentile(magnitude, threshold_percentile)

    # Find indices where magnitude exceeds threshold
    active_indices = np.where(magnitude > threshold)[0]

    if len(active_indices) == 0:
        return 0, len(data)

    # Get continuous block with most data
    start_idx = active_indices[0]
    end_idx = active_indices[-1]

    return start_idx, end_idx

def create_absolute_time_window(ride_data, ride_time, start_time, end_time):
    """
    Create a window based on absolute time (not peak-relative).
    Returns data and time arrays for the time range.
    """
    window_indices = np.where((ride_time.values >= start_time) & (ride_time.values <= end_time))[0]

    if len(window_indices) == 0:
        print(f"Warning: No data found in time range {start_time}s to {end_time}s")
        return None, None

    start_idx = window_indices[0]
    end_idx = window_indices[-1] + 1

    return ride_data.iloc[start_idx:end_idx].reset_index(drop=True), \
           ride_time.iloc[start_idx:end_idx].reset_index(drop=True)

def create_window_around_peak(ride_data, ride_time, peak_idx, before_seconds=10, after_seconds=50):
    """
    Create a time window around the peak.
    Returns data and time arrays for the window.
    """
    peak_time = ride_time.iloc[peak_idx]

    # Find indices within the window
    time_relative = ride_time.values - peak_time
    window_indices = np.where((time_relative >= -before_seconds) & (time_relative <= after_seconds))[0]

    if len(window_indices) == 0:
        return ride_data, ride_time

    start_idx = window_indices[0]
    end_idx = window_indices[-1] + 1

    return ride_data.iloc[start_idx:end_idx].reset_index(drop=True), \
           ride_time.iloc[start_idx:end_idx].reset_index(drop=True)

def align_rides(ride1, ride2, ride1_time, ride2_time, peak_time1, peak_time2):
    """
    Align two rides using provided peak times.
    Uses the actual first positive peaks we already found.
    Returns aligned time axes with peak at t=0.
    """
    print(f"Ride 1 alignment: peak at {peak_time1:.1f}s, value: {ride1.iloc[(ride1_time - peak_time1).abs().argmin()]:,.0f}")
    print(f"Ride 2 alignment: peak at {peak_time2:.1f}s, value: {ride2.iloc[(ride2_time - peak_time2).abs().argmin()]:,.0f}")

    # Create aligned time axis with peak at t=0
    new_time1 = ride1_time.values - peak_time1
    new_time2 = ride2_time.values - peak_time2

    return new_time1, new_time2

def save_data(filtered_data, raw_data, time_data, output_path):
    """Save filtered ride data in original format (Raw = X, Time = Y)."""
    try:
        with open(output_path, "w") as f:
            for idx, (raw_val, time_val) in enumerate(zip(filtered_data.values, time_data.values)):
                # Convert time back from seconds to microseconds
                time_us = int(time_val * 1_000_000)
                # Write in original format
                f.write(f"Raw = {int(np.round(raw_val))}, Time = {time_us}\n")
        print(f"Saved windowed data to: {output_path}")
        return True
    except Exception as e:
        print(f"Error saving data to {output_path}: {e}")
        return False

def calculate_rms(data):
    """Calculate RMS (Root Mean Square) of data."""
    return np.sqrt(np.mean(data.values ** 2))

def calculate_metrics(ride1, ride2, ride1_name="Ride 1", ride2_name="Ride 2"):
    """Calculate comparison metrics between two rides."""
    rms1 = calculate_rms(ride1)
    rms2 = calculate_rms(ride2)

    max_amp1 = np.min(ride1.values)  # Most negative peak
    max_amp2 = np.min(ride2.values)

    print("\n" + "="*60)
    print("RIDE COMPARISON METRICS")
    print("="*60)
    print(f"{ride1_name} - RMS Steering Energy: {rms1:,.0f}")
    print(f"{ride2_name} - RMS Steering Energy: {rms2:,.0f}")
    print(f"Difference: {abs(rms1 - rms2):,.0f} ({abs(rms1 - rms2)/max(rms1, rms2)*100:.1f}%)")
    print()
    print(f"{ride1_name} - Max G-Force (peak): {max_amp1:,.0f}")
    print(f"{ride2_name} - Max G-Force (peak): {max_amp2:,.0f}")
    print(f"Difference: {abs(max_amp1 - max_amp2):,.0f}")
    print()
    if rms1 < rms2:
        print(f"✓ {ride1_name} was smoother: {(rms2-rms1)/rms2*100:.1f}% less steering energy")
    else:
        print(f"✓ {ride2_name} was smoother: {(rms1-rms2)/rms1*100:.1f}% less steering energy")
    print("="*60 + "\n")

def main():
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description='Compare two bobsled/skeleton rides with band-pass filtering and alignment',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 compare_rides.py                                               # Use defaults (first peak, threshold=50000)
  python3 compare_rides.py --peak-mode max                               # Use maximum peak mode
  python3 compare_rides.py --peak-mode first --threshold 40000           # First peak with custom threshold
  python3 compare_rides.py --before 5 --after 60 --peak-mode first       # Peak-based: 5s before, 60s after
  python3 compare_rides.py --window-mode absolute --start 40 --end 120   # Absolute time: from 40s to 120s
  python3 compare_rides.py ride1.txt ride2.txt --peak-mode max --before 10 --after 50  # Custom everything
        """
    )

    parser.add_argument('ride1', nargs='?', default="/testFile/55/output6.txt",
                       help='Path to first ride file (default: 55/output6.txt)')
    parser.add_argument('ride2', nargs='?', default="testFile/56/output6.txt",
                       help='Path to second ride file (default: 56/output6.txt)')

    # Window mode selection
    parser.add_argument('--window-mode', type=str, default='peak', choices=['peak', 'absolute'],
                       help='Window mode: "peak" aligns on first peak, "absolute" uses fixed time range (default: peak)')

    # Peak-based window options
    parser.add_argument('--before', type=int, default=10,
                       help='Seconds before peak to include in window (default: 10, only for --window-mode peak)')
    parser.add_argument('--after', type=int, default=50,
                       help='Seconds after peak to include in window (default: 50, only for --window-mode peak)')
    parser.add_argument('--threshold', type=int, default=50000,
                       help='Threshold value for first positive peak detection (default: 50000, finds first value ABOVE this. Example: 50000 finds first value above 50,000)')
    parser.add_argument('--peak-mode', type=str, default='first', choices=['first', 'max'],
                       help='Peak detection mode: "first" finds first peak above threshold, "max" finds largest peak (default: first)')

    # Absolute time window options
    parser.add_argument('--start', type=float, default=None,
                       help='Start time in seconds for BOTH rides (only for --window-mode absolute)')
    parser.add_argument('--end', type=float, default=None,
                       help='End time in seconds for BOTH rides (only for --window-mode absolute)')

    # Per-ride absolute windows (overrides --start/--end)
    parser.add_argument('--start1', type=float, default=None,
                       help='Start time in seconds for ride1 (overrides --start)')
    parser.add_argument('--end1', type=float, default=None,
                       help='End time in seconds for ride1 (overrides --end)')
    parser.add_argument('--start2', type=float, default=None,
                       help='Start time in seconds for ride2 (overrides --start)')
    parser.add_argument('--end2', type=float, default=None,
                       help='End time in seconds for ride2 (overrides --end)')

    # Output options
    parser.add_argument('--output1', type=str, default=None,
                       help='Save windowed ride1 data to this file (in original Raw/Time format)')
    parser.add_argument('--output2', type=str, default=None,
                       help='Save windowed ride2 data to this file (in original Raw/Time format)')

    args = parser.parse_args()

    ride1_path = args.ride1
    ride2_path = args.ride2
    window_mode = args.window_mode
    before_seconds = args.before
    after_seconds = args.after
    start_time = args.start
    end_time = args.end
    threshold = args.threshold
    peak_mode = args.peak_mode

    print(f"Using paths:")
    print(f"  Ride 1: {ride1_path}")
    print(f"  Ride 2: {ride2_path}")
    if window_mode == 'peak':
        print(f"Window mode: PEAK-BASED ({peak_mode.upper()} mode, {before_seconds}s before, {after_seconds}s after)")
        if peak_mode == 'first':
            print(f"  Peak detection: First peak above threshold {threshold}")
        else:
            print(f"  Peak detection: Maximum (largest) peak")
    else:
        if start_time is None or end_time is None:
            print("Error: --window-mode absolute requires --start and --end arguments")
            return
        print(f"Window mode: ABSOLUTE ({start_time}s to {end_time}s)")

    print("\nLoading rides...")
    ride1_raw = load_data(ride1_path)
    ride2_raw = load_data(ride2_path)

    # Extract relative paths for display
    ride1_display = ride1_path.replace("/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/", "")
    ride2_display = ride2_path.replace("/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/", "")

    if ride1_raw.empty or ride2_raw.empty:
        print("Error loading data files")
        return

    print(f"Ride 1: {len(ride1_raw)} samples, duration: {ride1_raw['time_s'].iloc[-1]:.1f}s")
    print(f"Ride 2: {len(ride2_raw)} samples, duration: {ride2_raw['time_s'].iloc[-1]:.1f}s")

    # Apply band-pass filter
    print("\nApplying band-pass filter (0.05 - 50.0 Hz)...")
    ride1_filtered = apply_bandpass_filter(ride1_raw)
    ride2_filtered = apply_bandpass_filter(ride2_raw)

    if ride1_filtered is None or ride2_filtered is None:
        print("Error applying filter")
        return

    # Find peaks first
    print("\nFinding peaks...")
    if peak_mode == 'first':
        peak_idx1_pos, peak_time1_pos = find_first_positive_threshold_crossing(ride1_filtered, ride1_raw["time_s"], threshold=threshold)
        peak_idx2_pos, peak_time2_pos = find_first_positive_threshold_crossing(ride2_filtered, ride2_raw["time_s"], threshold=threshold)
        print(f"Ride 1 POSITIVE peak (FIRST above {threshold}): {peak_time1_pos:.1f}s, value: {ride1_filtered.iloc[peak_idx1_pos]:,.0f}")
        print(f"Ride 2 POSITIVE peak (FIRST above {threshold}): {peak_time2_pos:.1f}s, value: {ride2_filtered.iloc[peak_idx2_pos]:,.0f}")
    else:  # peak_mode == 'max'
        peak_idx1_pos = find_peak_index(ride1_filtered, mode='positive')
        peak_idx2_pos = find_peak_index(ride2_filtered, mode='positive')
        peak_time1_pos = ride1_raw['time_s'].iloc[peak_idx1_pos]
        peak_time2_pos = ride2_raw['time_s'].iloc[peak_idx2_pos]
        print(f"Ride 1 POSITIVE peak (MAXIMUM): {peak_time1_pos:.1f}s, value: {ride1_filtered.iloc[peak_idx1_pos]:,.0f}")
        print(f"Ride 2 POSITIVE peak (MAXIMUM): {peak_time2_pos:.1f}s, value: {ride2_filtered.iloc[peak_idx2_pos]:,.0f}")

    peak_idx1_neg = find_peak_index(ride1_filtered, mode='negative')
    peak_idx2_neg = find_peak_index(ride2_filtered, mode='negative')
    print(f"Ride 1 negative peak: {ride1_raw['time_s'].iloc[peak_idx1_neg]:.1f}s, value: {ride1_filtered.iloc[peak_idx1_neg]:,.0f}")
    print(f"Ride 2 negative peak: {ride2_raw['time_s'].iloc[peak_idx2_neg]:.1f}s, value: {ride2_filtered.iloc[peak_idx2_neg]:,.0f}")

    # Create window based on selected mode
    if window_mode == 'peak':
        print(f"\nCreating windows around POSITIVE peaks ({before_seconds}s before, {after_seconds}s after)...")
        ride1_filtered_window, ride1_time_window = create_window_around_peak(
            ride1_filtered, ride1_raw["time_s"], peak_idx1_pos, before_seconds=before_seconds, after_seconds=after_seconds
        )
        ride2_filtered_window, ride2_time_window = create_window_around_peak(
            ride2_filtered, ride2_raw["time_s"], peak_idx2_pos, before_seconds=before_seconds, after_seconds=after_seconds
        )
    else:  # absolute mode
        # Per-ride windows take precedence, fall back to shared --start/--end
        start1 = args.start1 if args.start1 is not None else (args.start or 0)
        end1 = args.end1 if args.end1 is not None else (args.end or ride1_raw["time_s"].iloc[-1])
        start2 = args.start2 if args.start2 is not None else (args.start or 0)
        end2 = args.end2 if args.end2 is not None else (args.end or ride2_raw["time_s"].iloc[-1])

        if args.start1 is not None or args.start2 is not None:
            print(f"\nCreating absolute time windows (per-ride):")
            print(f"  Ride 1: {start1}s to {end1}s")
            print(f"  Ride 2: {start2}s to {end2}s")
        else:
            print(f"\nCreating absolute time windows ({start1}s to {end1}s)...")

        ride1_filtered_window, ride1_time_window = create_absolute_time_window(
            ride1_filtered, ride1_raw["time_s"], start1, end1
        )
        ride2_filtered_window, ride2_time_window = create_absolute_time_window(
            ride2_filtered, ride2_raw["time_s"], start2, end2
        )

        if ride1_filtered_window is None or ride2_filtered_window is None:
            print("Error creating windows")
            return

    print(f"Ride 1 window: {ride1_time_window.iloc[0]:.1f}s - {ride1_time_window.iloc[-1]:.1f}s")
    print(f"Ride 2 window: {ride2_time_window.iloc[0]:.1f}s - {ride2_time_window.iloc[-1]:.1f}s")

    # Save windowed data if output paths specified
    if args.output1:
        save_data(ride1_filtered_window, ride1_raw, ride1_time_window, args.output1)
    if args.output2:
        save_data(ride2_filtered_window, ride2_raw, ride2_time_window, args.output2)

    # Align rides by peak (only if using peak mode)
    if window_mode == 'peak':
        print("\nAligning rides by peak...")
        time1_aligned, time2_aligned = align_rides(ride1_filtered_window, ride2_filtered_window,
                                                   ride1_time_window, ride2_time_window,
                                                   peak_time1_pos, peak_time2_pos)
    else:
        # For absolute mode, use time as-is without alignment
        print("\nUsing absolute time (no peak alignment)...")
        time1_aligned = ride1_time_window.values
        time2_aligned = ride2_time_window.values

    # Calculate metrics (on windows only)
    calculate_metrics(ride1_filtered_window, ride2_filtered_window, ride1_display, ride2_display)

    # Print analysis window summary (for FFT/frequency analysis sync)
    print(f"\n{'='*60}")
    print("ANALYSIS WINDOW INFO (for FFT sync)")
    print(f"{'='*60}")
    print(f"Ride 1: {ride1_time_window.iloc[0]:.1f}s to {ride1_time_window.iloc[-1]:.1f}s")
    print(f"Ride 2: {ride2_time_window.iloc[0]:.1f}s to {ride2_time_window.iloc[-1]:.1f}s")
    print(f"{'='*60}\n")

    # Plot - Single zoomed view
    print("Creating comparison plot...")
    fig, ax = plt.subplots(figsize=(14, 7))

    ax.plot(time1_aligned, ride1_filtered_window.values, label=ride1_display,
            color='blue', linewidth=2.5, alpha=0.85)
    ax.plot(time2_aligned, ride2_filtered_window.values, label=ride2_display,
            color='red', linewidth=2.5, alpha=0.85)

    # Only show peak alignment line in peak mode
    if window_mode == 'peak':
        ax.axvline(x=0, color='green', linestyle='--', linewidth=1.5, alpha=0.7, label='First Peak Alignment')

    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Raw Units', fontsize=12)
    ax.set_title(f'Ride Comparison - Channel 6 (R2) | Band-Pass Filter: 0.05 - 50.0 Hz | {"Peak-based (" + peak_mode.upper() + "): " + str(before_seconds) + "s Before + " + str(after_seconds) + "s After" if window_mode == "peak" else "Absolute: " + str(start_time) + "s to " + str(end_time) + "s"}', fontsize=13, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best', fontsize=11)

    plt.tight_layout()

    # Save figure
    output_path = "/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/ride_comparison.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nPlot saved to: {output_path}")

    # Show the interactive matplotlib plot
    plt.show()

if __name__ == "__main__":
    main()
