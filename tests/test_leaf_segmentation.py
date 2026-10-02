import tempfile
import unittest
from pathlib import Path
import json

import numpy as np
import tifffile

from depibeans.fluorescence import datasets, images
from depibeans.leaf_segmentation import inset_labels, register_labels, segment_leaves, summarize_by_leaf, update_observation
from tools.preview_leaf_segmentation import build_review


def ellipse_image(shape=(180, 240)):
    y, x = np.ogrid[:shape[0], :shape[1]]
    image = np.full(shape, 5, dtype=np.float32)
    image[((y - 55) / 22) ** 2 + ((x - 55) / 14) ** 2 <= 1] = 120
    image[((y - 112) / 25) ** 2 + ((x - 160) / 38) ** 2 <= 1] = 180
    return image


class LeafSegmentationTests(unittest.TestCase):
    def test_separate_leaves_have_stable_top_to_bottom_identifiers(self):
        labels, result = segment_leaves(ellipse_image(), min_area=100)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(labels.max(), 2)
        self.assertLess(result["regions"][0]["centroid"][0], result["regions"][1]["centroid"][0])
        again, _ = segment_leaves(ellipse_image(), min_area=100)
        np.testing.assert_array_equal(labels, again)

    def test_touching_round_leaves_are_separated(self):
        y, x = np.ogrid[:160, :200]
        image = np.full((160, 200), 5, dtype=np.float32)
        image[(y - 80) ** 2 + (x - 78) ** 2 <= 34 ** 2] = 150
        image[(y - 80) ** 2 + (x - 122) ** 2 <= 34 ** 2] = 155
        labels, result = segment_leaves(image, min_area=100)
        self.assertEqual(labels.max(), 2)
        self.assertTrue(all(region["area_pixels"] > 2500 for region in result["regions"]))
        self.assertLess(result["regions"][0]["centroid"][1], result["regions"][1]["centroid"][1])

    def test_connected_three_lobed_cluster_is_separated(self):
        y, x = np.ogrid[:240, :170]
        image = np.full((240, 170), 5, dtype=np.float32)
        foreground = (
            ((y - 50) / 43) ** 2 + ((x - 82) / 32) ** 2 <= 1
        ) | (
            ((y - 120) / 48) ** 2 + ((x - 70) / 36) ** 2 <= 1
        ) | (
            ((y - 195) / 45) ** 2 + ((x - 86) / 33) ** 2 <= 1
        )
        image[foreground] = 150
        labels, result = segment_leaves(image, min_area=100)
        self.assertEqual(labels.max(), 3)
        self.assertEqual(len(result["regions"]), 3)

    def test_noise_is_removed_and_edge_region_is_flagged(self):
        image = ellipse_image()
        image[2:4, 120:122] = 220
        image[80:130, :18] = 140
        labels, result = segment_leaves(image, min_area=100)
        self.assertEqual(labels[2:4, 120:122].max(), 0)
        self.assertTrue(any(region["touches_edge"] for region in result["regions"]))
        self.assertEqual(result["status"], "accepted_with_warnings")

    def test_constant_image_reports_no_foreground(self):
        labels, result = segment_leaves(np.ones((80, 90), dtype=np.float32), min_area=20)
        self.assertFalse(labels.any())
        self.assertEqual(result["state"], "unavailable")

    def test_valid_nan_mask_preserves_a_dim_leaf(self):
        y, x = np.ogrid[:120, :180]
        image = np.full((120, 180), np.nan, dtype=np.float32)
        image[(y - 45) ** 2 + (x - 45) ** 2 <= 20 ** 2] = 25
        image[(y - 72) ** 2 + (x - 125) ** 2 <= 25 ** 2] = 250
        labels, result = segment_leaves(image, min_area=100)
        self.assertEqual(labels.max(), 2)
        self.assertIsNone(result["threshold"])
        self.assertTrue(all(region["area_pixels"] > 1000 for region in result["regions"]))

    def test_summaries_preserve_invalid_pixel_counts(self):
        labels, result = segment_leaves(ellipse_image(), min_area=100)
        metric = ellipse_image() / 200
        first = labels == 1
        metric[np.argwhere(first)[:25, 0], np.argwhere(first)[:25, 1]] = np.nan
        summaries = summarize_by_leaf(metric, labels, result["regions"])
        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0]["area_pixels"] - summaries[0]["valid_pixels"], 25)
        self.assertGreater(summaries[1]["mean"], summaries[0]["mean"])

    def test_measurement_inset_removes_each_region_perimeter(self):
        labels, _ = segment_leaves(ellipse_image(), min_area=100)
        inset = inset_labels(labels, 5)
        self.assertEqual(inset.max(), labels.max())
        for identifier in range(1, int(labels.max()) + 1):
            self.assertGreater((inset == identifier).sum(), 0)
            self.assertLess((inset == identifier).sum(), (labels == identifier).sum())
            self.assertTrue(np.all(labels[inset == identifier] == identifier))

    def test_small_translation_is_registered(self):
        source = ellipse_image()
        labels, _ = segment_leaves(source, min_area=100)
        target = np.roll(np.roll(source, 4, axis=0), -3, axis=1)
        moved, registration = register_labels(labels, target)
        self.assertEqual(registration["state"], "accepted")
        self.assertEqual(registration["shift_pixels"], [4.0, -3.0])
        self.assertGreater(registration["score"], 0.98)
        self.assertFalse(np.array_equal(labels, moved))

    def test_local_review_keeps_source_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = ellipse_image()
            source = root / "reference-Fm.tif"
            tifffile.imwrite(source, reference)
            original = source.read_bytes()
            result = build_review(source, root / "review", min_area=100)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(result["state"], "completed")
            for name in ["heatmap.png", "leaf-overlay.png", "leaf-labels.tif", "leaf-labels-inset-8px.tif", "segmentation.json", "index.html"]:
                self.assertTrue((root / "review" / name).is_file(), name)

    def test_observation_backfill_adds_masks_and_leaf_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            captures = Path(temporary)
            observation = captures / "npq-example"
            observation.mkdir()
            reference = ellipse_image()
            f0 = reference * 0.35
            fm_prime = reference.copy()
            source = observation / "science-Fm-prime.tif"
            tifffile.imwrite(source, fm_prime)
            tifffile.imwrite(observation / "science-F0.tif", f0)
            original = source.read_bytes()
            manifest = {
                "name": "NPQ example", "state": "completed", "completed_at": 123,
                "metrics": {
                    "F0": {"label": "F₀", "units": "camera units", "display_min": 0, "display_max": 100, "points": [{"file": "science-F0.tif", "time_s": 0, "value": 1, "valid_pixels": f0.size}]},
                    "Fm_prime": {"label": "Fm′", "units": "camera units", "display_min": 0, "display_max": 200, "points": [{"file": source.name, "time_s": 10, "value": 2, "valid_pixels": fm_prime.size}]},
                },
            }
            (observation / "fluorescence.json").write_text(json.dumps(manifest))

            result = update_observation(observation, inset_pixels=8)

            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(result["segmentation"]["state"], "completed")
            self.assertEqual(result["segmentation"]["measurement_inset_pixels"], 8)
            self.assertEqual(len(result["metrics"]["F0"]["points"][0]["leaf_values"]), 2)
            self.assertTrue((observation / result["segmentation"]["detected_label_file"]).is_file())
            served = datasets(captures)[0]
            self.assertIn("detected_image_id", served["segmentation"])
            self.assertIn("measurement_image_id", served["segmentation"])
            self.assertEqual(len([item for item in images(captures) if item["kind"] == "segmentation"]), 2)


if __name__ == "__main__":
    unittest.main()
