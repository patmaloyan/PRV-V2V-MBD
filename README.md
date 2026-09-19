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

# VeReMi NextGen

A comprehensive dataset and dataset generator for evaluating **Misbehavior Detection** in Vehicle-to-Everything (V2X) communication.

## Paper Reference
If you are using our dataset, please use the following citation:

> Hermann, A., Remmers, J. N.,  Eissermann, D., Erb, B and Kargl, F. 2026. VeReMi NextGen: A Dataset for Evaluating Misbehavior Detection Systems in VANETs. *Proceedings of the 2026 IEEE Vehicular Networking Conference Conference (Montreal, Canada, 2026)*.
```
@inproceedings{Hermann2026vereminextgen,
	author = {Hermann, Artur and Remmers, Jan Niklas and Eisermann, Dennis and Erb, Benjamin and Kargl, Frank},
	booktitle = {2026 {IEEE} {Vehicular} {Networking} {Conference} ({VNC})},
	date = {2026-06},
	location = {Montreal, Canada},
	title = {VeReMi {NextGen}: A {Dataset} for {Evaluating} {Misbehavior} {Detection} {Systems} in {VANETs}},
}
```

## Overview

VeReMi NextGen provides:

- **Dataset** with 15 attack types on V2X Cooperative Awareness Messages
- **Train/Val/Test Sets** for machine learning experiments
- **Plug'n Play Solution** for recreating the VeReMi Baseline with the option to change parameters
- **Attack Generator** to create custom attack scenarios 
- **CaTCH-MBD System** implementing CaTCH adopted to VeReMi NextGen
- **Parameter Optimization** for systematically obtaining the best thresholds  
  

## CPM-Assisted MBD Extension

This repository extends VeReMi NextGen with CPM-assisted misbehavior detection and the supporting simulation and evaluation pipeline.

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



## Repository Structure

```
VeReMi-NextGen/
├── Dataset/          # Download-Links for each set of VeReMi NextGen
├── Generator/        # Everything to recreate VeReMi NextGen or an own new Dataset
└── Documentation/    # Detailed documentation of VeReMi NextGen 
```

## Documentation

**[Full Documentation](./Documentation)**

- [Home](./Documentation) – Overview, message format, quick start
- [Getting Started](./Documentation/Getting%20Started) - Guide to run the simulation on you own machine
- [Architecture](./Documentation/Architecture) – System design & Overview
- [Processes](./Documentation/Processes) – Processes that occure during simulation
- [Evaluation](./Documentation/Evaluation) – Tools used for evluating VeReMi NextGen 
- [Post-Processing](./Documentation/Post-Processing) – Post-Processing pipeline for integrating MB and more
- [Eclipse MOSAIC](./Documentation/Eclipse%20MOSAIC) - Eclipse MOSAIC Simulation Setup
