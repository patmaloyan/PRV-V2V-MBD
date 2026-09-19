#!/usr/bin/env python3
"""Generate the three PRV paper results from one experiment directory."""

from __future__ import annotations

import argparse
from pathlib import Path

import cases_graph
import performance_distribution
import performance_table


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent / "created"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "experiment_root", type=Path,
        help="Directory containing experiment.json and attacks/",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--attack-seeds", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--simulation-seed", default="1")
    parser.add_argument("--warmup-seconds", type=int, default=30)
    parser.add_argument(
        "--performance-setting", default="InTAS_urban_2AM_7200sec",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.warmup_seconds < 0:
        raise ValueError("--warmup-seconds must not be negative")
    experiment_root = args.experiment_root.resolve()
    output_dir = args.output_dir.resolve()

    for path in cases_graph.generate(
        experiment_root, output_dir, args.attack_seeds,
        args.simulation_seed, args.warmup_seconds,
    ):
        print(f"Wrote {path}")
    for path in performance_distribution.generate(
        experiment_root, output_dir, args.performance_setting,
        args.attack_seeds, args.simulation_seed, args.warmup_seconds,
    ):
        print(f"Wrote {path}")
    table_path = performance_table.generate(
        experiment_root, output_dir, args.attack_seeds,
        args.simulation_seed, args.warmup_seconds,
    )
    print(f"Wrote {table_path}")


if __name__ == "__main__":
    main()
