"""Create the paper PRV reciprocity-case graph without worker processes."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


MBD_DIR = Path(__file__).resolve().parents[1]
if str(MBD_DIR) not in sys.path:
    sys.path.insert(0, str(MBD_DIR))

from cpm_detector import INTERVAL_NS, PrvDetector  # noqa: E402
from data_structures import Parameters  # noqa: E402
from kalman_detector import evaluation_receiver_ids, load_json_list  # noqa: E402
from common import load_manifest, run_root, scenario_definition  # noqa: E402


CASES = ("mutual", "a_to_b_only", "b_to_a_only")
GROUPS = ("benign", "attacker")
CASE_STYLES = {
    "mutual": ("Mutual (+2)", "#739DC3"),
    "a_to_b_only": (r"$A\rightarrow B$ only (-1)", "#DD7774"),
    "b_to_a_only": (r"$B\rightarrow A$ only (0)", "#C8C3C0"),
}
DEFAULT_SETTINGS = (
    ("InTAS_urban_2AM_7200sec", "Low density"),
    ("InTAS_urban_7AM_300sec", "High density"),
)


class ReciprocityCaseCollector(PrvDetector):
    """Count evidence-direction cases immediately before PRV scores a bucket."""

    def __init__(self, identity_by_alias: dict, minimum_bucket: int):
        super().__init__(Parameters(), catch_enabled=False)
        self.identity_by_alias = identity_by_alias
        self.minimum_bucket = minimum_bucket
        self.subject_by_track = {}
        self.case_counts = defaultdict(Counter)

    def track_id(self, track, create_trust=False):
        track_id = super().track_id(track, create_trust)
        identity = self.identity_by_alias.get(str(track.station_alias))
        if identity is not None:
            self.subject_by_track[track_id] = identity["sender_id"]
        return track_id

    def close_current_bucket(self):
        accepted = {
            track_id: state.accepted for track_id, state in self.trust.items()
        }
        if self.current_bucket >= self.minimum_bucket:
            for subject_id in self.trust:
                subject = self.subject_by_track.get(subject_id)
                if subject is None:
                    continue
                for counterpart_id, counterpart_accepted in accepted.items():
                    if counterpart_id == subject_id or not counterpart_accepted:
                        continue
                    a_to_b = self.bucket_edges.get((subject_id, counterpart_id))
                    b_to_a = self.bucket_edges.get((counterpart_id, subject_id))
                    if a_to_b is not None and b_to_a is not None:
                        case = "mutual"
                    elif a_to_b is not None:
                        case = "a_to_b_only"
                    elif b_to_a is not None:
                        case = "b_to_a_only"
                    else:
                        continue
                    self.case_counts[subject][case] += 1
        return super().close_current_bucket()


def identity_map(cam_paths) -> dict:
    identities = {}
    for path in cam_paths:
        for message in load_json_list(path):
            alias = str(message.get("sender_alias", 0))
            identities[alias] = {
                "sender_id": str(message.get("sender_id", alias)),
                "attacker": int(message.get("attacker", 0)),
            }
    return identities


def collect_attack(input_folder: Path, minimum_time_ns: int) -> dict:
    cam_paths = {
        path.stem: path for path in (input_folder / "cam").glob("*.json")
    }
    cpm_paths = {
        path.stem: path for path in (input_folder / "cpm").glob("*.json")
    }
    receiver_ids = evaluation_receiver_ids(
        input_folder, sorted(set(cam_paths) | set(cpm_paths))
    )
    identities = identity_map(cam_paths.values())
    by_subject = defaultdict(Counter)
    for index, receiver_id in enumerate(receiver_ids, 1):
        collector = ReciprocityCaseCollector(
            identities, minimum_time_ns // INTERVAL_NS
        )
        collector.process_receiver(
            cam_paths.get(receiver_id),
            cpm_paths.get(receiver_id),
            input_folder / "ego" / f"{receiver_id}.json",
        )
        for subject, counts in collector.case_counts.items():
            by_subject[subject].update(counts)
        if index % 10 == 0 or index == len(receiver_ids):
            print(
                f"[cases] processed {index}/{len(receiver_ids)} receivers",
                flush=True,
            )
    attacker_by_subject = {
        value["sender_id"]: value["attacker"] for value in identities.values()
    }
    return group_counts(by_subject, attacker_by_subject)


def group_counts(by_subject: dict, attacker_by_subject: dict) -> dict:
    grouped = {}
    for attacker, group_name in ((0, "benign"), (1, "attacker")):
        subjects = [
            subject for subject in by_subject
            if attacker_by_subject.get(subject) == attacker
        ]
        totals = Counter()
        for subject in subjects:
            totals.update(by_subject[subject])
        grouped[group_name] = {
            "vehicles": len(subjects),
            "cases": {case: totals[case] for case in CASES},
        }
    return grouped


def pool_seed_groups(seed_groups: list[dict]) -> dict:
    pooled = {}
    for group_name in GROUPS:
        totals = Counter()
        vehicles = 0
        for grouped in seed_groups:
            vehicles += grouped[group_name]["vehicles"]
            totals.update(grouped[group_name]["cases"])
        pooled[group_name] = {
            "vehicles": vehicles,
            "cases": {case: totals[case] for case in CASES},
        }
    return pooled


def percentages(grouped: dict, group_name: str) -> np.ndarray:
    values = np.array(
        [grouped[group_name]["cases"][case] for case in CASES], dtype=float
    )
    total = values.sum()
    return values * (100.0 / total) if total else values


def collect(
    experiment_root: Path, attack_seeds: list[int], simulation_seed: str,
    warmup_seconds: int,
) -> dict:
    manifest = load_manifest(experiment_root)
    results = {}
    for setting, _panel_title in DEFAULT_SETTINGS:
        start_s = int(scenario_definition(manifest, setting)["communication_start"])
        minimum_time_ns = (start_s + warmup_seconds) * 1_000_000_000
        groups = []
        for attack_seed in attack_seeds:
            input_folder = run_root(
                experiment_root, "constantPositionOffset", attack_seed,
                simulation_seed,
            ) / setting
            if not input_folder.is_dir():
                raise FileNotFoundError(input_folder)
            print(f"[cases] {setting}, attack seed {attack_seed}", flush=True)
            groups.append(collect_attack(input_folder, minimum_time_ns))
        results[setting] = pool_seed_groups(groups)
    return results


def plot(results: dict, output_dir: Path) -> tuple[Path, Path]:
    with plt.rc_context({"font.size": 10, "pdf.fonttype": 42}):
        figure, axes = plt.subplots(
            1, 2, figsize=(7.16, 3.25), sharey=True,
            gridspec_kw={"wspace": 0.10},
        )
        bar_x = np.array([0.0, 0.72])
        handles = []
        for axis, (setting, panel_title) in zip(axes, DEFAULT_SETTINGS):
            bottoms = np.zeros(len(bar_x))
            for case in CASES:
                values = [
                    percentages(results[setting], group_name)[CASES.index(case)]
                    for group_name in GROUPS
                ]
                label, color = CASE_STYLES[case]
                bars = axis.bar(
                    bar_x, values, width=0.55, bottom=bottoms,
                    color=color, edgecolor="#333333", linewidth=0.45,
                    label=label, zorder=3,
                )
                if axis is axes[0]:
                    handles.append(bars[0])
                for x_value, value, bottom in zip(bar_x, values, bottoms):
                    if value >= 5.0:
                        axis.text(
                            x_value, bottom + value / 2, f"{value:.1f}",
                            ha="center", va="center", fontsize=9.5,
                        )
                bottoms += np.asarray(values)
            axis.set_title(panel_title, pad=5, fontweight="bold")
            axis.set_xticks(bar_x, ("Benign", "Attacker"))
            axis.set_ylim(0, 100)
            axis.set_yticks(np.arange(0, 101, 20))
            axis.grid(axis="y", color="#D9D9D9", linewidth=0.55, zorder=0)
            axis.spines["top"].set_visible(False)
            axis.spines["right"].set_visible(False)
        axes[0].set_ylabel("Share of reciprocity cases (%)")
        figure.legend(
            handles, [CASE_STYLES[case][0] for case in CASES],
            loc="upper center", bbox_to_anchor=(0.5, 0.985),
            ncol=3, frameon=False,
        )
        figure.subplots_adjust(
            left=0.09, right=0.995, top=0.83, bottom=0.14
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        png_path = output_dir / "prv_cases_graph.png"
        pdf_path = output_dir / "prv_cases_graph.pdf"
        figure.savefig(png_path, dpi=600, bbox_inches="tight", pad_inches=0.02)
        figure.savefig(pdf_path, bbox_inches="tight", pad_inches=0.02)
        plt.close(figure)
    return png_path, pdf_path


def generate(
    experiment_root: Path, output_dir: Path, attack_seeds: list[int],
    simulation_seed: str, warmup_seconds: int,
) -> tuple[Path, Path]:
    return plot(
        collect(
            experiment_root, attack_seeds, simulation_seed, warmup_seconds
        ),
        output_dir,
    )
