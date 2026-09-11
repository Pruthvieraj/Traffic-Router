"""
vehicle_density_calibration.py
===============================
A free, real-data calibration pipeline for congestion.py's synthetic model.

`congestion.py`'s own docstring already names the honest upgrade path:
"apply_congestion() is also where you would plug in something calibrated
from real data (e.g., vehicle-density counts from a UVH-26-style CCTV/
vision pipeline...) instead of the synthetic model." This module is that
pipeline's data-processing half: turn real vehicle-count annotations from a
dataset like IISc's UVH-26 (https://huggingface.co/datasets/iisc-aim/UVH-26
— COCO-format bounding-box annotations, 14 Indian-traffic vehicle classes,
26,646 crowdsourced-annotated 1080p frames from Indian junctions) into a
congestion multiplier that can stand in for, or be blended with,
`congestion.py`'s synthetic `rush_hour_multiplier()` curve.

**Honest scope, stated plainly up front — read this before using any of
this.** This sandbox cannot download the actual UVH-26 dataset to
demonstrate this end-to-end on real images. That is NOT this project's
usual "needs a paid key/account" caveat (UVH-26 itself is a free,
public dataset) — it's a distinct, narrower one: this specific sandboxed
environment's outbound network access is allowlisted to package registries
only (pypi.org, npm, ...), and huggingface.co, its CDN, and even fallback
hosts like github.com/raw.githubusercontent.com are all rejected at the
network layer here, independent of cost. Confirmed directly: every one of
those hosts returns a hard connection-level rejection from this sandbox's
egress proxy, not a slow download or a rate limit.

So, following the exact same honest pattern this project already uses
twice elsewhere (the real D-Wave QPU integration in `qpu_solver.py`, and
the real Google Routes traffic provider in `traffic_provider.py` — "the
wiring is real and tested, the live call isn't something this environment
can make"): everything in this file is real, tested logic, not a stub —
covered by `tests/test_vehicle_density_calibration.py` against a small
COCO-format fixture that mirrors UVH-26's *documented* schema exactly
(image/annotation/category records with `bbox`/`category_id`) — but it has
never been run against the real dataset's actual files, because this
sandbox structurally cannot fetch them. Running it for real is one
function call away for anyone with normal internet access and a local copy
of (a slice of) UVH-26 — see `calibrate_from_uvh26.py` at the repo root.
"""

import statistics


def vehicle_counts_per_image(coco: dict, vehicle_category_ids: set | None = None) -> dict:
    """Count annotated vehicle bounding boxes per image from a COCO-format
    annotation dict — UVH-26's exact documented format:
    ``{"images": [{"id": ...}, ...],
       "annotations": [{"image_id": ..., "category_id": ..., "bbox": [x, y, w, h]}, ...],
       "categories": [{"id": ..., "name": ...}, ...]}``.

    Every image present in ``coco["images"]`` is included in the result
    (with a count of 0 if it has no matching annotations), so an empty
    frame isn't silently dropped from the average.

    Args:
        coco: a COCO-format dict (as loaded via ``json.load`` from a UVH-26
            annotation file, or any dataset using the same schema).
        vehicle_category_ids: if given, only annotations whose
            ``category_id`` is in this set are counted (e.g. to exclude a
            non-vehicle class if a dataset variant has one). UVH-26's own
            14 categories are all vehicle types, so the default (``None``,
            meaning "count every category present") is the right choice for
            it specifically.

    Returns:
        ``{image_id: vehicle_count}``.
    """
    counts = {img["id"]: 0 for img in coco.get("images", [])}
    for ann in coco.get("annotations", []):
        cid = ann.get("category_id")
        if vehicle_category_ids is not None and cid not in vehicle_category_ids:
            continue
        image_id = ann["image_id"]
        counts[image_id] = counts.get(image_id, 0) + 1
    return counts


def density_to_congestion_multiplier(
    vehicle_count: int,
    light_threshold: float = 8,
    heavy_threshold: float = 30,
    min_multiplier: float = 1.0,
    max_multiplier: float = 2.2,
) -> float:
    """Map a real per-frame vehicle count to a congestion multiplier via a
    simple, fully disclosed piecewise-linear scale — deliberately not
    dressed up as more precise than it is: at or below ``light_threshold``
    vehicles in frame, free-flow (``min_multiplier``, default 1.0x); at or
    above ``heavy_threshold``, saturated (``max_multiplier``, default
    2.2x — comparable order of magnitude to `congestion.py`'s own synthetic
    evening-peak ceiling); linearly interpolated in between. The default
    thresholds are a reasonable starting guess for a single-lane urban
    junction frame, not a value derived from UVH-26 itself (this sandbox
    has never seen real UVH-26 frames to derive one from) — override them
    once real calibration data says otherwise.
    """
    if heavy_threshold <= light_threshold:
        raise ValueError("heavy_threshold must be greater than light_threshold")
    if vehicle_count <= light_threshold:
        return min_multiplier
    if vehicle_count >= heavy_threshold:
        return max_multiplier
    frac = (vehicle_count - light_threshold) / (heavy_threshold - light_threshold)
    return round(min_multiplier + frac * (max_multiplier - min_multiplier), 3)


def calibrate_multiplier_stats(coco: dict, vehicle_category_ids: set | None = None) -> dict:
    """Summarize a batch of annotated frames (e.g. all frames from one
    UVH-26 junction, or one time-of-day bucket) into calibration stats:
    the real vehicle-count distribution, and the congestion multiplier it
    implies via `density_to_congestion_multiplier`. These are the numbers
    you'd actually compare against `congestion.py`'s synthetic
    `rush_hour_multiplier()` output (baseline 1.05x, up to roughly 2.6x-
    3.5x at its two Gaussian peaks) to judge whether the synthetic curve
    over- or under-states real peak congestion for the junctions your
    frames came from.

    Raises ValueError if ``coco`` has no images (nothing to summarize) —
    fails loudly rather than silently returning a hollow "0 images"
    result that could be mistaken for a real all-empty finding.
    """
    counts = vehicle_counts_per_image(coco, vehicle_category_ids)
    values = list(counts.values())
    if not values:
        raise ValueError("coco dict has no images to summarize")
    multipliers = [density_to_congestion_multiplier(v) for v in values]
    return {
        "n_images": len(values),
        "mean_vehicle_count": statistics.mean(values),
        "median_vehicle_count": statistics.median(values),
        "min_vehicle_count": min(values),
        "max_vehicle_count": max(values),
        "mean_multiplier": round(statistics.mean(multipliers), 3),
        "median_multiplier": round(statistics.median(multipliers), 3),
    }


def blend_with_synthetic_multiplier(
    calibrated_multiplier: float, synthetic_multiplier: float, weight: float = 0.5
) -> float:
    """Blend a real calibrated multiplier (e.g. `calibrate_multiplier_stats`'s
    ``mean_multiplier`` for one junction's frames) with
    `congestion.py`'s existing synthetic `rush_hour_multiplier()` output for
    the same hour — a middle ground between "ignore the synthetic model
    entirely" and "ignore the real calibration entirely."

    ``weight`` is clamped to [0, 1]: 0.0 keeps the synthetic model
    completely unchanged (useful as a no-op sanity check), 1.0 trusts the
    calibrated number fully, anything in between linearly interpolates.
    """
    weight = max(0.0, min(1.0, weight))
    return round(synthetic_multiplier * (1 - weight) + calibrated_multiplier * weight, 3)
