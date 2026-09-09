"""Deprecated entry point for the old PPK pipeline.

The previous `ppk_pipeline` module is no longer in this repository.
Use `scripts/process_recording_all.py` instead.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deprecated. The old GNSS PPK pipeline entry point has been removed. "
            "Use scripts/process_recording_all.py."
        )
    )
    parser.add_argument(
        "--config",
        help="Ignored. Kept only so old invocations fail with a clear message.",
    )
    parser.parse_args()

    print(
        "scripts/pipeline/process_trip.py is deprecated and no longer runs the old "
        "ppk_pipeline.\n"
        "Use the current workflow instead:\n"
        "  python scripts/archive_in_recordings.py\n"
        "  python scripts/process_recording_all.py <ieraksts>\n"
        "  python scripts/viewer_server.py --port 8765",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
