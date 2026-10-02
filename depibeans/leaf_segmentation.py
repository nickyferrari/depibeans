"""Deterministic leaf regions and per-region fluorescence summaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import warnings

ALGORITHM_VERSION = "2.0.0"
SCHEMA = "depibeans.leaf-segmentation/1"


def _libraries():
    import numpy as np
    from scipy import ndimage as ndi
    from skimage import filters, measure, morphology, segmentation
    return np, ndi, filters, measure, morphology, segmentation


def _validated_image(image):
    np, *_ = _libraries()
    value = np.asarray(image)
    if value.ndim != 2 or value.dtype.kind not in "uif" or value.size == 0:
        raise ValueError("Leaf segmentation requires a two-dimensional numeric image")
    if value.size > 20_000_000:
        raise ValueError("Leaf segmentation image is too large")
    value = value.astype(np.float32, copy=False)
    if not np.isfinite(value).any():
        raise ValueError("Leaf segmentation image has no finite pixels")
    return value


def _foreground(image, smoothing_sigma=1.4):
    np, ndi, filters, *_ = _libraries()
    image = _validated_image(image)
    finite = np.isfinite(image)
    values = image[finite]
    low, high = np.percentile(values, [1, 99])
    contrast = float(high - low)
    # A supplied NaN mask already defines valid plant pixels. Do not re-threshold
    # away dim regions (or reject equally bright leaves as a constant frame).
    if finite.mean() < 0.95:
        return finite, None, contrast
    if not np.isfinite(contrast) or contrast <= max(1e-6, abs(float(high)) * 1e-6):
        return np.zeros(image.shape, dtype=bool), float(low), contrast
    # Pixels already rejected upstream (NaN) are background, clearly below any leaf.
    filled = np.where(finite, image, low - max(contrast, 1.0) if finite.mean() < 0.95 else low)
    smooth = ndi.gaussian_filter(filled, float(smoothing_sigma), mode="nearest")
    try:
        otsu = float(filters.threshold_otsu(smooth))
    except ValueError:
        otsu = float((low + high) / 2)
    # Reference the threshold to the dark background, not to the split between
    # bright and shaded leaves: Otsu alone discards dim but valid leaves.
    dark = smooth[smooth <= np.percentile(smooth, 35)]
    level = float(np.median(dark))
    noise = float(np.median(np.abs(dark - level))) * 1.4826
    threshold = min(otsu, max(level + 8 * noise, 0.06 * float(np.percentile(smooth, 99.5))))
    # The smoothed image finds dim leaves; the unsmoothed one keeps their outline
    # from spreading into the background at a low threshold.
    return (smooth > threshold) & (filled > threshold), threshold, contrast


def _stable_labels(labels):
    np, _, _, measure, *_ = _libraries()
    regions = sorted(measure.regionprops(labels), key=lambda region: (region.centroid[0], region.centroid[1]))
    tolerance = max(4.0, float(np.median([region.bbox[2] - region.bbox[0] for region in regions])) * 0.35) if regions else 4.0
    rows = []
    for region in regions:
        if rows and abs(region.centroid[0] - rows[-1]["center"]) <= tolerance:
            rows[-1]["regions"].append(region)
            rows[-1]["center"] = float(np.mean([item.centroid[0] for item in rows[-1]["regions"]]))
        else:
            rows.append({"center": float(region.centroid[0]), "regions": [region]})
    ordered = [region for row in rows for region in sorted(row["regions"], key=lambda item: item.centroid[1])]
    result = np.zeros(labels.shape, dtype=np.int32)
    for identifier, region in enumerate(ordered, 1):
        result[labels == region.label] = identifier
    return result


def segment_leaves(
    image,
    *,
    min_area=None,
    smoothing_sigma=1.4,
    closing_radius=None,
    hole_area=None,
    separation_prominence=0.2,
    separation_percentile=93.0,
):
    """Return a label image and JSON-safe segmentation metadata.

    Zero is background. Positive identifiers are stable from top to bottom,
    then left to right. Regions are separated along strong interior intensity
    edges (leaf overlaps); a single leaf is not divided by its veins.
    """
    np, ndi, _, measure, morphology, watershed_module = _libraries()
    image = _validated_image(image)
    pixels = int(image.size)
    min_area = int(min_area if min_area is not None else max(64, round(pixels * 0.0005)))
    closing_radius = int(closing_radius if closing_radius is not None else max(1, min(image.shape) // 500))
    hole_area = int(hole_area if hole_area is not None else max(min_area * 4, 128))
    separation_prominence = float(separation_prominence)
    if min_area < 4 or closing_radius < 0 or hole_area < 0 or not 0 < separation_prominence <= 1:
        raise ValueError("Invalid segmentation parameters")

    foreground, threshold, contrast = _foreground(image, smoothing_sigma)
    if closing_radius:
        foreground = morphology.closing(foreground, morphology.disk(closing_radius))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        foreground = morphology.remove_small_objects(foreground, min_size=min_area)
        foreground = morphology.remove_small_holes(foreground, area_threshold=hole_area)
    if not foreground.any():
        return np.zeros(image.shape, dtype=np.int32), {
            "schema": SCHEMA, "algorithm_version": ALGORITHM_VERSION,
            "state": "unavailable", "status": "unavailable",
            "reason": "No leaf-like foreground passed the area and contrast gates.",
            "parameters": {"min_area": min_area, "smoothing_sigma": float(smoothing_sigma), "closing_radius": closing_radius, "hole_area": hole_area, "separation_prominence": separation_prominence},
            "threshold": threshold, "contrast": contrast, "regions": [], "warnings": [],
        }

    # Overlapping leaves meet at a shadowed intensity step. Cut the foreground
    # along strong interior edges, keep the wide cores as markers, and grow them
    # back over the edge-strength image. Fine veins are too weak to be cut, and a
    # vein that ends inside a leaf cannot divide it.
    _, _, filters, *_ = _libraries()
    scale = min(image.shape) / 1456.0
    radius = lambda pixels: morphology.disk(max(1, int(round(pixels * scale))))
    filled = np.where(np.isfinite(image), image, 0.0)
    broad = ndi.gaussian_filter(filled, max(1.0, 3.0 * scale), mode="nearest")
    offset = max(1e-6, 0.02 * float(np.percentile(broad, 99.5)))
    strength = filters.sobel(broad) / (np.abs(broad) + offset)
    interior = ndi.binary_erosion(foreground, radius(12), border_value=1)
    markers = np.zeros(image.shape, dtype=np.int32)
    if interior.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            edges = (strength > np.percentile(strength[interior], separation_percentile)) & interior
            edges = morphology.remove_small_objects(edges, min_size=max(16, int(400 * scale * scale)))
            edges = ndi.binary_dilation(ndi.binary_closing(edges, radius(9)), radius(3))
            cut = foreground & ~edges
    else:
        cut = foreground
    # Within the cut foreground, wide cores become markers. Narrow bridges left by
    # a soft overlap edge, and touching leaves of equal brightness, separate by
    # shape: regional maxima of the distance transform, shallow maxima suppressed.
    distance = ndi.distance_transform_edt(cut)
    component_labels = measure.label(cut, connectivity=2)
    next_marker = 1
    for component in measure.regionprops(component_labels):
        if component.area < max(16, int(1500 * scale * scale)) and component.area < min_area:
            continue
        rows, cols = component.slice
        component_mask = component_labels[rows, cols] == component.label
        local_distance = distance[rows, cols] * component_mask
        maximum = float(local_distance.max())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            maxima = morphology.h_maxima(local_distance, max(1.0, maximum * separation_prominence)) & component_mask
        peaks = measure.regionprops(measure.label(maxima, connectivity=2))
        if not peaks:
            cy, cx = (int(round(v)) for v in component.centroid)
            markers[cy, cx] = next_marker
            next_marker += 1
            continue
        for peak in peaks:
            cy, cx = (int(round(v)) for v in peak.centroid)
            markers[rows.start + cy, cols.start + cx] = next_marker
            next_marker += 1
    # A separate blob that kept no marker is still one region.
    blobs = measure.label(foreground, connectivity=2)
    seeded = set(np.unique(blobs[markers > 0]).tolist())
    for component in measure.regionprops(blobs):
        if component.label not in seeded:
            cy, cx = (int(round(v)) for v in component.centroid)
            if blobs[cy, cx] != component.label:
                cy, cx = (int(v) for v in component.coords[len(component.coords) // 2])
            markers[cy, cx] = next_marker
            next_marker += 1
    surface = strength / max(1e-9, float(strength[foreground].max())) - ndi.distance_transform_edt(cut) / max(1.0, float(distance.max()))
    labels = watershed_module.watershed(surface, markers, mask=foreground, watershed_line=False)
    for region in measure.regionprops(labels):
        if region.area < min_area:
            labels[labels == region.label] = 0
    labels = _stable_labels(labels)

    height, width = image.shape
    edge_margin = max(2, round(min(height, width) * 0.01))
    regions = []
    all_warnings = []
    for region in measure.regionprops(labels):
        min_row, min_col, max_row, max_col = (int(v) for v in region.bbox)
        edge = min_row <= edge_margin or min_col <= edge_margin or max_row >= height - edge_margin or max_col >= width - edge_margin
        region_warnings = []
        if edge:
            region_warnings.append("Region touches the image edge; leaf area may be truncated.")
        if region.area < min_area * 2:
            region_warnings.append("Region is close to the minimum accepted area.")
        if region.solidity < 0.72:
            region_warnings.append("Irregular outline may contain overlapping leaves or non-leaf foreground.")
        regions.append({
            "id": int(region.label), "area_pixels": int(region.area),
            "centroid": [float(region.centroid[0]), float(region.centroid[1])],
            "bbox": [min_row, min_col, max_row, max_col], "touches_edge": edge,
            "solidity": float(region.solidity), "warnings": region_warnings,
        })
        all_warnings.extend(f"Leaf {region.label}: {warning}" for warning in region_warnings)
    if contrast < max(4.0, abs(float(np.nanpercentile(image, 99))) * 0.03):
        all_warnings.append("Reference image has weak foreground contrast.")
    status = "accepted_with_warnings" if all_warnings else "accepted"
    return labels, {
        "schema": SCHEMA, "algorithm_version": ALGORITHM_VERSION,
        "state": "completed", "status": status,
        "parameters": {"min_area": min_area, "smoothing_sigma": float(smoothing_sigma), "closing_radius": closing_radius, "hole_area": hole_area, "separation_prominence": separation_prominence, "edge_margin_pixels": edge_margin, "separation_percentile": float(separation_percentile), "separation": "interior-edge markers, watershed over relative edge strength"},
        "threshold": threshold, "contrast": contrast, "shape": [height, width],
        "regions": regions, "warnings": all_warnings,
    }


def inset_labels(labels, inset_pixels=8):
    """Inset every labelled region from its complete perimeter.

    The returned image retains the original identifiers. Pixels within
    ``inset_pixels`` of background or another leaf become background. This is
    intended as a conservative measurement mask; it does not change the
    visually detected leaf boundary.
    """
    np, ndi, *_ = _libraries()
    labels = np.asarray(labels)
    if labels.ndim != 2 or labels.dtype.kind not in "ui":
        raise ValueError("Leaf labels must be a two-dimensional integer image")
    inset_pixels = float(inset_pixels)
    if not np.isfinite(inset_pixels) or inset_pixels < 0:
        raise ValueError("Inset pixels must be finite and non-negative")
    if inset_pixels == 0:
        return labels.copy()
    result = np.zeros(labels.shape, dtype=labels.dtype)
    for identifier in range(1, int(labels.max()) + 1):
        selected = labels == identifier
        if selected.any():
            result[ndi.distance_transform_edt(selected) > inset_pixels] = identifier
    return result


def summarize_by_leaf(image, labels, regions=None):
    """Calculate descriptive statistics without changing the source image."""
    np, *_ = _libraries()
    image = _validated_image(image)
    labels = np.asarray(labels)
    if labels.shape != image.shape or labels.dtype.kind not in "ui":
        raise ValueError("Leaf labels do not match the fluorescence image")
    region_map = {int(region["id"]): region for region in (regions or [])}
    summaries = []
    for identifier in range(1, int(labels.max()) + 1):
        selected = labels == identifier
        area = int(selected.sum())
        if not area:
            continue
        valid = selected & np.isfinite(image)
        values = image[valid]
        warnings = list(region_map.get(identifier, {}).get("warnings", []))
        masked_fraction = float(1 - len(values) / area)
        if masked_fraction > 0.2:
            warnings.append("More than 20% of this region is invalid for this measurement.")
        item = {"id": identifier, "area_pixels": area, "valid_pixels": int(len(values)), "masked_fraction": masked_fraction, "warnings": warnings}
        if len(values):
            item.update(mean=float(np.mean(values, dtype=np.float64)), median=float(np.median(values)), stdev=float(np.std(values, dtype=np.float64)))
        else:
            item.update(mean=None, median=None, stdev=None)
        summaries.append(item)
    return summaries


def register_labels(reference_labels, target, *, max_shift=None, min_score=0.45):
    """Translate a reference label mask to a target image and report overlap."""
    np, ndi, _, _, _, _ = _libraries()
    from skimage.registration import phase_cross_correlation

    labels = np.asarray(reference_labels)
    target = _validated_image(target)
    if labels.shape != target.shape:
        return labels, {"state": "rejected", "reason": "Image dimensions differ from the segmentation reference.", "shift_pixels": [0.0, 0.0], "score": 0.0}
    reference_mask = labels > 0
    finite = np.isfinite(target)
    if finite.mean() < 0.95 and finite.any():
        target_mask = finite
    else:
        target_mask, _, _ = _foreground(target, 1.0)
    if not reference_mask.any() or not target_mask.any():
        return labels, {"state": "rejected", "reason": "Target image has insufficient foreground for alignment.", "shift_pixels": [0.0, 0.0], "score": 0.0}

    def score(candidate):
        candidate = candidate > 0
        return float(2 * np.logical_and(candidate, target_mask).sum() / max(1, candidate.sum() + target_mask.sum()))

    identity_score = score(labels)
    try:
        align_target_to_reference, _, _ = phase_cross_correlation(reference_mask.astype(float), target_mask.astype(float), upsample_factor=1)
        shift = -np.asarray(align_target_to_reference, dtype=float)
    except (ValueError, FloatingPointError):
        shift = np.zeros(2, dtype=float)
    max_shift = float(max_shift if max_shift is not None else min(25, max(5, min(labels.shape) * 0.05)))
    if float(np.linalg.norm(shift)) > max_shift:
        shift = np.zeros(2, dtype=float)
    shifted = ndi.shift(labels, shift=shift, order=0, mode="constant", cval=0, prefilter=False).astype(labels.dtype)
    shifted_score = score(shifted)
    if identity_score >= shifted_score:
        shifted, shift, shifted_score = labels.copy(), np.zeros(2), identity_score
    accepted = shifted_score >= float(min_score)
    result = {"state": "accepted" if accepted else "rejected", "shift_pixels": [float(shift[0]), float(shift[1])], "score": shifted_score, "method": "binary phase correlation followed by foreground Dice overlap"}
    if not accepted:
        result["reason"] = "Foreground alignment score is below the acceptance threshold."
    return shifted, result


def _point_files(manifest, observation):
    observation = Path(observation).resolve()
    for metric, definition in manifest.get("metrics", {}).items():
        for point in definition.get("points", []):
            filename = point.get("file")
            if not filename:
                continue
            path = (observation / filename).resolve()
            if path.is_file() and path.is_relative_to(observation):
                yield metric, definition, point, path


def _reference_point(manifest, observation):
    """Choose a masked fluorescence image whose finite area describes the leaves."""
    points = list(_point_files(manifest, observation))
    # Dark-adapted Fm is the brightest, unquenched image of every leaf.
    for preferred in ("Fm", "Fm_prime", "Fv_Fm", "NPQ", "F0"):
        for metric, _, point, path in points:
            if metric == preferred:
                return metric, point, path
    raise ValueError("Observation has no compatible fluorescence image for leaf segmentation")


def update_observation(observation, data=None, *, inset_pixels=8):
    """Add reproducible leaf masks and per-leaf values to a fluorescence manifest.

    Source TIFFs are never modified. The detected and conservative measurement
    masks are stored beside the derived fluorescence images. A failed optional
    segmentation never invalidates the whole-image fluorescence result.
    """
    import numpy as np
    import tifffile

    observation = Path(observation).resolve()
    manifest_path = observation / "fluorescence.json"
    manifest = data if data is not None else json.loads(manifest_path.read_text())
    metric, point, reference_path = _reference_point(manifest, observation)
    reference_hash = hashlib.sha256(reference_path.read_bytes()).hexdigest()
    analysis = observation / "analysis"
    analysis.mkdir(exist_ok=True)
    detected_path = analysis / "leaf-labels-detected.tif"
    measurement_path = analysis / f"leaf-labels-inset-{float(inset_pixels):g}px.tif"
    previous = manifest.get("segmentation", {})
    reusable = (
        previous.get("state") == "completed"
        and previous.get("algorithm_version") == ALGORITHM_VERSION
        and previous.get("reference_sha256") == reference_hash
        and float(previous.get("measurement_inset_pixels", -1)) == float(inset_pixels)
        and detected_path.is_file()
        and measurement_path.is_file()
    )
    if reusable:
        labels = np.asarray(tifffile.imread(detected_path)).squeeze()
        measurement_labels = np.asarray(tifffile.imread(measurement_path)).squeeze()
        segmentation = previous
    else:
        reference = np.asarray(tifffile.imread(reference_path)).squeeze()
        labels, segmentation = segment_leaves(reference)
        if segmentation.get("state") != "completed" or not labels.any():
            manifest["segmentation"] = {
                **segmentation,
                "reference_metric": metric,
                "reference_file": str(reference_path.relative_to(observation)),
                "reference_sha256": reference_hash,
                "measurement_inset_pixels": float(inset_pixels),
            }
            _write_manifest(manifest_path, manifest)
            return manifest
        measurement_labels = inset_labels(labels, inset_pixels)
        label_type = np.uint16 if int(labels.max()) <= 65535 else np.uint32
        tifffile.imwrite(detected_path, labels.astype(label_type), photometric="minisblack")
        tifffile.imwrite(measurement_path, measurement_labels.astype(label_type), photometric="minisblack")
        segmentation.update({
            "reference_metric": metric,
            "reference_file": str(reference_path.relative_to(observation)),
            "reference_sha256": reference_hash,
            "detected_label_file": str(detected_path.relative_to(observation)),
            "measurement_label_file": str(measurement_path.relative_to(observation)),
            "measurement_inset_pixels": float(inset_pixels),
        })

    region_map = {int(region["id"]): region for region in segmentation.get("regions", [])}
    for identifier, region in region_map.items():
        detected_area = int((labels == identifier).sum())
        measured_area = int((measurement_labels == identifier).sum())
        region["measurement_area_pixels"] = measured_area
        region["retained_fraction"] = float(measured_area / detected_area) if detected_area else 0.0

    for _, _, measurement, path in _point_files(manifest, observation):
        image = np.asarray(tifffile.imread(path)).squeeze()
        if image.shape != measurement_labels.shape:
            measurement["leaf_values"] = []
            measurement["leaf_analysis_note"] = "Image dimensions differ from the segmentation reference."
            continue
        values = summarize_by_leaf(image, measurement_labels, segmentation.get("regions", []))
        for item in values:
            region = region_map.get(int(item["id"]), {})
            item["detected_area_pixels"] = int(region.get("area_pixels", item["area_pixels"]))
            item["measurement_area_pixels"] = int(item.pop("area_pixels"))
            item["retained_fraction"] = float(region.get("retained_fraction", 0))
        measurement["leaf_values"] = values
        measurement.pop("leaf_analysis_note", None)

    manifest["segmentation"] = segmentation
    _write_manifest(manifest_path, manifest)
    return manifest


def _write_manifest(path, data):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False))
    temporary.replace(path)
