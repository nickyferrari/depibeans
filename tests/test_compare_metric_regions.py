"""Synthetic checks for tools/compare_metric_regions.py (no real data)."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

tifffile = pytest.importorskip("tifffile")

SPEC = importlib.util.spec_from_file_location("compare_metric_regions", Path(__file__).resolve().parents[1] / "tools" / "compare_metric_regions.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


def _observation(root):
    """Two 'leaves' of different brightness on a dim background, production-style manifest."""
    analysis = root / "analysis"
    analysis.mkdir(parents=True)
    shape = (40, 60)
    f0 = np.full(shape, 2.0, np.float32)
    fm = np.full(shape, 3.0, np.float32)
    fmp = np.full(shape, 2.5, np.float32)
    fs = np.full(shape, 2.2, np.float32)
    bright, dim = (slice(5, 25), slice(5, 25)), (slice(5, 25), slice(35, 55))
    f0[bright], fm[bright], fmp[bright], fs[bright] = 100, 500, 250, 150
    f0[dim], fm[dim], fmp[dim], fs[dim] = 40, 100, 80, 70
    fm[0, 0] = np.nan  # a clipped pixel
    mask = np.isfinite(f0) & np.isfinite(fm) & (f0 > 16) & (fm > f0)
    ref = np.where(mask, fm, np.nan).astype(np.float32)
    f0m = np.where(mask, f0, np.nan)
    light = np.isfinite(ref) & np.isfinite(fmp) & (fmp > 16)
    den = np.where(light, fmp, np.nan)
    images = {
        (2, "F0"): f0, (2, "Fm"): fm, (2, "Fv"): ref - f0m, (2, "Fv_Fm"): (ref - f0m) / ref,
        (4, "Fm_prime"): fmp, (4, "Fs"): fs, (4, "NPQ"): (ref - den) / den, (4, "PhiII"): (den - fs) / den,
    }
    metrics = {}
    for (sequence, key), image in images.items():
        name = f"analysis/{sequence:06d}-{key}.tif"
        tifffile.imwrite(root / name, image.astype(np.float32))
        finite = np.isfinite(image)
        metrics[key] = {"label": key, "points": [{"value": float(np.mean(image[finite], dtype=np.float64)), "time_s": float(sequence), "file": name, "capture_sequence": sequence, "valid_pixels": int(finite.sum())}]}
    tifffile.imwrite(analysis / "000002-reference-Fm.tif", ref)
    labels = np.zeros(shape, np.uint16)
    labels[bright], labels[dim] = 1, 2
    tifffile.imwrite(analysis / "leaf-labels-detected.tif", labels)
    inset = np.zeros(shape, np.uint16)
    inset[8:22, 8:22], inset[8:22, 38:52] = 1, 2
    tifffile.imwrite(analysis / "leaf-labels-inset-8px.tif", inset)
    (root / "fluorescence.json").write_text(json.dumps({"name": "synthetic", "state": "completed", "metrics": metrics, "segmentation": {}}))
    return root


def _value(report, metric, region, statistic):
    matches = [r for r in report["rows"] if (r["metric"], r["region"], r["statistic"]) == (metric, region, statistic)]
    assert len(matches) == 1, (metric, region, statistic, len(matches))
    return matches[0]["value"]


def test_production_reproduces_manifest(tmp_path):
    report = tool.compare(_observation(tmp_path / "obs"))
    production = [r for r in report["rows"] if r["region"] == "production"]
    assert {r["metric"] for r in production} == {"F0", "Fm", "Fv", "Fv_Fm", "Fm_prime", "Fs", "NPQ", "PhiII"}
    assert all(r["matches_stored"] for r in production)
    assert report["production_mismatches"] == []
    assert all(check["passed"] for check in report["checks"])


def test_average_of_ratios_differs_from_ratio_of_averages(tmp_path):
    report = tool.compare(_observation(tmp_path / "obs"))
    # Equal-area leaves: NPQ is 1.0 (bright) and 0.25 (dim).
    assert _value(report, "NPQ", "signal_mask", "average_of_ratios") == pytest.approx((1.0 + 0.25) / 2)
    assert _value(report, "NPQ", "signal_mask", "ratio_of_averages") == pytest.approx((300 - 165) / 165)
    assert _value(report, "PhiII", "leaf_union", "average_of_ratios") == pytest.approx((0.4 + 0.125) / 2)
    assert _value(report, "PhiII", "leaf_union", "ratio_of_averages") == pytest.approx((165 - 110) / 165)
    assert _value(report, "Fv_Fm", "leaf_union_inset", "average_of_ratios") == pytest.approx((0.8 + 0.6) / 2)
    assert _value(report, "Fv_Fm", "leaf_union_inset", "ratio_of_averages") == pytest.approx((300 - 70) / 300)


def test_raw_tiles_are_diluted_by_background(tmp_path):
    report = tool.compare(_observation(tmp_path / "obs"))
    tile_fv = _value(report, "Fv", "production_tiles", "difference_of_tile_values")
    assert _value(report, "Fv", "production", "mean") == pytest.approx(230.0)
    assert tile_fv < 230.0  # whole-frame Fm - F0 includes the dim background
    assert _value(report, "Fm", "signal_mask", "mean") == pytest.approx(300.0)
    assert _value(report, "Fm", "whole_frame", "mean") == pytest.approx(_value(report, "Fm", "production", "mean"))


def test_cli_writes_outputs_and_leaves_input_untouched(tmp_path):
    observation = _observation(tmp_path / "obs")
    before = {p: p.read_bytes() for p in observation.rglob("*") if p.is_file()}
    assert tool.main([str(observation), str(tmp_path / "out"), "--strict"]) == 0
    assert (tmp_path / "out" / "metric-regions.csv").is_file()
    assert json.loads((tmp_path / "out" / "metric-regions.json").read_text())["rows"]
    assert before == {p: p.read_bytes() for p in observation.rglob("*") if p.is_file()}
    with pytest.raises(SystemExit):
        tool.main([str(observation), str(observation / "out")])
