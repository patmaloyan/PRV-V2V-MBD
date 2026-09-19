# CPM simulation and evaluation

This folder defines the final reproducible experiment. Generated datasets are
kept here locally but are excluded from Git because of their size.

## Setup

Requirements are Docker, Java 17, Maven, Python 3.10 or newer, and sufficient
disk space. From the repository root, create an environment and install the
Python dependencies:

```bash
python -m venv .venv
.venv/bin/pip install -r Simulation-CPM-final/requirements.txt
docker pull ghcr.io/vs-uulm/veremi-nextgen:recreation@sha256:cdddb6e0ddcb350f9fb3602128b8fa046ecc0b5699082566cdb4ff01db68d4b8
```

## Create the dataset

Run the complete pipeline from the repository root:

```bash
.venv/bin/python Simulation-CPM-final/run.py pipeline
```

The command runs these stages sequentially and resumes completed work:

1. Simulate the four traffic settings in `experiment.json` with simulation seed 1.
2. Generate `constantPositionOffset` and `randomPositionOffset` datasets with attack seeds 1, 2, and 3.
3. Run `Generator/MBD_systems/main.py` for CAM-only (type 2) and PRV (type 6) detection on every attack set.
4. Pass this experiment folder to `Generator/MBD_systems/PRV-results/generate.py` to create the cases graph, performance distribution, and attack-performance table.

Individual stages can also be run with `simulate`, `attack`, or `evaluate`.
Use `run.py <stage> --help` for filters such as settings or attack seeds.

## Output layout

```text
Simulation-CPM-final/
├── seeded-simulations/1/<setting>/{cam,cpm,ego}/
└── attacks/<attack>/<attack-seed>/simulation-seed-1/
    ├── <setting>/{cam,cpm,ego}/
    └── results/<setting>/<detector>/
```

Paper figures and the LaTeX table are written to
`Generator/MBD_systems/PRV-results/created/`.

## Dataset availability

The generated dataset is not committed or hosted because of its size. Use the
pipeline above to reproduce it locally. For dataset inquiries, contact
[pmaloyan@gmail.com](mailto:pmaloyan@gmail.com).
