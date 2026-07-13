from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Optional, Union, Tuple
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segmentation import segment_ride, RideSegmentation


def _load_imu_txt(path: Union[str, Path]) -> Optional[np.ndarray]:
    rows = []
    try:
        with open(path) as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) != 4:
                    continue
                try:
                    rows.append([float(p) for p in parts])
                except ValueError:
                    continue
    except IOError:
        return None
    return np.array(rows) if rows else None


def _segment_label(seg, normalize: bool) -> str:
    if normalize:
        return seg.normalized().kind
    return seg.kind


def _labels_for_timestamps(timestamps: np.ndarray,
                           segmentation: RideSegmentation,
                           normalize: bool) -> np.ndarray:
    n = len(timestamps)
    labels = np.array(["unlabeled"] * n, dtype=object)
    for s in segmentation.segments:
        lbl = _segment_label(s, normalize)
        mask = (timestamps >= s.t_start) & (timestamps <= s.t_end)
        labels[mask] = lbl
    return labels


def build_export_dataframe(
        acc: np.ndarray,
        gyro: Optional[np.ndarray] = None,
        segmentation: Optional[RideSegmentation] = None,
        normalize: bool = True,
        use_gyro: bool = False,
        expected_n_curves: Optional[int] = None,
) -> pd.DataFrame:
    if segmentation is None:
        segmentation = segment_ride(
            acc,
            gyro if use_gyro else None,
            expected_n_curves=expected_n_curves,
        )

    labels = _labels_for_timestamps(acc[:, 0], segmentation, normalize)
    return pd.DataFrame({
        "timestamp": acc[:, 0],
        "x": acc[:, 1],
        "y": acc[:, 2],
        "z": acc[:, 3],
        "segment": labels,
    })


def build_export_dataframes(
        acc: np.ndarray,
        gyro: Optional[np.ndarray] = None,
        segmentation: Optional[RideSegmentation] = None,
        normalize: bool = True,
        use_gyro: bool = False,
        expected_n_curves: Optional[int] = None,
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    if segmentation is None:
        segmentation = segment_ride(
            acc,
            gyro if use_gyro else None,
            expected_n_curves=expected_n_curves,
        )

    acc_df = pd.DataFrame({
        "timestamp": acc[:, 0],
        "x": acc[:, 1],
        "y": acc[:, 2],
        "z": acc[:, 3],
        "segment": _labels_for_timestamps(acc[:, 0], segmentation, normalize),
    })

    gyro_df = None
    if gyro is not None:
        gyro_df = pd.DataFrame({
            "timestamp": gyro[:, 0],
            "x": gyro[:, 1],
            "y": gyro[:, 2],
            "z": gyro[:, 3],
            "segment": _labels_for_timestamps(gyro[:, 0], segmentation, normalize),
        })
    return acc_df, gyro_df


def export_segmented_csv(
        acc: np.ndarray,
        output_path: Union[str, Path],
        gyro: Optional[np.ndarray] = None,
        segmentation: Optional[RideSegmentation] = None,
        normalize: bool = True,
        use_gyro: bool = False,
        expected_n_curves: Optional[int] = None,
) -> Path:
    acc_df, _ = build_export_dataframes(
        acc=acc, gyro=gyro, segmentation=segmentation,
        normalize=normalize, use_gyro=use_gyro,
        expected_n_curves=expected_n_curves,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    acc_df.to_csv(output_path, index=False)
    return output_path


def export_segmented_pair(
        acc: np.ndarray,
        output_dir: Union[str, Path],
        ride_name: str,
        gyro: Optional[np.ndarray] = None,
        segmentation: Optional[RideSegmentation] = None,
        normalize: bool = True,
        use_gyro: bool = False,
        expected_n_curves: Optional[int] = None,
) -> Tuple[Path, Optional[Path]]:
    acc_df, gyro_df = build_export_dataframes(
        acc=acc, gyro=gyro, segmentation=segmentation,
        normalize=normalize, use_gyro=use_gyro,
        expected_n_curves=expected_n_curves,
    )
    output_dir = Path(output_dir)
    accel_dir = output_dir / "accel"
    accel_dir.mkdir(parents=True, exist_ok=True)
    accel_path = accel_dir / f"{ride_name}.csv"
    acc_df.to_csv(accel_path, index=False)

    gyro_path = None
    if gyro_df is not None:
        gyro_dir = output_dir / "gyro"
        gyro_dir.mkdir(parents=True, exist_ok=True)
        gyro_path = gyro_dir / f"{ride_name}.csv"
        gyro_df.to_csv(gyro_path, index=False)
    return accel_path, gyro_path


def export_from_file(
        accel_path: Union[str, Path],
        output: Union[str, Path],
        gyro_path: Optional[Union[str, Path]] = None,
        normalize: bool = True,
        use_gyro: bool = False,
        expected_n_curves: Optional[int] = None,
) -> Tuple[Path, Optional[Path]]:
    acc = _load_imu_txt(accel_path)
    if acc is None:
        raise ValueError(f"Could not load accelerometer data from {accel_path}")
    gyro = _load_imu_txt(gyro_path) if gyro_path else None

    output = Path(output)
    ride_name = Path(accel_path).stem

    if gyro is not None:
        out_dir = output if output.suffix == "" else output.parent / output.stem
        return export_segmented_pair(
            acc=acc, output_dir=out_dir, ride_name=ride_name,
            gyro=gyro, normalize=normalize, use_gyro=use_gyro,
            expected_n_curves=expected_n_curves,
        )
    out_csv = output if output.suffix == ".csv" else output / f"{ride_name}.csv"
    p = export_segmented_csv(
        acc=acc, output_path=out_csv,
        normalize=normalize, use_gyro=use_gyro,
        expected_n_curves=expected_n_curves,
    )
    return p, None


def _cli():
    p = argparse.ArgumentParser(description="Export segmented IMU ride data to CSV.")
    p.add_argument("accel", type=str, help="Path to accelerometer .txt (t,ax,ay,az)")
    p.add_argument("output", type=str,
                   help="Output: .csv path (accel only) or folder (accel+gyro structure)")
    p.add_argument("--gyro", type=str, default=None, help="Optional gyroscope .txt")
    p.add_argument("--use-gyro", action="store_true", help="Use gyro in detection")
    p.add_argument("--directional", action="store_true",
                   help="Keep curve_l/curve_r instead of normalized 'curve'")
    p.add_argument("--expected-curves", type=int, default=None,
                   help="Expected number of curves on this track")
    args = p.parse_args()

    acc_out, gyro_out = export_from_file(
        accel_path=args.accel,
        output=args.output,
        gyro_path=args.gyro,
        normalize=not args.directional,
        use_gyro=args.use_gyro,
        expected_n_curves=args.expected_curves,
    )
    print(f"Exported accel: {acc_out}")
    if gyro_out is not None:
        print(f"Exported gyro:  {gyro_out}")


if __name__ == "__main__":
    _cli()