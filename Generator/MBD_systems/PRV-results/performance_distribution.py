"""Create the paper-style CAM-only versus PRV performance figure."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import (
    ATTACKS, DETECTORS, add_counts, count_debug_file, debug_path,
    empty_counts, load_manifest, metrics, scenario_definition,
)


def collect(
    experiment_root: Path, setting: str, attack_seeds: list[int],
    simulation_seed: str, warmup_seconds: int,
) -> dict:
    manifest = load_manifest(experiment_root)
    start_s = int(scenario_definition(manifest, setting)["communication_start"])
    cutoff_ns = (start_s + warmup_seconds) * 1_000_000_000
    results = {}
    for attack, _attack_label, _color in ATTACKS:
        for detector_label, result_name in DETECTORS:
            pooled = empty_counts()
            for attack_seed in attack_seeds:
                path = debug_path(
                    experiment_root, attack, attack_seed, simulation_seed,
                    setting, result_name,
                )
                print(f"[performance] {path}", flush=True)
                add_counts(pooled, count_debug_file(path, cutoff_ns))
            results[(attack, detector_label)] = metrics(pooled)
    return results


def plot(results: dict, output_dir: Path) -> tuple[Path, Path]:
    figure, axes = plt.subplots(1, 3, figsize=(7.16, 2.65))
    specifications = (
        ("fpr", "False Positive Rate"),
        ("tpr", "True Positive Rate"),
        ("f1", "F1 Score"),
    )
    positions = np.arange(len(DETECTORS))
    bar_width = 0.36
    for axis, (metric_key, title) in zip(axes, specifications):
        all_values = []
        for attack_index, (attack, attack_label, color) in enumerate(ATTACKS):
            values = [
                results[(attack, detector_label)][metric_key] * 100
                for detector_label, _result_name in DETECTORS
            ]
            all_values.extend(values)
            bars = axis.bar(
                positions + (attack_index - 0.5) * bar_width,
                values, bar_width, label=attack_label, color=color,
            )
            for bar in bars:
                value = bar.get_height()
                axis.annotate(
                    f"{value:.1f}",
                    (bar.get_x() + bar.get_width() / 2, value),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=10.5,
                )
        axis.set_title(title, fontsize=11, fontweight="bold", pad=9)
        if axis is axes[0]:
            axis.set_ylabel("Rate (%)", fontsize=10)
        axis.set_xticks(
            positions, [label for label, _result_name in DETECTORS]
        )
        axis.tick_params(axis="both", labelsize=10)
        axis.grid(axis="y", alpha=0.25, linewidth=0.8)
        axis.set_axisbelow(True)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        upper = (
            min(100, max(10, math.ceil((max(all_values, default=0) + 8) / 10) * 10))
            if metric_key == "fpr" else 105
        )
        axis.set_ylim(0, upper)
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(
        handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.95),
        ncol=2, frameon=False, fontsize=10,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.86), w_pad=0.15)
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / "prv_performance_distribution.png"
    pdf_path = output_dir / "prv_performance_distribution.pdf"
    figure.savefig(png_path, dpi=600, bbox_inches="tight", facecolor="white")
    figure.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return png_path, pdf_path


def generate(
    experiment_root: Path, output_dir: Path, setting: str,
    attack_seeds: list[int], simulation_seed: str, warmup_seconds: int,
) -> tuple[Path, Path]:
    return plot(
        collect(
            experiment_root, setting, attack_seeds,
            simulation_seed, warmup_seconds,
        ),
        output_dir,
    )
