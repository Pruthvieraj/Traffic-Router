#!/usr/bin/env python3
"""
calibrate_from_uvh26.py — run the real UVH-26 congestion calibration.

    python3 calibrate_from_uvh26.py path/to/annotations.json [--categories 10,11,...]

**This script needs to be run on YOUR OWN machine, not inside the sandbox
this project was built in.** That sandbox's outbound network access is
allowlisted to package registries only, so it cannot reach huggingface.co
to download UVH-26 itself — confirmed directly (a hard connection-level
rejection, not a slow download), not a "needs a paid key" limitation like
the D-Wave QPU / Google Routes integrations elsewhere in this project.
UVH-26 itself is completely free: https://huggingface.co/datasets/iisc-aim/UVH-26

Steps to actually run this for real, from a machine with normal internet
access:

    pip install huggingface_hub
    python3 -c "from huggingface_hub import snapshot_download; \
        snapshot_download('iisc-aim/UVH-26', repo_type='dataset', \
        allow_patterns=['UVH-26-Val/000/*'], local_dir='uvh26_sample')"
    python3 calibrate_from_uvh26.py uvh26_sample/UVH-26-Val/annotations_mv.json

(Pick ONE small subfolder via allow_patterns — the full dataset is ~90GB.
Adjust the annotation filename to whichever of UVH-26-MV/UVH-26-ST you
downloaded; both use the same COCO schema this script expects.)

What this prints: `src.vehicle_density_calibration.calibrate_multiplier_stats`'s
summary (real vehicle-count distribution + the congestion multiplier it
implies) for whatever COCO-format annotation file you point it at, plus a
one-line comparison against `congestion.py`'s synthetic rush_hour_multiplier()
peak so you can judge, with real numbers, whether the synthetic model over-
or under-states real peak congestion for the junctions in your sample.
"""

import argparse
import json
import sys

sys.path.insert(0, "src")

from congestion import rush_hour_multiplier  # noqa: E402
from vehicle_density_calibration import calibrate_multiplier_stats  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("annotations_path", help="path to a UVH-26 COCO-format annotations JSON file")
    parser.add_argument(
        "--categories",
        default=None,
        help="comma-separated category_id list to count (default: every category in the file)",
    )
    args = parser.parse_args()

    with open(args.annotations_path) as f:
        coco = json.load(f)

    category_ids = None
    if args.categories:
        category_ids = {int(c) for c in args.categories.split(",")}

    stats = calibrate_multiplier_stats(coco, vehicle_category_ids=category_ids)

    print(f"Frames summarized:        {stats['n_images']}")
    print(f"Vehicle count  mean/median/min/max: "
          f"{stats['mean_vehicle_count']:.1f} / {stats['median_vehicle_count']:.1f} / "
          f"{stats['min_vehicle_count']} / {stats['max_vehicle_count']}")
    print(f"Calibrated congestion multiplier  mean/median: "
          f"{stats['mean_multiplier']:.3f}x / {stats['median_multiplier']:.3f}x")

    synthetic_peak = max(rush_hour_multiplier(9.0), rush_hour_multiplier(18.5))
    print(f"\nFor comparison — congestion.py's synthetic rush-hour peak multiplier: {synthetic_peak:.3f}x")
    if stats["mean_multiplier"] > synthetic_peak:
        print("-> the real calibrated data implies MORE congestion than the synthetic model assumes.")
    elif stats["mean_multiplier"] < synthetic_peak:
        print("-> the real calibrated data implies LESS congestion than the synthetic model assumes.")
    else:
        print("-> the real calibrated data matches the synthetic model's peak almost exactly.")


if __name__ == "__main__":
    main()
