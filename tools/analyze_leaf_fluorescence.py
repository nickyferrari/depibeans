"""Compare fluorescence parameters between locally segmented leaves."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parents[1]
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from depibeans.leaf_segmentation import inset_labels, segment_leaves


def _point_files(manifest, observation):
    for metric, definition in manifest.get("metrics", {}).items():
        for point in definition.get("points", []):
            filename = point.get("file")
            path = observation / filename if filename else None
            if path and path.is_file():
                yield metric, definition, point, path


def _reference(manifest, observation):
    points = list(_point_files(manifest, observation))
    for preferred in ("Fm_prime", "Fm", "F0"):
        for metric, definition, point, path in points:
            if metric == preferred:
                return metric, point, path
    raise ValueError("Observation has no compatible fluorescence TIFF")


def _write_figure(rows, regions, insets, selected_inset, output):
    import matplotlib.pyplot as plt
    import numpy as np

    leaf_ids = [int(region["id"]) for region in regions]
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    specs = [("F0", "F₀", "raw camera units"), ("Fm", "Fm", "raw camera units"),
             ("Fv", "Fv", "raw camera units"), ("Fv_Fm", "Fv/Fm", "dimensionless")]
    for ax, (metric, title, units) in zip(axes.flat[:4], specs):
        values = []
        for leaf in leaf_ids:
            match = [r for r in rows if r["metric"] == metric and r["leaf_id"] == leaf and r["inset_pixels"] == selected_inset]
            values.append(match[0]["mean"] if match else np.nan)
        colors = ["#c66b21" if next(region for region in regions if region["id"] == leaf)["touches_edge"] else "#2d7f5e" for leaf in leaf_ids]
        ax.bar([str(v) for v in leaf_ids], values, color=colors)
        ax.set(title=f"{title} by leaf · {selected_inset:g}px inset", xlabel="Leaf ID", ylabel=units)
        ax.spines[["top", "right"]].set_visible(False)

    ax = axes.flat[4]
    npq_rows = [r for r in rows if r["metric"] == "NPQ" and r["inset_pixels"] == selected_inset]
    for leaf in leaf_ids:
        points = sorted((r for r in npq_rows if r["leaf_id"] == leaf), key=lambda r: r["time_s"])
        if points:
            ax.plot([p["time_s"] for p in points], [p["mean"] for p in points], marker="o", label=str(leaf))
    ax.set(title=f"NPQ time course · {selected_inset:g}px inset", xlabel="Seconds after actinic start", ylabel="NPQ")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(title="Leaf", ncol=3, fontsize=8)

    ax = axes.flat[5]
    for leaf in leaf_ids:
        retained = []
        original = next(r["original_pixels"] for r in rows if r["leaf_id"] == leaf)
        for inset in insets:
            match = next(r for r in rows if r["leaf_id"] == leaf and r["inset_pixels"] == inset)
            retained.append(match["measurement_pixels"] / original if original else np.nan)
        ax.plot(insets, retained, marker="o", label=str(leaf))
    ax.axvline(selected_inset, color="#c66b21", linestyle="--", linewidth=1)
    ax.set(title="Area retained by inset", xlabel="Inset from detected edge (pixels)", ylabel="Retained fraction", ylim=(0, 1.02))
    ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("DEPI per-leaf fluorescence comparison", fontsize=16)
    fig.savefig(output, dpi=160, facecolor="white")
    plt.close(fig)


def analyze_observation(observation, output, *, insets=(0, 4, 8, 12, 16, 24), selected_inset=8):
    import numpy as np
    import tifffile

    observation = Path(observation).resolve()
    output = Path(output).resolve()
    manifest = json.loads((observation / "fluorescence.json").read_text())
    reference_metric, reference_point, reference_path = _reference(manifest, observation)
    reference_image = np.asarray(tifffile.imread(reference_path)).squeeze()
    labels, segmentation = segment_leaves(reference_image)
    output.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(output / "leaf-labels-detected.tif", labels.astype(np.uint16), photometric="minisblack")

    regions = segmentation.get("regions", [])
    original_area = {int(region["id"]): int((labels == int(region["id"])).sum()) for region in regions}
    images = [(metric, definition, point, path, np.asarray(tifffile.imread(path)).squeeze())
              for metric, definition, point, path in _point_files(manifest, observation)]
    rows = []
    for inset in insets:
        measured = inset_labels(labels, inset)
        tifffile.imwrite(output / f"leaf-labels-inset-{float(inset):g}px.tif", measured.astype(np.uint16), photometric="minisblack")
        for region in regions:
            leaf_id = int(region["id"])
            selected = measured == leaf_id
            measurement_pixels = int(selected.sum())
            for metric, definition, point, path, image in images:
                valid = selected & np.isfinite(image)
                values = image[valid]
                row = {
                    "leaf_id": leaf_id,
                    "touches_edge": bool(region["touches_edge"]),
                    "inset_pixels": float(inset),
                    "original_pixels": original_area[leaf_id],
                    "measurement_pixels": measurement_pixels,
                    "retained_fraction": float(measurement_pixels / original_area[leaf_id]) if original_area[leaf_id] else 0.0,
                    "metric": metric,
                    "label": definition.get("label", metric),
                    "units": definition.get("units", ""),
                    "time_s": float(point.get("time_s", 0)),
                    "source_file": path.name,
                    "valid_pixels": int(values.size),
                    "masked_fraction": float(1 - values.size / measurement_pixels) if measurement_pixels else 1.0,
                    "mean": float(np.mean(values, dtype=np.float64)) if values.size else None,
                    "median": float(np.median(values)) if values.size else None,
                    "stdev": float(np.std(values, dtype=np.float64)) if values.size else None,
                }
                rows.append(row)

    columns = list(rows[0]) if rows else []
    with (output / "per-leaf-fluorescence.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "source_observation": manifest.get("name"),
        "qualification": manifest.get("qualification"),
        "reference_metric": reference_metric,
        "reference_file": reference_path.name,
        "selected_inset_pixels": float(selected_inset),
        "insets_pixels": [float(value) for value in insets],
        "segmentation": segmentation,
        "rows": rows,
    }
    (output / "per-leaf-fluorescence.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    _write_figure(rows, regions, list(insets), float(selected_inset), output / "leaf-parameter-comparison.png")

    chosen = [row for row in rows if row["inset_pixels"] == float(selected_inset)]
    lines = ["# DEPI per-leaf fluorescence comparison", "",
             f"Reference: `{reference_path.name}`. Measurement masks use a {float(selected_inset):g}-pixel inset from every detected leaf boundary.", "",
             f"Qualification: {manifest.get('qualification', 'Not supplied')}", "",
             "The completed observation contains F₀, Fm, Fv, Fv/Fm, three Fm′ measurements, and three NPQ measurements. It does not contain Fs, so ΦII cannot be calculated.", "",
             "## Selected inset values", "",
             "| Leaf | Edge | Retained | F₀ | Fm | Fv/Fm | NPQ at final time |", "|---:|:---:|---:|---:|---:|---:|---:|"]
    for region in regions:
        leaf = int(region["id"])
        subset = [row for row in chosen if row["leaf_id"] == leaf]
        def value(metric, last=False):
            matches = [row for row in subset if row["metric"] == metric]
            if last:
                matches = sorted(matches, key=lambda row: row["time_s"])
            item = matches[-1] if matches else None
            return "—" if not item or item["mean"] is None else f"{item['mean']:.4f}"
        retained = subset[0]["retained_fraction"] if subset else 0
        lines.append(f"| {leaf} | {'yes' if region['touches_edge'] else 'no'} | {retained:.1%} | {value('F0')} | {value('Fm')} | {value('Fv_Fm')} | {value('NPQ', True)} |")
    def inset_changes(metric):
        keys = {(row["leaf_id"], row["time_s"]) for row in rows if row["metric"] == metric}
        changes = []
        for leaf, time_s in keys:
            full = next((row for row in rows if row["metric"] == metric and row["leaf_id"] == leaf and row["time_s"] == time_s and row["inset_pixels"] == 0), None)
            inset = next((row for row in rows if row["metric"] == metric and row["leaf_id"] == leaf and row["time_s"] == time_s and row["inset_pixels"] == float(selected_inset)), None)
            if full and inset and full["mean"] not in (None, 0) and inset["mean"] is not None:
                changes.append(100 * (inset["mean"] - full["mean"]) / abs(full["mean"]))
        return changes

    f0_change = inset_changes("F0")
    fm_change = inset_changes("Fm")
    fvfm_change = inset_changes("Fv_Fm")
    npq_change = inset_changes("NPQ")
    lines += ["", "## Inset sensitivity", "",
              f"Compared with the full detected regions, the {float(selected_inset):g}-pixel inset changes the median F₀ mean by {np.median(f0_change):+.2f}% and the median Fm mean by {np.median(fm_change):+.2f}%.",
              f"The median absolute change is {np.median(np.abs(fvfm_change)):.2f}% for Fv/Fm and {np.median(np.abs(npq_change)):.2f}% for NPQ across its three timepoints.",
              "The narrow fragments lose the largest fraction of their area, so their inset sensitivity should be reviewed separately from complete leaves.", "",
              "The complete sensitivity data are in `per-leaf-fluorescence.csv`; compare rows with the same leaf, metric, and time. Raw camera-unit metrics and dimensionless ratios should be interpreted separately.", ""]
    (output / "SUMMARY.md").write_text("\n".join(lines))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path, help="Directory containing fluorescence.json and its TIFF files")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--insets", default="0,4,8,12,16,24", help="Comma-separated inset distances in pixels")
    parser.add_argument("--selected-inset", default=8, type=float)
    args = parser.parse_args()
    insets = tuple(float(value) for value in args.insets.split(","))
    result = analyze_observation(args.observation, args.output, insets=insets, selected_inset=args.selected_inset)
    print(f"{len(result['segmentation'].get('regions', []))} leaves; results: {args.output.resolve()}")


if __name__ == "__main__":
    main()
