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
        print(f"Warning: Cutoff frequencies exceed Nyquist frequency ({nyquist:.2f} Hz)")
        return None
    if highpass_cutoff >= lowpass_cutoff:
        return None
    if len(data) <= 3 * (order + 1):
        return None

    try:
        normal_cutoff_hp = highpass_cutoff / nyquist
        b_hp, a_hp = butter(order, normal_cutoff_hp, btype='high', analog=False)
        result = filtfilt(b_hp, a_hp, data['raw'].values)

        normal_cutoff_lp = lowpass_cutoff / nyquist
        b_lp, a_lp = butter(order, normal_cutoff_lp, btype='low', analog=False)
        result = filtfilt(b_lp, a_lp, result)

        return pd.Series(result, index=data.index)
    except Exception as e:
        print(f"Error applying filter: {e}")
        return None

def find_first_threshold_crossing(data, ride_time, threshold=-100000):
    """
    Find the START of the LONGEST continuous segment below threshold.
    This avoids noise spikes and finds the actual ride (sustained activity).
    Example: threshold=-100000 finds first value of longest segment below -100,000
    """
    # Look for data BELOW threshold (negative peaks)
    indices = np.where(data.values < threshold)[0]

    if len(indices) == 0:
        print(f"Warning: No data found below threshold {threshold}")
        return 0, ride_time.iloc[0]

    # Find continuous segments below threshold
    # Look for gaps in the indices to identify separate events
    gaps = np.where(np.diff(indices) > 100)[0]  # Gap > 100 samples = separate events

    if len(gaps) == 0:
        # All activity is continuous - use the first point
        first_crossing_idx = indices[0]
    else:
        # Find ALL segments and pick the LONGEST one
        segments = []
        start_idx = 0

        for gap in gaps:
            segment_start = indices[start_idx]
            segment_end = indices[gap]
            segment_length = gap - start_idx + 1
            segments.append((segment_start, start_idx, segment_length))
            start_idx = gap + 1

        # Add final segment
        segment_start = indices[start_idx]
        segment_length = len(indices) - start_idx
        segments.append((segment_start, start_idx, segment_length))

        # Find LONGEST segment (most likely the real ride, not noise)
        longest_segment = max(segments, key=lambda x: x[2])
        first_crossing_idx = longest_segment[0]

        print(f"  Found {len(segments)} segments below threshold:")
        for i, (seg_start, seg_idx, seg_len) in enumerate(segments):
            start_time = ride_time.iloc[seg_start]
            print(f"    Segment {i+1}: {seg_len} samples, starts at {start_time:.2f}s, value: {data.values[seg_start]:.0f}")
        print(f"  → Using segment {segments.index(longest_segment)+1} (longest: {longest_segment[2]} samples)")

    first_crossing_time = ride_time.iloc[first_crossing_idx]

    return first_crossing_idx, first_crossing_time

def create_absolute_time_window(ride_data, ride_time, start_time, end_time):
    """Create a window based on absolute time range."""
    window_indices = np.where((ride_time.values >= start_time) & (ride_time.values <= end_time))[0]

    if len(window_indices) == 0:
        print(f"Warning: No data found in time range {start_time}s to {end_time}s")
        return None, None

    start_idx = window_indices[0]
    end_idx = window_indices[-1] + 1

    return ride_data.iloc[start_idx:end_idx].reset_index(drop=True), \
           ride_time.iloc[start_idx:end_idx].reset_index(drop=True)

def create_window_around_peak(ride_data, ride_time, peak_idx, before_seconds=30, after_seconds=30):
    """Create a time window around a specific index."""
    peak_time = ride_time.iloc[peak_idx]

    time_relative = ride_time.values - peak_time
    window_indices = np.where((time_relative >= -before_seconds) & (time_relative <= after_seconds))[0]

    if len(window_indices) == 0:
        return ride_data, ride_time

    start_idx = window_indices[0]
    end_idx = window_indices[-1] + 1

    return ride_data.iloc[start_idx:end_idx].reset_index(drop=True), \
           ride_time.iloc[start_idx:end_idx].reset_index(drop=True)

