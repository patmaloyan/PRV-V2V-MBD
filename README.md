# CPM-Assisted V2X Misbehavior Detection

This repository extends VeReMi NextGen with CPM-assisted misbehavior detection and a reproducible simulation, attack-generation, evaluation, and PRV-results pipeline.

## CPM-Assisted MBD Extension

### 1. Simulation changes

The final Eclipse MOSAIC configuration is located at [`Generator/simulation/mosaic-cpm-final`](./Generator/simulation/mosaic-cpm-final).

It retains the VeReMi NextGen MOSAIC structure and adds:

- **CPM communication:** vehicles build and broadcast at most one CPM per second as a MOSAIC `GenericV2xMessage`. CAM and CPM records use the same sender-state snapshot and are written to separate `cam`, `cpm`, and `ego` output folders.
- **Perception and occlusion:** CPM perception covers 360 degrees with an 80 m range. The scenario enables MOSAIC's wall index, and the application applies both `WallOcclusion` and `BoundingBoxOcclusion`, so buildings and intervening vehicles can hide perceived objects.
- **Communication-zone entry:** `just_entered_communication_zone` is `1` for the first two simulated seconds after a vehicle enters the configured area and `0` otherwise. It is included for CAM and CPM senders and receivers.
- **Windowed collection:** simulation time and geographic bounds are configurable. Radios and CPM perception are enabled only at the first in-window, in-area CAM transmission, while sampling, vehicle behavior, and pseudonym scheduling still begin at vehicle startup.
- **Pseudonyms and output performance:** pseudonym changes use a configurable simulation-time interval (100 s in the final scenario), with per-vehicle debug counts. Message records are appended as newline-delimited JSON during simulation to avoid repeatedly rewriting full files.

Key custom and modified files:

| File | Purpose |
| --- | --- |
| `applications/CamApp/src/main/java/entities/CpmPayload.java` | New serializable UTF-8 JSON payload used to carry CPMs in `GenericV2xMessage`. |
| `applications/CamApp/src/main/java/etsi/VehicleCamSendingApp.java` | CPM creation, transmission and reception; perception and occlusion; radio gating; `justEntered`; pseudonyms; and output routing. |
| `applications/CamApp/src/main/java/entities/VehicleAdditionalInformation.java` | Adds `justEnteredCommunicationZone` to CAM metadata. |
| `applications/CamApp/src/main/java/entities/ConfigSettings.java` | Defines collection time/area, pseudonym interval, output paths, and CAM settings. |
| `applications/CamApp/src/main/java/util/JSONParser.java` | Appends streamed message records and writes pseudonym debug counts. |
| `applications/CamApp/pom.xml` | Builds CamApp for Java 17 against Eclipse MOSAIC 25.0. |
| `scenarios/urban/application/EtsiApplication.json` | Selects the final collection window, area, pseudonym interval, and output locations. |
| `scenarios/urban/application/application_config.json` | Enables the 5 m vehicle grid, building-wall index, and bounded perception area. |
| `scenarios/urban/scenario_config.json` | Defines the 600 s InTAS run and active MOSAIC federates. |
| `scenarios/urban/application/CamApp-0.0.1.jar` | Packaged CamApp used by the scenario. |

### 2. MBD system

[`Generator/MBD_systems`](./Generator/MBD_systems) retains the VeReMi processing and CaTCH modules and adds the Kalman and CPM-assisted detectors:

- `kalman_filter.py` implements the motion and measurement model.
- `kalman_detector.py` implements CAM-only and CAM+CPM tracking and association.
- `cpm_detector.py` implements two-edge reciprocity and the final PRV trust detector.
- `main.py` runs detector types 2 (CAM-only), 3 (CAM+CPM), 4 (two-edge reciprocity), and 6 (PRV).

The [`PRV-results`](./Generator/MBD_systems/PRV-results) folder generates the PRV reciprocity-cases graph, CAM-only versus PRV performance distribution, and performance table across attacks and traffic scenarios. Run all three with:

```bash
python Generator/MBD_systems/PRV-results/generate.py <experiment-root>
```

Results are written to `Generator/MBD_systems/PRV-results/created`. The experiment root must contain `experiment.json` and its corresponding `attacks/` directory; the final layout is defined in Section 3.

