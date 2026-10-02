"""Create an exploratory local review of vascular contrast inside segmented leaves."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_venation_review(image_path, labels_path, output, *, leaf_ids=None, inset_pixels=20):
    import matplotlib.pyplot as plt
    import numpy as np
    from scipy import ndimage as ndi
    from skimage.morphology import black_tophat, disk
    import tifffile

    image_path = Path(image_path).resolve()
    labels_path = Path(labels_path).resolve()
    output = Path(output).resolve()
    image = np.asarray(tifffile.imread(image_path)).squeeze()
    labels = np.asarray(tifffile.imread(labels_path)).squeeze()
    if image.shape != labels.shape or image.ndim != 2:
        raise ValueError("Image and label mask must be matching two-dimensional arrays")
    if leaf_ids is None:
        areas = [(identifier, int((labels == identifier).sum())) for identifier in range(1, int(labels.max()) + 1)]
        leaf_ids = [identifier for identifier, _ in sorted(areas, key=lambda item: item[1], reverse=True)[:3]]
    leaf_ids = [int(identifier) for identifier in leaf_ids]

    figure, axes = plt.subplots(len(leaf_ids), 2, figsize=(10, 4.6 * len(leaf_ids)), squeeze=False, constrained_layout=True)
    records = []
    for row, identifier in enumerate(leaf_ids):
        mask = labels == identifier
        components, _ = ndi.label(mask)
        component_sizes = np.bincount(components.ravel())
        component_sizes[0] = 0
        mask = components == int(component_sizes.argmax())
        ys, xs = np.nonzero(mask)
        if not len(ys):
            raise ValueError(f"Leaf {identifier} is absent from the label image")
        pad = 10
        y0, y1 = max(0, int(ys.min()) - pad), min(image.shape[0], int(ys.max()) + pad + 1)
        x0, x1 = max(0, int(xs.min()) - pad), min(image.shape[1], int(xs.max()) + pad + 1)
        crop = image[y0:y1, x0:x1].astype(float)
        crop_mask = mask[y0:y1, x0:x1]
        valid = crop_mask & np.isfinite(crop)
        low, high = np.percentile(crop[valid], [2, 98])
        normalized = np.clip((crop - low) / max(high - low, 1e-8), 0, 1)
        fill = float(np.median(normalized[valid]))
        normalized[~np.isfinite(normalized)] = fill
        normalized[~crop_mask] = fill
        response = np.maximum.reduce([black_tophat(normalized, disk(radius)) for radius in (7, 13, 21, 31)])
        interior = ndi.distance_transform_edt(crop_mask) > float(inset_pixels)
        response[~interior] = 0
        response_values = response[interior]
        display_max = float(np.percentile(response_values, 99.5)) if response_values.size else 1.0

        axes[row, 0].imshow(normalized, cmap="gray", vmin=0, vmax=1)
        axes[row, 0].set_title(f"Leaf {identifier} · normalized fluorescence")
        axes[row, 1].imshow(response, cmap="magma", vmin=0, vmax=max(display_max, 1e-8))
        axes[row, 1].set_title("Exploratory multiscale dark-ridge response")
        for axis in axes[row]:
            axis.axis("off")
        records.append({"leaf_id": identifier, "bbox": [y0, x0, y1, x1], "interior_inset_pixels": float(inset_pixels), "scales_pixels": [7, 13, 21, 31]})

    figure.suptitle("Vascular-structure review · enhancement only, no accepted section labels", fontsize=14)
    figure.savefig(output, dpi=170, facecolor="white")
    plt.close(figure)
    metadata = {"state": "exploratory", "source_image": image_path.name, "source_labels": labels_path.name, "leaves": records,
                "limitation": "Dark-ridge enhancement exposes candidate midribs and first-order veins, but automatic tracing is not yet reliable enough to define measurement sections."}
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--leaf-ids", help="Comma-separated IDs; defaults to the three largest regions")
    parser.add_argument("--inset-pixels", type=float, default=20)
    args = parser.parse_args()
    leaf_ids = [int(value) for value in args.leaf_ids.split(",")] if args.leaf_ids else None
    result = build_venation_review(args.image, args.labels, args.output, leaf_ids=leaf_ids, inset_pixels=args.inset_pixels)
    print(f"Exploratory venation review for {len(result['leaves'])} leaves: {args.output.resolve()}")


if __name__ == "__main__":
    main()
