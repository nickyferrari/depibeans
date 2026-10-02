# DepiBeans

DepiBeans is the Python controller and web interface for DEPI plant-imaging
chambers (chlorophyll fluorescence imaging under programmed light), written for
the Walker Lab at Michigan State University.

**This is a published copy of the source, not the working repository.** It was
made from commit `a54763b` (2026-09-24) of the private repository.

- Development history, deployment records, machine setup scripts, the lab's
  web-hosting code and the gas-mixer screens are left out.
- Lab web addresses, account paths, e-mail addresses and device serial numbers
  are replaced by example values (`portal.example.org`, `/home/chamber`,
  `user@example.edu`). As published, this copy does not connect to any
  instrument.
- Do not deploy from this copy.

Having the source does not mean every hardware operation has passed
commissioning. `docs/REPLACEMENT-ACCEPTANCE.md` lists the acceptance work that
was still open on the date above.

## What is here

| Area | Source |
| --- | --- |
| Controller HTTP API, scheduling, manual operations | `depibeans/control_app.py` |
| Experiment plans and the execution journal | `depibeans/scripting.py`, `depibeans/execution.py` |
| Experiments, protocols, versions and saved schedules | `depibeans/workbench.py` |
| Camera and FPGA adapters | `depibeans/avt_camera.py`, `chamber_adapter.py`, `chamber_fpga.py`, `linux_adept.py` |
| Waveforms, lighting and calibration | `depibeans/camera_protocol.py`, `lighting.py`, `calibration.py` |
| Fluorescence results (F0, Fm, Fv/Fm, NPQ, ΦII) | `depibeans/fluorescence.py`, `measurement_images.py` |
| Leaf regions | `depibeans/leaf_segmentation.py` |
| Live camera preview | `depibeans/live_view.py` |
| Reports, image downloads and ZIP exports | `depibeans/run_exports.py`, `frame_preview.py` |
| Sign-in, invitations, sessions and access checks on the chamber computer | `depibeans/portal.py` |
| Outbound connection from the chamber computer | `depibeans/portal_connection.py` |
| Browser interface | `depibeans/ui/dist/` (the experiment editor is built from `depibeans/ui/src/editor/`) |
| Windows desktop lighting application | `depibeans/desktop.py`, `native.py` |
| Translated legacy experiments and their compiled plans | `examples/research/` |
| Hardware profiles (examples) | `profiles/` |
| Tests | `tests/` |

## Run it without hardware

Python 3.10 or later, on macOS or Linux.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[portal]'
python tools/dev_preview.py
```

Open `http://127.0.0.1:8765`. This entry point uses the real interface, the
experiment workspace and a simulator. It refuses physical execution and does
not look for devices. Its data goes into `.development/data/`.

```sh
python -m unittest discover -s tests
node --test tests/js/*.test.*
```

The fluorescence and leaf-region code needs the optional analysis packages:
`python -m pip install -e '.[analysis]'`. One test module
(`tests/test_compare_metric_regions.py`) also needs `pytest`.

## Changing the experiment editor

The editor is written as small modules in `depibeans/ui/src/editor/`.
`tools/build_ui.py` joins them into `depibeans/ui/dist/app.js`; edit the
modules, run the build, and keep both. See `docs/DEVELOPMENT-AND-RELEASES.md`.

```sh
python3 tools/build_ui.py
python3 -m unittest tests.test_ui_build
```

## Hardware

The camera needs Allied Vision Vimba X with VmbPy and its GigE transport. The
FPGA needs the Digilent Adept runtime and device permissions. The Windows
desktop application has its own native library. Vendor installers and
binaries are not included.

The files in `profiles/` are examples. A profile describes one machine; do not
assume one fits another chamber.

## Documents

- Methods: `docs/FLUORESCENCE-METRIC-PROVENANCE.md`, `docs/LEAF-SEGMENTATION.md`,
  `docs/SEGMENTATION-EVALUATION-METHOD.md`
- Lighting hardware: `docs/BIGFOOT-LIGHTING-MAP.md`, `docs/BASEMENT-MANUAL-LIGHTS.md`
- Design and status: `docs/ARCHITECTURE-REVIEW.md`, `docs/MIGRATION.md`,
  `docs/LEGACY-PARITY.md`, `docs/REPLACEMENT-ACCEPTANCE.md`
- Release notes: `docs/RELEASE-*.md`

Some documents mention files that are not in this copy (hosting, relay, mixer,
handoff records).

## Licence

No licence has been chosen for this code. Until one is added, the usual
copyright rules apply. The IBM Plex Sans font carries its own licence,
`licenses/IBM-Plex-Sans-OFL.txt`.
