# Leaf segmentation

Completed fluorescence observations are segmented automatically when the optional analysis dependencies are installed. The portal keeps the heatmap as the base image and displays the detected leaf edge in white, the conservative measurement boundary in orange, and stable leaf numbers by default. Whole-image fluorescence results remain available if segmentation cannot run.

The prototype creates a review directory from one two-dimensional TIFF. It preserves the source file and writes:

- `heatmap.png`, a false-color rendering of the source values;
- `leaf-overlay.png`, candidate boundaries and region numbers;
- `leaf-labels.tif`, the candidate integer label mask;
- `leaf-labels-inset-8px.tif`, the conservative measurement mask by default;
- `segmentation.json`, parameters, regions, warnings, and source SHA-256;
- `index.html`, a side-by-side local review page.

## Run a review

Install the optional analysis dependencies:

```sh
python -m pip install -e '.[analysis]'
```

Generate a review from a background-corrected Fm reference or another two-dimensional TIFF:

```sh
python tools/preview_leaf_segmentation.py /path/to/reference-Fm.tif --output /path/to/review
```

Open the generated `index.html` locally. The white line is the detected boundary; the orange line is the measurement boundary after the default 8-pixel inset. Adjusting `--inset-pixels`, `--min-area`, `--smoothing-sigma`, or `--separation-prominence` creates another candidate review; it does not alter the DEPI observation or portal. Lower separation prominence detects more watershed centers; higher values merge weakly separated centers.

The inset is calculated independently inside each labelled region. It discards pixels near background and shared leaf boundaries while preserving the original segmentation for review and provenance. Retained area is always reported because a fixed inset removes a larger proportion of narrow or partial leaves.

## Compare fluorescence by leaf

For a local completed-observation directory containing `fluorescence.json` and its referenced TIFFs:

```sh
python tools/analyze_leaf_fluorescence.py /path/to/observation \
  --output /path/to/results --selected-inset 8
```

This writes detected and inset label TIFFs, a long-form CSV, a JSON report, a Markdown summary, and a comparison figure. Missing measurements remain missing; for example, ΦII is not calculated when the observation has no Fs acquisition.

To add the accepted default segmentation to an existing completed observation and update its `fluorescence.json` manifest:

```sh
python tools/backfill_leaf_segmentation.py /path/to/observation
```

This writes label TIFFs under the observation's `analysis/` directory and adds per-leaf mean, median, standard deviation, valid-pixel count, and retained-area metadata. The source fluorescence TIFFs are unchanged.

## Current algorithm

The candidate algorithm uses a finite-pixel mask when a DEPI image already contains a substantial NaN background. For ordinary full-frame images it uses Gaussian smoothing and an Otsu threshold. Morphological cleanup removes small objects and holes, and a distance-transform watershed attempts to separate touching regions. Regions are numbered by visual row and then from left to right.

This algorithm has only been checked against synthetic shapes. Its output is not accepted for scientific analysis or production use.

## Acceptance work

Before any portal integration, collect representative real DEPI images with separated, touching, dim, bright, truncated, and obstructed leaves. Manually outline a small reference set and compare the candidates with those masks. The acceptance review should cover false splits, merged leaves, background objects, edge behavior, stability across measurement phases, and a Dice target of at least 0.90 for clearly separated leaves.

Portal integration resumes only after the overlays look acceptable to the DEPI team. Measuring flashes and saturation pulses on the migrated testbed still require separate physical and scientific validation.

## Checks

Run the focused local tests with:

```sh
python -m unittest -v tests.test_leaf_segmentation
```

The tests cover deterministic synthetic regions, touching shapes, noise, edge warnings, dim valid regions, invalid pixels, translation, generated review files, and preservation of the source TIFF.
