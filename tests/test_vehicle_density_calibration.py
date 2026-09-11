"""
tests/test_vehicle_density_calibration.py
==========================================
Covers src/vehicle_density_calibration.py against a small COCO-format
fixture that mirrors UVH-26's documented annotation schema exactly
(image/annotation/category records with bbox/category_id) — this sandbox
cannot download the real dataset (see that module's docstring for why),
so this fixture is a schema-accurate stand-in, not real UVH-26 data, and
every test here says so implicitly by being clearly synthetic rather than
claiming otherwise.
"""

import pytest

from vehicle_density_calibration import (
    blend_with_synthetic_multiplier,
    calibrate_multiplier_stats,
    density_to_congestion_multiplier,
    vehicle_counts_per_image,
)


def _fixture_coco():
    """3 images: one empty (0 vehicles), one light (3 vehicles, one of
    which is a non-vehicle category to exercise filtering), one heavy
    (35 vehicles) — deliberately spanning below/inside/above the default
    density_to_congestion_multiplier thresholds."""
    images = [{"id": 1, "file_name": "empty.jpg"}, {"id": 2, "file_name": "light.jpg"}, {"id": 3, "file_name": "heavy.jpg"}]
    categories = [
        {"id": 10, "name": "sedan"},
        {"id": 11, "name": "two_wheeler"},
        {"id": 99, "name": "unclear"},
    ]
    annotations = []
    # image 2: 2 real vehicles + 1 "unclear"
    annotations.append({"id": 1, "image_id": 2, "category_id": 10, "bbox": [0, 0, 10, 10]})
    annotations.append({"id": 2, "image_id": 2, "category_id": 11, "bbox": [10, 10, 10, 10]})
    annotations.append({"id": 3, "image_id": 2, "category_id": 99, "bbox": [20, 20, 5, 5]})
    # image 3: 35 vehicles (heavy)
    for i in range(35):
        annotations.append({"id": 100 + i, "image_id": 3, "category_id": 10, "bbox": [i, i, 5, 5]})
    return {"images": images, "annotations": annotations, "categories": categories}


class TestVehicleCountsPerImage:
    def test_counts_every_image_including_empty_ones(self):
        counts = vehicle_counts_per_image(_fixture_coco())
        assert counts == {1: 0, 2: 3, 3: 35}

    def test_category_filter_excludes_non_vehicle_class(self):
        counts = vehicle_counts_per_image(_fixture_coco(), vehicle_category_ids={10, 11})
        assert counts[2] == 2  # the "unclear" (99) annotation is excluded
        assert counts[3] == 35

    def test_empty_coco_dict_yields_no_images(self):
        assert vehicle_counts_per_image({}) == {}


class TestDensityToCongestionMultiplier:
    def test_at_or_below_light_threshold_is_free_flow(self):
        assert density_to_congestion_multiplier(0) == 1.0
        assert density_to_congestion_multiplier(8) == 1.0

    def test_at_or_above_heavy_threshold_is_saturated(self):
        assert density_to_congestion_multiplier(30) == 2.2
        assert density_to_congestion_multiplier(500) == 2.2

    def test_midpoint_is_linearly_interpolated(self):
        # thresholds 8..30, midpoint 19 -> halfway between 1.0 and 2.2
        mid = density_to_congestion_multiplier(19)
        assert mid == pytest.approx(1.6, abs=0.01)

    def test_monotonically_non_decreasing_in_vehicle_count(self):
        values = [density_to_congestion_multiplier(v) for v in range(0, 40)]
        assert all(values[i] <= values[i + 1] for i in range(len(values) - 1))

    def test_custom_thresholds_and_bounds_are_honored(self):
        assert density_to_congestion_multiplier(5, light_threshold=5, heavy_threshold=10, min_multiplier=1.5, max_multiplier=3.0) == 1.5
        assert density_to_congestion_multiplier(10, light_threshold=5, heavy_threshold=10, min_multiplier=1.5, max_multiplier=3.0) == 3.0

    def test_rejects_invalid_threshold_ordering(self):
        with pytest.raises(ValueError):
            density_to_congestion_multiplier(5, light_threshold=10, heavy_threshold=5)


class TestCalibrateMultiplierStats:
    def test_summary_matches_hand_computed_values(self):
        stats = calibrate_multiplier_stats(_fixture_coco())
        assert stats["n_images"] == 3
        assert stats["min_vehicle_count"] == 0
        assert stats["max_vehicle_count"] == 35
        assert stats["mean_vehicle_count"] == pytest.approx((0 + 3 + 35) / 3)
        assert stats["median_vehicle_count"] == 3
        # multipliers: 1.0 (0 veh), 1.0 (3 veh, below light threshold 8), 2.2 (35 veh)
        assert stats["mean_multiplier"] == pytest.approx((1.0 + 1.0 + 2.2) / 3, abs=0.001)
        assert stats["median_multiplier"] == 1.0

    def test_category_filter_changes_the_summary(self):
        stats = calibrate_multiplier_stats(_fixture_coco(), vehicle_category_ids={10, 11})
        assert stats["max_vehicle_count"] == 35
        assert stats["mean_vehicle_count"] == pytest.approx((0 + 2 + 35) / 3)

    def test_raises_on_no_images(self):
        with pytest.raises(ValueError):
            calibrate_multiplier_stats({"images": [], "annotations": [], "categories": []})


class TestBlendWithSyntheticMultiplier:
    def test_weight_zero_keeps_synthetic_unchanged(self):
        assert blend_with_synthetic_multiplier(calibrated_multiplier=2.2, synthetic_multiplier=1.6, weight=0.0) == 1.6

    def test_weight_one_trusts_calibrated_fully(self):
        assert blend_with_synthetic_multiplier(calibrated_multiplier=2.2, synthetic_multiplier=1.6, weight=1.0) == 2.2

    def test_weight_half_is_the_midpoint(self):
        result = blend_with_synthetic_multiplier(calibrated_multiplier=2.0, synthetic_multiplier=1.0, weight=0.5)
        assert result == pytest.approx(1.5)

    def test_weight_is_clamped_outside_zero_one(self):
        assert blend_with_synthetic_multiplier(2.2, 1.6, weight=-5) == 1.6
        assert blend_with_synthetic_multiplier(2.2, 1.6, weight=5) == 2.2
