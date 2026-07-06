from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ppk_pipeline.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the GNSS PPK pipeline.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the YAML config file.",
    )
    args = parser.parse_args()

    run_pipeline(Path(args.config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