### 3. Full pipeline and PRV results

[`Simulation-CPM-final`](./Simulation-CPM-final) contains the final experiment manifest and reproducible pipeline. The generated data are excluded from Git because of their size. From the repository root, run:

```bash
.venv/bin/pip install -r Simulation-CPM-final/requirements.txt
.venv/bin/python Simulation-CPM-final/run.py pipeline
```

The command runs the complete workflow:

1. Eclipse MOSAIC creates the four clean CAM/CPM simulation datasets.
2. `attackGenerator.py` creates `constantPositionOffset` and `randomPositionOffset` attack sets with seeds 1–3.
3. `Generator/MBD_systems/main.py` runs CAM-only (type 2) and PRV (type 6) detection on every attack set.
4. `PRV-results/generate.py` reads those detector results and creates the cases graph, performance distribution, and attack-performance table.

Completed outputs are validated and skipped when the pipeline is resumed. The generated dataset is not hosted because of its size. See [`Simulation-CPM-final/README.md`](./Simulation-CPM-final/README.md) for setup, individual stage commands, output layout, and dataset inquiries.

## VeReMi NextGen foundation

This work is based on VeReMi NextGen, a dataset and generator for evaluating misbehavior detection in V2X communication.

<p align="right">
  <i>Image: <code>ghcr.io/vs-uulm/veremi-nextgen:latest</code></i><br>
  <a href="https://zenodo.org/records/19665762" align="left">
    <img src="https://img.shields.io/badge/To%20The%20Downloads-Dataset-2ea44f?style=flat-square&logo=github" alt="To the downloads">
  </a>
  <img src="https://img.shields.io/badge/MOSAIC-25.2-blue?style=flat-square">
  <img src="https://img.shields.io/badge/SUMO-1.25.0-orange?style=flat-square">
  <img src="https://img.shields.io/badge/OMNeT%2B%2B-6.1-green?style=flat-square">
  <img src="https://img.shields.io/badge/INET-4.5.4-red?style=flat-square">
</p>

VeReMi NextGen provides its CAM dataset, attack generator, CaTCH-MBD system, parameter optimization, and train/validation/test sets.

### Paper reference

If you use the VeReMi NextGen dataset, cite:

> Hermann, A., Remmers, J. N., Eisermann, D., Erb, B. and Kargl, F. 2026. VeReMi NextGen: A Dataset for Evaluating Misbehavior Detection Systems in VANETs. *Proceedings of the 2026 IEEE Vehicular Networking Conference (Montreal, Canada, 2026)*.

```bibtex
@inproceedings{Hermann2026vereminextgen,
	author = {Hermann, Artur and Remmers, Jan Niklas and Eisermann, Dennis and Erb, Benjamin and Kargl, Frank},
	booktitle = {2026 {IEEE} {Vehicular} {Networking} {Conference} ({VNC})},
	date = {2026-06},
	location = {Montreal, Canada},
	title = {VeReMi {NextGen}: A {Dataset} for {Evaluating} {Misbehavior} {Detection} {Systems} in {VANETs}},
}
```

## Repository Structure

```
V2X-CPM-assisted-MBD/
├── Simulation-CPM-final/       # Full reproducible experiment pipeline
├── Generator/
│   ├── simulation/mosaic-cpm-final/
│   ├── attackGenerator/
│   └── MBD_systems/PRV-results/
├── Documentation/
└── Dataset/                    # Upstream VeReMi NextGen dataset links
```

## Documentation

**[Full Documentation](./Documentation)**

- [CPM-Assisted MBD](./Documentation/CPM-Assisted-MBD) – Full pipeline documentation
- [Home](./Documentation) – Overview, message format, quick start
- [Getting Started](./Documentation/Getting%20Started) - Guide to run the simulation on your own machine
- [Architecture](./Documentation/Architecture) – System design & Overview
- [Processes](./Documentation/Processes) – Processes that occure during simulation
- [Evaluation](./Documentation/Evaluation) – Tools used for evaluating VeReMi NextGen
- [Post-Processing](./Documentation/Post-Processing) – Post-Processing pipeline for integrating MB and more
- [Eclipse MOSAIC](./Documentation/Eclipse%20MOSAIC) - Eclipse MOSAIC Simulation Setup
