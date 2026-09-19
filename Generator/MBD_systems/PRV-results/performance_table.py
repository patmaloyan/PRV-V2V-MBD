"""Create the paper LaTeX table across attacks and scenarios."""

from __future__ import annotations

from pathlib import Path

from common import (
    ATTACKS, DETECTORS, SCENARIOS, add_counts, count_debug_file, debug_path,
    empty_counts, load_manifest, metrics, scenario_definition,
)


def collect(
    experiment_root: Path, attack_seeds: list[int], simulation_seed: str,
    warmup_seconds: int,
) -> dict:
    manifest = load_manifest(experiment_root)
    pooled = {}
    for setting, scenario_label in SCENARIOS:
        start_s = int(scenario_definition(manifest, setting)["communication_start"])
        cutoff_ns = (start_s + warmup_seconds) * 1_000_000_000
        for attack, _attack_label, _color in ATTACKS:
            for detector_label, result_name in DETECTORS:
                counts = empty_counts()
                for attack_seed in attack_seeds:
                    path = debug_path(
                        experiment_root, attack, attack_seed, simulation_seed,
                        setting, result_name,
                    )
                    print(f"[table] {path}", flush=True)
                    add_counts(counts, count_debug_file(path, cutoff_ns))
                pooled[(scenario_label, attack, detector_label)] = counts
    return pooled


def tabular_lines(pooled: dict, attack: str) -> list[str]:
    lines = [
        r"\begin{tabular}{@{}llrrrr@{}}",
        r"\toprule",
        r"Scenario & Method & FPR (\%) & TPR (\%) & Precision (\%) & F1 (\%) \\",
        r"\midrule",
    ]
    for scenario_index, (_setting, scenario_label) in enumerate(SCENARIOS):
        lines.append(rf"\multirow{{2}}{{*}}{{{scenario_label}}}")
        for detector_label, _result_name in DETECTORS:
            counts = pooled[(scenario_label, attack, detector_label)]
            values = metrics(counts)
            lines.append(
                "% pooled counts: "
                + ", ".join(
                    f"{key.upper()}={counts[key]}"
                    for key in ("tp", "fp", "tn", "fn")
                )
            )
            lines.append(
                f"  & {detector_label:<8} & {values['fpr'] * 100:.2f} "
                f"& {values['tpr'] * 100:.2f} & {values['precision'] * 100:.2f} "
                f"& {values['f1'] * 100:.2f} \\\\"
            )
        if scenario_index != len(SCENARIOS) - 1:
            lines.append(r"\addlinespace[2pt]")
    lines.extend((r"\bottomrule", r"\end{tabular}"))
    return lines


def render(
    pooled: dict, attack_seeds: list[int], warmup_seconds: int,
) -> str:
    seed_text = ", ".join(str(seed) for seed in attack_seeds)
    pieces = [
        r"% Requires \usepackage{booktabs,multirow,graphicx}",
        "% Metrics use pooled TP/FP/TN/FN counts rather than seed averages.",
        r"\begin{table*}[t]",
        r"\centering",
    ]
    for attack_index, (attack, attack_label, _color) in enumerate(ATTACKS):
        if attack_index:
            pieces.append(r"\hfill")
        pieces.extend((
            r"\begin{minipage}[t]{0.49\textwidth}",
            r"\centering",
            rf"\caption{{{attack_label} performance after a {warmup_seconds}-s warm-up; attack seeds {seed_text}.}}",
            r"\resizebox{\linewidth}{!}{%",
        ))
        pieces.extend(tabular_lines(pooled, attack))
        pieces.extend(("}", r"\end{minipage}"))
    pieces.extend((r"\end{table*}", ""))
    return "\n".join(pieces)


def generate(
    experiment_root: Path, output_dir: Path, attack_seeds: list[int],
    simulation_seed: str, warmup_seconds: int,
) -> Path:
    pooled = collect(
        experiment_root, attack_seeds, simulation_seed, warmup_seconds
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "prv_performance_across_attacks.tex"
    output.write_text(
        render(pooled, attack_seeds, warmup_seconds), encoding="utf-8"
    )
    return output
