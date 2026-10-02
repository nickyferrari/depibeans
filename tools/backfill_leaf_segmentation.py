"""Add leaf segmentation to one completed DEPI fluorescence observation."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parents[1]
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from depibeans.leaf_segmentation import update_observation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path)
    parser.add_argument("--inset-pixels", type=float, default=8)
    args = parser.parse_args()
    result = update_observation(args.observation, inset_pixels=args.inset_pixels)
    segmentation = result.get("segmentation", {})
    print(f"{segmentation.get('status', 'unavailable')}: {len(segmentation.get('regions', []))} regions")


if __name__ == "__main__":
    main()
