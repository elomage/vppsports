#!/usr/bin/env python3
"""
Accelerometer Data Plotting & Analysis
Parses binary accelerometer data and plots filtered 3-axis data
Supports correlation with strain gauge data (R4)
"""

import struct
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt
from pathlib import Path
import argparse


def parse_accel_binary(file_path):
    """Parse binary accelerometer data (struct: uint32_t timestamp_us + int32_t x,y,z)"""
    accel_file = Path(file_path)
    file_size = accel_file.stat().st_size
    record_size = 16  # 4 + 4 + 4 + 4 bytes
    num_records = file_size // record_size

    with open(accel_file, 'rb') as f:
        data = f.read()

    records = []
    for i in range(num_records):
        offset = i * record_size
        timestamp_us, x, y, z = struct.unpack('<I i i i', data[offset:offset+record_size])
        records.append({
            'timestamp_s': timestamp_us / 1e6,
            'x': x,
            'y': y,
            'z': z
        })

    df = pd.DataFrame(records)
    return df


def apply_filters(df, fs, hp_freq=0.05, lp_freq=20):
    """
    Apply high-pass and low-pass filters to accelerometer data

    hp_freq: High-pass cutoff (default 0.05 Hz - removes DC drift, like strain data)
    lp_freq: Low-pass cutoff (default 20 Hz - removes sensor noise & vibrations)
    """
    nyquist = fs / 2

    # High-pass filter (0.05 Hz removes low-frequency thermal drift)
    hp = hp_freq / nyquist
    b_hp, a_hp = butter(4, hp, 'high')

    # Low-pass filter (20 Hz removes high-frequency noise, keeps steering signals)
    lp = lp_freq / nyquist
    b_lp, a_lp = butter(4, lp, 'low')

    # Apply cascade filters
    df['x_filtered'] = filtfilt(b_lp, a_lp, filtfilt(b_hp, a_hp, df['x']))
    df['y_filtered'] = filtfilt(b_lp, a_lp, filtfilt(b_hp, a_hp, df['y']))
    df['z_filtered'] = filtfilt(b_lp, a_lp, filtfilt(b_hp, a_hp, df['z']))

    return df, (hp_freq, lp_freq)


def plot_accelerometer(df, start_time=0, end_time=400, output_file='accel_plot.png'):
    """Plot all 3 accelerometer axes in time window"""
    time_window = (df['timestamp_s'] >= start_time) & (df['timestamp_s'] <= end_time)
    time_data = df[time_window]['timestamp_s']

    fig, axes = plt.subplots(3, 1, figsize=(14, 10))

    # X-axis (Roll - lateral tilt)
    axes[0].plot(time_data, df[time_window]['x_filtered'],
                label='X (Roll/Lateral)', color='red', linewidth=0.8)
    axes[0].set_ylabel('X Acceleration (mg)', fontsize=10)
    axes[0].set_title('Accelerometer Data - Filtered (0.05-20 Hz)', fontsize=12, fontweight='bold')
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    # Y-axis (Pitch - forward/backward)
    axes[1].plot(time_data, df[time_window]['y_filtered'],
                label='Y (Pitch/Forward)', color='green', linewidth=0.8)
    axes[1].set_ylabel('Y Acceleration (mg)', fontsize=10)
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    # Z-axis (Yaw - vertical)
    axes[2].plot(time_data, df[time_window]['z_filtered'],
                label='Z (Yaw/Vertical)', color='blue', linewidth=0.8)
    axes[2].set_ylabel('Z Acceleration (mg)', fontsize=10)
    axes[2].set_xlabel('Time (seconds)', fontsize=10)
    axes[2].grid(True, alpha=0.3)
    axes[2].legend()

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"✅ Saved: {output_file}")
    return fig


def print_statistics(df, start_time=40, end_time=130):
    """Print statistics for time window"""
    time_window = (df['timestamp_s'] >= start_time) & (df['timestamp_s'] <= end_time)

    print("\n=== ACCELEROMETER STATISTICS ===")
    print(f"Time window: {start_time}s - {end_time}s")
    print(f"\nFiltered Data (mg):")
    print(f"  X (Roll):   mean={df[time_window]['x_filtered'].mean():>10.1f}, std={df[time_window]['x_filtered'].std():>10.1f}")
    print(f"  Y (Pitch):  mean={df[time_window]['y_filtered'].mean():>10.1f}, std={df[time_window]['y_filtered'].std():>10.1f}")
    print(f"  Z (Yaw):    mean={df[time_window]['z_filtered'].mean():>10.1f}, std={df[time_window]['z_filtered'].std():>10.1f}")

    # RMS values
    print(f"\nRMS Values (mg):")
    print(f"  X: {np.sqrt(np.mean(df[time_window]['x_filtered']**2)):.1f}")
    print(f"  Y: {np.sqrt(np.mean(df[time_window]['y_filtered']**2)):.1f}")
    print(f"  Z: {np.sqrt(np.mean(df[time_window]['z_filtered']**2)):.1f}")


def main():
    parser = argparse.ArgumentParser(description='Plot accelerometer data')
    parser.add_argument('--file', type=str, default='2026_03_16_Sigulda_brauciens_4_accel.BIN',
                       help='Binary accelerometer file')
    parser.add_argument('--start', type=int, default=40, help='Start time (seconds)')
    parser.add_argument('--end', type=int, default=130, help='End time (seconds)')
    parser.add_argument('--hp', type=float, default=0.05, help='High-pass cutoff (Hz)')
    parser.add_argument('--lp', type=float, default=20, help='Low-pass cutoff (Hz)')
    parser.add_argument('--output', type=str, default='accel_filtered_plot.png',
                       help='Output filename')

    args = parser.parse_args()

    # Parse data
    print(f"Loading {args.file}...")
    df = parse_accel_binary(args.file)

    # Get sampling rate
    fs = len(df) / (df['timestamp_s'].max() - df['timestamp_s'].min())
    print(f"Sampling rate: {fs:.1f} Hz")
    print(f"Duration: {df['timestamp_s'].min():.1f}s - {df['timestamp_s'].max():.1f}s")
    print(f"Total records: {len(df)}")

    # Apply filters
    print(f"\nApplying filters: HP={args.hp}Hz, LP={args.lp}Hz")
    df, filters = apply_filters(df, fs, hp_freq=args.hp, lp_freq=args.lp)

    # Plot
    plot_accelerometer(df, start_time=args.start, end_time=args.end, output_file=args.output)

    # Statistics
    print_statistics(df, args.start, args.end)

    # Save filtered data
    df.to_csv('accel_filtered_data.csv', index=False)
    print(f"✅ Saved: accel_filtered_data.csv")


if __name__ == '__main__':
    main()
