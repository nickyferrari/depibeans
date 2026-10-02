"""Compare DEPI fluorescence metrics under several explicit region definitions.

Offline and read-only with respect to its input: the observation directory is
only read, and every output is written to the separate output directory.

For every measurement point in ``fluorescence.json`` the tool recomputes each
metric from the saved derived TIFFs under these region definitions:

``production``
    The rule used by ``depibeans.fluorescence.analyze_run``: raw images
    (Background, F0, Fm, Fm_prime, Fs, Measuring) are averaged over every
    finite pixel of the frame; Fv and Fv/Fm over the dark-reference signal
    mask ``finite(F0) & finite(Fm) & (F0 > 16) & (Fm > F0)``; NPQ and PhiII
    over ``finite(reference Fm) & finite(Fm') & (Fm' > 16)``. Ratios are the
    mean of per-pixel ratios. The result is compared with the stored value.
``production_tiles``
    Ratio metrics and Fv calculated by hand from the *production tile values*
    of the raw images (what a reader of the portal tiles would compute).
``whole_frame``
    Every pixel where the operands are finite (and the denominator non-zero).
``signal_mask``
    The production signal mask applied consistently to ALL metrics, including
    the raw images.
``leaf_union`` / ``leaf_union_inset``
    Union of the detected / inset leaf labels, when the label files exist.

Ratio metrics are reported twice on identical pixel sets:

``average_of_ratios``  mean over pixels of the per-pixel ratio
``ratio_of_averages``  the formula applied to the region means of the operands

Dependencies: numpy and tifffile only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

RAW_METRICS = ("Background", "F0", "Fm", "Fm_prime", "Fs", "Measuring")
RATIO_METRICS = ("Fv_Fm", "NPQ", "PhiII")
SIGNAL_THRESHOLD = 16.0  # camera units; fluorescence.py lines 112, 129, 133
STAT_MEAN = "mean"
STAT_AOR = "average_of_ratios"
STAT_ROA = "ratio_of_averages"


def _read(path):
    import numpy as np
    import tifffile

    return np.asarray(tifffile.imread(path)).squeeze().astype(np.float32)


def _mean(values):
    import numpy as np

    return float(np.mean(values, dtype=np.float64)) if values.size else None


def _point_key(point):
    sequence = point.get("capture_sequence")
    return ("sequence", int(sequence)) if sequence is not None else ("time", float(point.get("time_s", 0)))


def _index_points(manifest):
    """Return {key: {metric: point}} preserving manifest order of keys."""
    index = {}
    for metric, definition in manifest.get("metrics", {}).items():
        for point in definition.get("points", []):
            index.setdefault(_point_key(point), {})[metric] = point
    return index


def _load_labels(observation, manifest):
    import numpy as np
    import tifffile

    segmentation = manifest.get("segmentation", {}) or {}
    result = {}
    for name, field, fallback in (
        ("leaf_union", "detected_label_file", "analysis/leaf-labels-detected.tif"),
        ("leaf_union_inset", "measurement_label_file", "analysis/leaf-labels-inset-8px.tif"),
    ):
        path = observation / (segmentation.get(field) or fallback)
        if path.is_file():
            result[name] = np.asarray(tifffile.imread(path)).squeeze() > 0
    return result


def _ratio_rows(numerator_a, numerator_b, denominator, region):
    """Per-pixel (a - b) / d and the same formula on region means.

    Both statistics use exactly the same pixels: region, all operands finite,
    denominator non-zero.
    """
    import numpy as np

    pixels = region & np.isfinite(numerator_a) & np.isfinite(numerator_b) & np.isfinite(denominator) & (denominator != 0)
    count = int(pixels.sum())
    if not count:
        return None, None, 0
    a, b, d = numerator_a[pixels], numerator_b[pixels], denominator[pixels]
    with np.errstate(all="ignore"):
        per_pixel = (a - b) / d
    average_of_ratios = _mean(per_pixel)
    mean_a, mean_b, mean_d = _mean(a), _mean(b), _mean(d)
    ratio_of_averages = (mean_a - mean_b) / mean_d if mean_d else None
    return average_of_ratios, ratio_of_averages, count


def compare(observation, *, relative_tolerance=1e-6, absolute_tolerance=1e-6):
    """Return the comparison report for one local observation directory."""
    import numpy as np

    observation = Path(observation).resolve()
    manifest = json.loads((observation / "fluorescence.json").read_text())
    index = _index_points(manifest)
    label_regions = _load_labels(observation, manifest)
    rows, checks, regions_report, timestamps = [], [], [], []

    def image_of(point):
        if not point or not point.get("file"):
            return None
        path = (observation / point["file"]).resolve()
        if not path.is_file() or not path.is_relative_to(observation):
            return None
        return _read(path)

    # The dark reference is the key that carries both F0 and Fm.
    dark_key = next((key for key, metrics in index.items() if "F0" in metrics and "Fm" in metrics), None)
    f0 = image_of(index[dark_key]["F0"]) if dark_key else None
    fm = image_of(index[dark_key]["Fm"]) if dark_key else None
    dark_mask = None
    reference_fm = None
    if f0 is not None and fm is not None:
        dark_mask = np.isfinite(f0) & np.isfinite(fm) & (f0 > SIGNAL_THRESHOLD) & (fm > f0)
        reference_fm = np.where(dark_mask, fm, np.nan).astype(np.float32)
        if dark_key[0] == "sequence":
            stored_reference = observation / f"analysis/{dark_key[1]:06d}-reference-Fm.tif"
            if stored_reference.is_file():
                saved = _read(stored_reference)
                same = bool(np.array_equal(np.isfinite(saved), dark_mask) and np.array_equal(saved[dark_mask], reference_fm[dark_mask]))
                checks.append({"check": "reference-Fm file equals Fm under the dark-reference mask", "passed": same})
                reference_fm = saved  # production reads this file (fluorescence.py line 129)

    frame_pixels = None

    def add(key, point, metric, region, statistic, value, count, stored=None):
        row = {
            "capture_sequence": key[1] if key[0] == "sequence" else None,
            "time_s": point.get("time_s") if point else None,
            "metric": metric, "region": region, "statistic": statistic,
            "value": value, "n_pixels": count,
            "fraction_of_frame": (count / frame_pixels) if frame_pixels and count is not None else None,
            "stored_value": stored, "difference_from_stored": None, "matches_stored": None,
        }
        if stored is not None and value is not None:
            row["difference_from_stored"] = value - stored
            row["matches_stored"] = bool(math.isclose(value, stored, rel_tol=relative_tolerance, abs_tol=absolute_tolerance))
        rows.append(row)
        return row

    for key, metrics in index.items():
        images = {metric: image_of(point) for metric, point in metrics.items()}
        any_image = next((image for image in images.values() if image is not None), None)
        if any_image is None:
            continue
        frame_pixels = int(any_image.size)
        whole = np.ones(any_image.shape, dtype=bool)
        any_point = next(iter(metrics.values()))

        # Production signal mask for this key.
        fmprime, fs = images.get("Fm_prime"), images.get("Fs")
        local_mask_rule = None
        if fmprime is not None and reference_fm is not None and ("NPQ" in metrics or "PhiII" not in metrics):
            signal = np.isfinite(reference_fm) & np.isfinite(fmprime) & (fmprime > SIGNAL_THRESHOLD)
            local_mask_rule = "finite(reference Fm) & finite(Fm') & (Fm' > 16)"
        elif fmprime is not None and fs is not None and "PhiII" in metrics:
            # No compatible dark reference: fluorescence.py line 133.
            signal = np.isfinite(fs) & np.isfinite(fmprime) & (fs > SIGNAL_THRESHOLD)
            local_mask_rule = "finite(Fs) & finite(Fm') & (Fs > 16)  [no compatible dark reference]"
        elif dark_mask is not None and dark_mask.shape == any_image.shape:
            signal = dark_mask
            local_mask_rule = "finite(F0) & finite(Fm) & (F0 > 16) & (Fm > F0)"
        else:
            signal = None
        named_regions = {"whole_frame": whole}
        if signal is not None:
            named_regions["signal_mask"] = signal
        for name, mask in label_regions.items():
            if mask.shape == any_image.shape:
                named_regions[name] = mask
        regions_report.append({
            "capture_sequence": key[1] if key[0] == "sequence" else None,
            "time_s": any_point.get("time_s"), "frame_pixels": frame_pixels,
            "signal_mask_rule": local_mask_rule,
            "regions": {name: {"pixels": int(mask.sum()), "fraction_of_frame": float(mask.mean())} for name, mask in named_regions.items()},
            "overlap": {
                f"{name}_within_signal_mask": float((mask & signal).sum() / max(1, mask.sum()))
                for name, mask in named_regions.items() if signal is not None and name.startswith("leaf")
            },
        })

        # Raw images.
        for metric in RAW_METRICS:
            image = images.get(metric)
            if image is None:
                continue
            stored = metrics[metric].get("value")
            finite = np.isfinite(image)
            row = add(key, metrics[metric], metric, "production", STAT_MEAN, _mean(image[finite]), int(finite.sum()), stored)
            stored_pixels = metrics[metric].get("valid_pixels")
            if stored_pixels is not None:
                checks.append({"check": f"{metric} valid_pixels @ {key[1]}", "passed": int(finite.sum()) == int(stored_pixels), "computed": int(finite.sum()), "stored": int(stored_pixels)})
            for name, mask in named_regions.items():
                pixels = mask & finite
                add(key, metrics[metric], metric, name, STAT_MEAN, _mean(image[pixels]), int(pixels.sum()))

        # Derived metrics: (numerator a, numerator b, denominator, production mask, production operands).
        derived = {}
        if key == dark_key and f0 is not None and fm is not None:
            derived["Fv"] = (fm, f0, None)
            derived["Fv_Fm"] = (fm, f0, fm)
        if fmprime is not None and reference_fm is not None and dark_mask is not None:
            derived["NPQ"] = (fm, fmprime, fmprime)  # unmasked dark Fm; masks are applied per region
        if fmprime is not None and fs is not None:
            derived["PhiII"] = (fmprime, fs, fmprime)

        for metric, (a, b, d) in derived.items():
            point = metrics.get(metric)
            stored = point.get("value") if point else None
            production_mask = dark_mask if metric in ("Fv", "Fv_Fm") else signal
            if metric == "NPQ":
                production_mask = np.isfinite(reference_fm) & np.isfinite(fmprime) & (fmprime > SIGNAL_THRESHOLD)
            region_set = dict(named_regions)
            if metric in ("Fv", "Fv_Fm") and dark_mask is not None:
                region_set["signal_mask"] = dark_mask
            if metric == "Fv":
                if production_mask is not None:
                    pixels = production_mask & np.isfinite(a) & np.isfinite(b)
                    add(key, point or any_point, metric, "production", STAT_MEAN, _mean((a - b)[pixels]), int(pixels.sum()), stored)
                for name, mask in region_set.items():
                    pixels = mask & np.isfinite(a) & np.isfinite(b)
                    add(key, point or any_point, metric, name, STAT_MEAN, _mean((a - b)[pixels]), int(pixels.sum()))
                tiles = [index[dark_key][m].get("value") for m in ("Fm", "F0")]
                if all(v is not None for v in tiles):
                    add(key, point or any_point, metric, "production_tiles", "difference_of_tile_values", tiles[0] - tiles[1], None)
                continue
            if production_mask is not None:
                aor, roa, count = _ratio_rows(a, b, d, production_mask)
                add(key, point or any_point, metric, "production", STAT_AOR, aor, count, stored)
                if point and point.get("valid_pixels") is not None:
                    checks.append({"check": f"{metric} valid_pixels @ {key[1]}", "passed": count == int(point["valid_pixels"]), "computed": count, "stored": int(point["valid_pixels"])})
            for name, mask in region_set.items():
                aor, roa, count = _ratio_rows(a, b, d, mask)
                add(key, point or any_point, metric, name, STAT_AOR, aor, count)
                add(key, point or any_point, metric, name, STAT_ROA, roa, count)
            # What a reader computes from the tiles.
            tile = lambda m, source=metrics: (source.get(m) or {}).get("value")
            dark_tile = lambda m: (index.get(dark_key, {}).get(m) or {}).get("value")
            operands = {"Fv_Fm": (dark_tile("Fm"), dark_tile("F0"), dark_tile("Fm")),
                        "NPQ": (dark_tile("Fm"), tile("Fm_prime"), tile("Fm_prime")),
                        "PhiII": (tile("Fm_prime"), tile("Fs"), tile("Fm_prime"))}[metric]
            if all(v is not None for v in operands) and operands[2]:
                add(key, point or any_point, metric, "production_tiles", STAT_ROA, (operands[0] - operands[1]) / operands[2], None)

        # Timestamps.
        entry = {"capture_sequence": key[1] if key[0] == "sequence" else None, "time_s": any_point.get("time_s"), "label": any_point.get("label")}
        if key[0] == "sequence":
            metadata = observation / f"capture-{key[1]:06d}" / "metadata.json"
            if metadata.is_file():
                meta = json.loads(metadata.read_text())
                for field in ("intended_trigger", "actual_trigger", "trigger_lateness_s", "timing_source"):
                    entry[field] = meta.get(field)
                entry["time_source"] = "actual_trigger" if meta.get("actual_trigger") else "metadata.json mtime (not preserved in a copy)"
        timestamps.append(entry)

    state_path = observation / "analysis-state.json"
    origin = json.loads(state_path.read_text()).get("origin") if state_path.is_file() else None
    for entry in timestamps:
        if origin is not None and entry.get("actual_trigger") and entry.get("time_s") is not None:
            entry["actual_trigger_minus_origin"] = entry["actual_trigger"] - origin
            checks.append({"check": f"time_s equals actual_trigger - origin @ {entry['capture_sequence']}", "passed": bool(abs(entry["actual_trigger_minus_origin"] - entry["time_s"]) < 1e-6)})

    mismatches = [row for row in rows if row["matches_stored"] is False]
    return {
        "schema": "depibeans.metric-region-comparison/1",
        "observation": observation.name,
        "name": manifest.get("name"),
        "time_origin": manifest.get("time_origin"), "run_start": manifest.get("run_start"), "origin": origin,
        "segmentation_algorithm_version_of_label_files": (manifest.get("segmentation") or {}).get("algorithm_version"),
        "segmentation_reference_file_of_label_files": (manifest.get("segmentation") or {}).get("reference_file"),
        "tolerance": {"relative": relative_tolerance, "absolute": absolute_tolerance},
        "production_mismatches": mismatches,
        "checks": checks, "regions": regions_report, "timestamps": timestamps, "rows": rows,
    }


def write_report(report, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "metric-regions.json").write_text(json.dumps(report, indent=2, allow_nan=False, default=lambda v: None))
    fields = ["capture_sequence", "time_s", "metric", "region", "statistic", "value", "n_pixels", "fraction_of_frame", "stored_value", "difference_from_stored", "matches_stored"]
    with (output / "metric-regions.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report["rows"])
    return output


def _json_safe(report):
    """Replace non-finite floats so the JSON stays strict."""
    def clean(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    return clean(report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("observation", type=Path, help="LOCAL copy of an observation directory containing fluorescence.json and its TIFFs")
    parser.add_argument("output", type=Path, help="Directory for metric-regions.csv and metric-regions.json (must not be inside the observation)")
    parser.add_argument("--relative-tolerance", type=float, default=1e-6, help="Relative tolerance for the production check (default 1e-6)")
    parser.add_argument("--strict", action="store_true", help="Exit with status 1 if any production value does not reproduce")
    args = parser.parse_args(argv)
    observation, output = args.observation.resolve(), args.output.resolve()
    if output == observation or output.is_relative_to(observation):
        parser.error("The output directory must be outside the observation directory; inputs are never modified.")
    report = _json_safe(compare(observation, relative_tolerance=args.relative_tolerance))
    destination = write_report(report, output)
    production = [row for row in report["rows"] if row["region"] == "production" and row["stored_value"] is not None]
    print(f"{len(production) - len(report['production_mismatches'])}/{len(production)} production values reproduced")
    for row in report["production_mismatches"]:
        print(f"MISMATCH {row['metric']} @ {row['capture_sequence'] or row['time_s']}: computed {row['value']!r}, stored {row['stored_value']!r}")
    failed = [check for check in report["checks"] if not check["passed"]]
    for check in failed:
        print("CHECK FAILED", json.dumps(check))
    print(destination)
    return 1 if args.strict and (report["production_mismatches"] or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
