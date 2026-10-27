"""spark-submit entry point for the parameter sweep (local or Amazon EMR).

    spark-submit sweeps/run_sweep.py --sessions data/sessions --out results/sweep.parquet
    spark-submit ... sweeps/run_sweep.py --sessions s3://BUCKET/sessions --out s3://BUCKET/results/sweeps/sweep.parquet
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from microprice import sweep


def localize(uri: str) -> Path:
    """Copies s3:// inputs to local disk with the AWS CLI available on EMR nodes."""
    if not uri.startswith("s3://"):
        return Path(uri)
    local = Path(tempfile.mkdtemp(prefix="sessions-"))
    subprocess.run(["aws", "s3", "sync", uri, str(local)], check=True)
    return local


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--partitions", type=int, default=256)
    args = parser.parse_args()
    paths = sorted(localize(args.sessions).glob("*.npz"))
    results = sweep.run_spark(paths, master="", partitions=args.partitions, limit=None)
    if args.out.startswith("s3://"):
        local = Path(tempfile.mkdtemp()) / "sweep.parquet"
        results.to_parquet(local)
        subprocess.run(["aws", "s3", "cp", str(local), args.out], check=True)
    else:
        results.to_parquet(args.out)


if __name__ == "__main__":
    main()
