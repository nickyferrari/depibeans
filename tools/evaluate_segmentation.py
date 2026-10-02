"""Evaluate the deployed leaf segmentation on LOCAL copies of saved observations.

Read-only with respect to the observations. The deployed code is imported from
``depibeans.leaf_segmentation``; nothing is copied or modified.

For every observation the script segments the reference image the pipeline
would choose (``_reference_point``) and the other candidate references (Fm,
first Fm', masked reference-Fm), writes three-panel review figures, renders the
label file stored in the observation next to a fresh run, and measures how
stable the regions are between references and between observations.

The figures must be LOOKED AT by a person; the numbers here only describe
agreement between segmentations, never correctness against the plants.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parents[1]
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from depibeans.leaf_segmentation import ALGORITHM_VERSION, _reference_point, inset_labels, segment_leaves


def _read(path):
    import numpy as np
    import tifffile

    return np.asarray(tifffile.imread(path)).squeeze()


def candidates(observation, manifest):
    """Return [(name, path, is_pipeline_choice)] without duplicates of the same file."""
    metric, _, chosen = _reference_point(manifest, observation)
    found = [(f"pipeline-{metric}", chosen, True)]
    points = {m: [observation / p["file"] for p in d.get("points", []) if p.get("file")] for m, d in manifest.get("metrics", {}).items()}
    extra = [("Fm", (points.get("Fm") or [None])[0]), ("first-Fm_prime", (points.get("Fm_prime") or [None])[0])]
    extra += [("reference-Fm", path) for path in sorted((observation / "analysis").glob("*-reference-Fm.tif"))[:1]]
    for name, path in extra:
        if path and path.is_file() and path.resolve() != chosen.resolve():
            found.append((name, path, False))
    return found


def _stretch(image):
    """Square-root stretch between the 0.5th and 99.8th percentile; NaN is black."""
    import numpy as np

    finite = np.isfinite(image)
    low, high = np.percentile(image[finite], [0.5, 99.8])
    scaled = np.clip((np.where(finite, image, low) - low) / max(high - low, 1e-9), 0, 1)
    return np.sqrt(scaled)


def _label_rgb(labels, gray):
    import numpy as np
    from matplotlib import colormaps

    palette = colormaps["tab20"](np.arange(20))[:, :3]
    rgb = np.repeat((gray * 0.55)[..., None], 3, axis=2)
    for identifier in np.unique(labels[labels > 0]):
        selected = labels == identifier
        rgb[selected] = 0.45 * rgb[selected] + 0.55 * palette[(int(identifier) - 1) % 20]
    return rgb


def _boundaries(labels):
    import numpy as np

    edge = np.zeros(labels.shape, dtype=bool)
    edge[:-1] |= labels[:-1] != labels[1:]
    edge[:, :-1] |= labels[:, :-1] != labels[:, 1:]
    return edge


def _annotate(axis, labels):
    from scipy import ndimage as ndi

    identifiers = [int(v) for v in sorted(set(labels[labels > 0].tolist()))]
    for identifier, (row, col) in zip(identifiers, ndi.center_of_mass(labels > 0, labels, identifiers)):
        axis.text(col, row, str(identifier), color="white", fontsize=11, fontweight="bold", ha="center", va="center",
                  bbox={"facecolor": "black", "alpha": 0.6, "pad": 1.5, "edgecolor": "none"})


def figure(image, panels, title, destination):
    """panels: [(caption, labels)] drawn after the stretched grayscale source."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import ndimage as ndi

    gray = _stretch(image.astype("float32"))
    fig, axes = plt.subplots(1, 1 + len(panels), figsize=(7.2 * (1 + len(panels)), 5.9), constrained_layout=True)
    axes[0].imshow(gray, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
    axes[0].set_title("source, sqrt stretch (NaN = black)")
    for axis, (caption, labels) in zip(axes[1:], panels):
        rgb = _label_rgb(labels, gray)
        rgb[ndi.binary_dilation(_boundaries(labels), iterations=1)] = (1, 1, 1)
        axis.imshow(rgb, interpolation="nearest")
        _annotate(axis, labels)
        axis.set_title(caption)
    for axis in axes:
        axis.set_xticks([]); axis.set_yticks([])
    fig.suptitle(title)
    fig.savefig(destination, dpi=110)
    plt.close(fig)


def region_table(labels):
    from skimage import measure

    return {int(r.label): {"area": int(r.area), "centroid": [float(r.centroid[0]), float(r.centroid[1])]} for r in measure.regionprops(labels)}


def match(labels_a, labels_b):
    """Optimal one-to-one matching of regions by IoU (Hungarian)."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    a, b = region_table(labels_a), region_table(labels_b)
    ids_a, ids_b = sorted(a), sorted(b)
    union_fg = int(((labels_a > 0) | (labels_b > 0)).sum())
    result = {"regions_a": len(ids_a), "regions_b": len(ids_b),
              "foreground_iou": float(((labels_a > 0) & (labels_b > 0)).sum() / union_fg) if union_fg else None,
              "pairs": [], "unmatched_a": [], "unmatched_b": []}
    if not ids_a or not ids_b:
        result["unmatched_a"], result["unmatched_b"] = ids_a, ids_b
        return result
    pair_counts = np.zeros((int(labels_a.max()) + 1, int(labels_b.max()) + 1), dtype=np.int64)
    np.add.at(pair_counts, (labels_a.ravel(), labels_b.ravel()), 1)
    iou = np.zeros((len(ids_a), len(ids_b)))
    for i, ia in enumerate(ids_a):
        for j, ib in enumerate(ids_b):
            inter = pair_counts[ia, ib]
            if inter:
                iou[i, j] = inter / (a[ia]["area"] + b[ib]["area"] - inter)
    rows, cols = linear_sum_assignment(-iou)
    matched_a, matched_b = set(), set()
    for i, j in zip(rows, cols):
        if iou[i, j] <= 0:
            continue
        ia, ib = ids_a[i], ids_b[j]
        matched_a.add(ia); matched_b.add(ib)
        shift = float(np.hypot(*(np.subtract(a[ia]["centroid"], b[ib]["centroid"]))))
        result["pairs"].append({"id_a": ia, "id_b": ib, "same_id": ia == ib, "iou": float(iou[i, j]),
                                "area_a": a[ia]["area"], "area_b": b[ib]["area"],
                                "area_change_fraction": float((b[ib]["area"] - a[ia]["area"]) / a[ia]["area"]),
                                "centroid_shift_pixels": shift})
    result["unmatched_a"] = [v for v in ids_a if v not in matched_a]
    result["unmatched_b"] = [v for v in ids_b if v not in matched_b]
    ious = [p["iou"] for p in result["pairs"]]
    result["summary"] = {
        "matched_pairs": len(ious), "pairs_iou_at_least_0.8": int(sum(v >= 0.8 for v in ious)),
        "pairs_iou_below_0.5": int(sum(v < 0.5 for v in ious)),
        "median_iou": float(np.median(ious)) if ious else None, "min_iou": float(min(ious)) if ious else None,
        "pairs_with_same_id": int(sum(p["same_id"] for p in result["pairs"])),
        "pairs_same_id_and_iou_at_least_0.8": int(sum(p["same_id"] and p["iou"] >= 0.8 for p in result["pairs"])),
        "max_centroid_shift_pixels": max((p["centroid_shift_pixels"] for p in result["pairs"]), default=None),
    }
    return result


def evaluate(observation, output, *, sensitivity=False):
    import numpy as np
    import tifffile

    observation = Path(observation).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((observation / "fluorescence.json").read_text())
    report = {"observation": observation.name, "deployed_algorithm_version": ALGORITHM_VERSION, "candidates": {}, "comparisons": {}}
    label_sets = {}
    for name, path, chosen in candidates(observation, manifest):
        image = _read(path)
        labels, meta = segment_leaves(image)
        inset = inset_labels(labels, 8)
        label_sets[name] = labels
        tifffile.imwrite(output / f"labels-{name}.tif", labels.astype(np.uint16))
        finite_fraction = float(np.isfinite(image).mean())
        figure(image, [(f"deployed v{ALGORITHM_VERSION}: {len(meta['regions'])} regions", labels), ("8 px inset measurement labels", inset)],
               f"{observation.name[:12]} · {name} · {path.name} · finite {finite_fraction:.1%}", output / f"segmentation-{name}.png")
        report["candidates"][name] = {
            "file": str(path.relative_to(observation)), "pipeline_choice": chosen, "finite_fraction": finite_fraction,
            "foreground_path": "finite-pixel mask (NaN background)" if finite_fraction < 0.95 else "threshold",
            "threshold": meta.get("threshold"), "status": meta.get("status"), "region_count": len(meta.get("regions", [])),
            "regions": [{k: r[k] for k in ("id", "area_pixels", "centroid", "touches_edge", "solidity", "warnings")} for r in meta.get("regions", [])],
            "inset_retained_fraction": {int(i): float((inset == i).sum() / max(1, (labels == i).sum())) for i in np.unique(labels[labels > 0])},
            "foreground_fraction_of_frame": float((labels > 0).mean()),
        }
    pipeline = next(name for name in label_sets if name.startswith("pipeline-"))
    report["pipeline_choice"] = pipeline

    stored = manifest.get("segmentation") or {}
    stored_path = observation / (stored.get("detected_label_file") or "analysis/leaf-labels-detected.tif")
    if stored_path.is_file():
        stored_labels = _read(stored_path).astype(np.int32)
        reference_image = _read(next(path for name, path, _ in candidates(observation, manifest) if name == pipeline))
        figure(reference_image, [(f"STORED label file (algorithm {stored.get('algorithm_version')}, reference {stored.get('reference_metric')})", stored_labels),
                                 (f"fresh deployed v{ALGORITHM_VERSION} on {pipeline}", label_sets[pipeline])],
               f"{observation.name[:12]} · stored labels vs fresh run", output / "stored-vs-fresh.png")
        report["stored"] = {"algorithm_version": stored.get("algorithm_version"), "reference_metric": stored.get("reference_metric"),
                            "reference_file": stored.get("reference_file"), "region_count": int(len(np.unique(stored_labels)) - 1),
                            "identical_to_fresh": bool(np.array_equal(stored_labels, label_sets[pipeline])),
                            "would_be_reused_by_deployed_code": stored.get("algorithm_version") == ALGORITHM_VERSION}
        report["comparisons"][f"stored__vs__{pipeline}"] = match(stored_labels, label_sets[pipeline])
        label_sets["stored"] = stored_labels
    names = [n for n in label_sets if n != "stored"]
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            report["comparisons"][f"{first}__vs__{second}"] = match(label_sets[first], label_sets[second])

    if sensitivity:
        image = _read(next(path for name, path, _ in candidates(observation, manifest) if name == pipeline))
        sweep = []
        for parameter, values in (("separation_prominence", (0.1, 0.15, 0.2, 0.3, 0.4)), ("separation_percentile", (88.0, 90.0, 93.0, 95.0, 97.0))):
            for value in values:
                labels, meta = segment_leaves(image, **{parameter: value})
                sweep.append({"parameter": parameter, "value": value, "region_count": len(meta["regions"]),
                              "vs_default": match(label_sets[pipeline], labels)["summary"]})
        report["sensitivity"] = sweep
    (output / "segmentation-evaluation.json").write_text(json.dumps(report, indent=2))
    return report, label_sets


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("observations", nargs="+", type=Path, help="LOCAL observation directories (fluorescence.json + TIFFs)")
    parser.add_argument("--output", type=Path, required=True, help="Output directory outside the observations and outside tracked repository paths")
    parser.add_argument("--sensitivity", action="store_true", help="Also sweep separation_prominence and separation_percentile")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    for observation in args.observations:
        if output.is_relative_to(observation.resolve()):
            parser.error("Output must not be inside an observation directory")
    results = {}
    for observation in args.observations:
        report, label_sets = evaluate(observation, output / observation.name[:12], sensitivity=args.sensitivity)
        results[observation.name[:12]] = (report, label_sets)
        print(observation.name[:12], {name: item["region_count"] for name, item in report["candidates"].items()}, "stored:", report.get("stored", {}).get("region_count"))
    names = list(results)
    cross = {}
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            for kind in ("pipeline", "stored"):
                a = results[first][1].get(results[first][0]["pipeline_choice"] if kind == "pipeline" else "stored")
                b = results[second][1].get(results[second][0]["pipeline_choice"] if kind == "pipeline" else "stored")
                if a is not None and b is not None and a.shape == b.shape:
                    cross[f"{first}__vs__{second}__{kind}"] = match(a, b)
    (output / "cross-observation.json").write_text(json.dumps(cross, indent=2))
    print(output)


if __name__ == "__main__":
    main()
