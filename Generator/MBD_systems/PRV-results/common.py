"""Shared input paths and streaming metrics for PRV paper results."""

from __future__ import annotations

import json
from pathlib import Path

import ijson


SCENARIOS = (
    ("InTAS_urban_2AM_7200sec", "Urban, low (2 AM)"),
    ("InTAS_urban_7AM_300sec", "Urban, high (7 AM)"),
    ("InTAS_highway_2AM_7200sec", "Highway, low (2 AM)"),
    ("InTAS_highway_7AM_300sec", "Highway, high (7 AM)"),
)
ATTACKS = (
    ("randomPositionOffset", "Random Position Offset", "#7F9FBE"),
    ("constantPositionOffset", "Constant Position Offset", "#E67E22"),
)
DETECTORS = (
    ("CAM-only", "kalman_cam_only_no_catch"),
    ("PRV", "kalman_cam_cpm_prv_no_catch"),
)
COUNT_KEYS = ("tp", "tn", "fp", "fn")


class JsonNanToNullReader:
    """Replace bare ``NaN`` tokens while streaming detector JSON."""

    def __init__(self, source):
        self.source = source
        self.buffer = bytearray()
        self.carry = b""
        self.eof = False

    def read(self, size=-1):
        if size == 0:
            return b""
        if size < 0:
            data = self.carry + self.source.read()
            self.carry = b""
            return bytes(self.buffer) + data.replace(b"NaN", b"null")
        while len(self.buffer) < size and not self.eof:
            chunk = self.source.read(max(65_536, size))
            if not chunk:
                self.eof = True
                self.buffer.extend(self.carry.replace(b"NaN", b"null"))
                self.carry = b""
                break
            data = self.carry + chunk
            carry_size = (
                0 if data.endswith(b"NaN")
                else 2 if data.endswith(b"Na")
                else 1 if data.endswith(b"N")
                else 0
            )
            self.carry = data[-carry_size:] if carry_size else b""
            if carry_size:
                data = data[:-carry_size]
            self.buffer.extend(data.replace(b"NaN", b"null"))
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result


def load_manifest(experiment_root: Path) -> dict:
    path = experiment_root / "experiment.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_definition(manifest: dict, setting: str) -> dict:
    definition = manifest.get("scenarios", {}).get(setting)
    if definition is None:
        definition = manifest.get("analysis_datasets", {}).get(setting)
    if definition is None:
        raise KeyError(f"Unknown scenario in experiment.json: {setting}")
    return definition


def run_root(
    experiment_root: Path, attack: str, attack_seed: int,
    simulation_seed: str,
) -> Path:
    return (
        experiment_root / "attacks" / attack / str(attack_seed)
        / f"simulation-seed-{simulation_seed}"
    )


def debug_path(
    experiment_root: Path, attack: str, attack_seed: int,
    simulation_seed: str, setting: str, result_name: str,
) -> Path:
    return run_root(
        experiment_root, attack, attack_seed, simulation_seed
    ) / "results" / setting / result_name / "debug.json"


def empty_counts() -> dict[str, int]:
    return {key: 0 for key in COUNT_KEYS}


def add_counts(destination: dict[str, int], source: dict[str, int]) -> None:
    for key in COUNT_KEYS:
        destination[key] += source[key]


def count_debug_file(path: Path, cutoff_ns: int) -> dict[str, int]:
    if not path.is_file():
        raise FileNotFoundError(path)
    counts = empty_counts()
    with path.open("rb") as source:
        for row in ijson.items(JsonNanToNullReader(source), "item"):
            if str(row.get("message_type", "")).upper() != "CAM":
                continue
            if int(row["rcvTime"]) < cutoff_ns:
                continue
            attacker = int(row["attacker"])
            prediction = int(row["prediction"])
            if attacker == 1 and prediction == 1:
                counts["tp"] += 1
            elif attacker == 0 and prediction == 0:
                counts["tn"] += 1
            elif attacker == 0 and prediction == 1:
                counts["fp"] += 1
            elif attacker == 1 and prediction == 0:
                counts["fn"] += 1
    return counts


def metrics(counts: dict[str, int]) -> dict[str, float]:
    tp, tn, fp, fn = (counts[key] for key in COUNT_KEYS)
    return {
        "fpr": fp / (fp + tn) if fp + tn else 0.0,
        "tpr": tp / (tp + fn) if tp + fn else 0.0,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
    }