def calculate_rms(data):
    """Calculate RMS (Root Mean Square) of data."""
    return np.sqrt(np.mean(data.values ** 2))

def main():
    parser = argparse.ArgumentParser(
        description='Compare multiple bobsled/skeleton rides with band-pass filtering',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 compare_rides_multi.py ride1.txt ride2.txt ride3.txt              # Compare 3 rides
  python3 compare_rides_multi.py ride1.txt ride2.txt                        # Compare 2 rides
  python3 compare_rides_multi.py ride1.txt ride2.txt --threshold -45000     # Custom threshold
  python3 compare_rides_multi.py ride1.txt ride2.txt --before 10 --after 60 # Custom window
  python3 compare_rides_multi.py ride1.txt ride2.txt --window-mode absolute --start 40 --end 120
        """
    )

    parser.add_argument('rides', nargs='+',
                       help='Paths to ride files (2 or more)')
    parser.add_argument('--window-mode', type=str, default='peak', choices=['peak', 'absolute', 'threshold'],
                       help='Window mode: "peak" for peak-based, "absolute" for fixed time, "threshold" for first event (default: threshold)')
    parser.add_argument('--threshold', type=int, default=-100000,
                       help='Threshold value for first event detection (default: -100000, finds first peak BELOW this negative value. Example: -100000 finds first value below -100,000)')
    parser.add_argument('--before', type=int, default=10,
                       help='Seconds before event to include (default: 10)')
    parser.add_argument('--after', type=int, default=50,
                       help='Seconds after event to include (default: 50)')
    parser.add_argument('--start', type=float, default=None,
                       help='Start time for absolute window')
    parser.add_argument('--end', type=float, default=None,
                       help='End time for absolute window')

    args = parser.parse_args()

    if len(args.rides) < 2:
        print("Error: Please provide at least 2 ride files")
        return

    rides_paths = args.rides
    window_mode = args.window_mode
    threshold = args.threshold
    before_seconds = args.before
    after_seconds = args.after
    start_time = args.start
    end_time = args.end

    print(f"Comparing {len(rides_paths)} rides:")
    for i, path in enumerate(rides_paths, 1):
        display_path = path.replace("/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/", "")
        print(f"  {i}. {display_path}")

    if window_mode == 'threshold':
        print(f"Window mode: THRESHOLD-BASED (first negative peak BELOW {threshold}, {before_seconds}s before + {after_seconds}s after)")
    elif window_mode == 'absolute':
        if start_time is None or end_time is None:
            print("Error: --window-mode absolute requires --start and --end")
            return
        print(f"Window mode: ABSOLUTE ({start_time}s to {end_time}s)")
    else:
        print(f"Window mode: PEAK-BASED ({before_seconds}s before + {after_seconds}s after)")

    # Load and filter all rides
    print("\nLoading and filtering rides...")
    rides_raw = []
    rides_filtered = []
    rides_display = []
    rides_windows = []
    rides_times_window = []

    for path in rides_paths:
        display_path = path.replace("/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/", "")
        rides_display.append(display_path)

        # Load
        raw = load_data(path)
        if raw.empty:
            print(f"Error loading {path}")
            return

        rides_raw.append(raw)

        # Filter
        filtered = apply_bandpass_filter(raw)
        if filtered is None:
            print(f"Error filtering {path}")
            return

        rides_filtered.append(filtered)

        print(f"{display_path}: {len(raw)} samples, {raw['time_s'].iloc[-1]:.1f}s duration")

    # Find alignment points (first threshold crossing)
    print("\nFinding first threshold crossings...")
    alignment_times = []
    alignment_indices = []

    for i, (filtered, raw_time, display_path) in enumerate(zip(rides_filtered, [r["time_s"] for r in rides_raw], rides_display)):
        if window_mode == 'threshold':
            idx, time = find_first_threshold_crossing(filtered, raw_time, threshold)
            alignment_times.append(time)
            alignment_indices.append(idx)
            print(f"{display_path}: First crossing at {time:.2f}s, value: {filtered.iloc[idx]:,.0f}")
        else:
            # For other modes, find max positive peak instead
            idx = np.argmax(filtered.values)
            time = raw_time.iloc[idx]
            alignment_times.append(time)
            alignment_indices.append(idx)
            print(f"{display_path}: Peak at {time:.2f}s, value: {filtered.iloc[idx]:,.0f}")

    # Create windows
    print("\nCreating windows...")
    for i, (filtered, raw_time, display_path, idx, aln_time) in enumerate(
        zip(rides_filtered, [r["time_s"] for r in rides_raw], rides_display, alignment_indices, alignment_times)):

        if window_mode == 'absolute':
            data_win, time_win = create_absolute_time_window(filtered, raw_time, start_time, end_time)
        else:  # threshold or peak
            data_win, time_win = create_window_around_peak(filtered, raw_time, idx, before_seconds, after_seconds)

        if data_win is None:
            print(f"Error creating window for {display_path}")
            return

        rides_windows.append(data_win)
        rides_times_window.append(time_win)

        print(f"{display_path} window: {time_win.iloc[0]:.1f}s - {time_win.iloc[-1]:.1f}s")

    # Calculate metrics
    print("\n" + "="*70)
    print("RIDE COMPARISON METRICS")
    print("="*70)
    metrics = []
    for display_path, window_data in zip(rides_display, rides_windows):
        rms = calculate_rms(window_data)
        max_force = np.min(window_data.values)
        metrics.append((rms, max_force))
        print(f"{display_path}")
        print(f"  RMS Steering Energy: {rms:,.0f}")
        print(f"  Max G-Force (peak): {max_force:,.0f}")

    # Find best ride
    best_rms_idx = np.argmin([m[0] for m in metrics])
    print(f"\n✓ Best RMS: {rides_display[best_rms_idx]} ({metrics[best_rms_idx][0]:,.0f})")
    print("="*70 + "\n")

    # Plot all rides
    print("Creating comparison plot...")
    fig, ax = plt.subplots(figsize=(15, 8))

    colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown', 'pink', 'gray']

    for i, (data_win, time_win, display_path, aln_time) in enumerate(
        zip(rides_windows, rides_times_window, rides_display, alignment_times)):
        color = colors[i % len(colors)]

        if window_mode == 'threshold' or window_mode == 'peak':
            # Align at EVENT (t=0 is the event point, not window start)
            time_aligned = time_win.values - aln_time
            ax.plot(time_aligned, data_win.values, label=display_path, color=color, linewidth=2.5, alpha=0.85)
            if i == 0:  # Only show alignment line for first ride
                ax.axvline(x=0, color='green', linestyle='--', linewidth=1.5, alpha=0.7, label='First Event')
        else:
            # Absolute time - show actual times
            ax.plot(time_win.values, data_win.values, label=display_path, color=color, linewidth=2.5, alpha=0.85)

    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Raw Units', fontsize=12)

    title = f'Ride Comparison ({len(rides_paths)} rides) - Channel 6 (R2) | Band-Pass Filter: 0.05 - 5.0 Hz'
    if window_mode == 'threshold':
        title += f' | Threshold: {threshold}'
    elif window_mode == 'absolute':
        title += f' | Time: {start_time}s to {end_time}s'
    else:
        title += f' | Peak-based: {before_seconds}s Before + {after_seconds}s After'

    ax.set_title(title, fontsize=13, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best', fontsize=10)

    plt.tight_layout()

    output_path = "/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/ride_comparison_multi.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Plot saved to: {output_path}")

    plt.show()

if __name__ == "__main__":
    main()
