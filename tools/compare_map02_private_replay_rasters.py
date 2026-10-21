#!/usr/bin/env python3
"""Owner-local, two-replay PNG raster comparison for *unverified* MAP02 candidates.

Both runs must independently pass the pre-existing BK2 PLAY-marker and PNG
integrity checks. This checks repeatability of *provided* decoded screenshots,
not authentic replay, distinct emulator processes or original PS1 MAP02.
Never publish private screenshots, log contents, PNG digests or BK2 data.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import warnings

from PIL import Image, UnidentifiedImageError

from tools.validate_map02_private_replay_markers import _read_regular
from tools.verify_map02_private_visual_candidates import (
    MAX_MANIFEST, MAX_SHOTS, read_png_private, verify as verify_visual,
)

SCHEMA = "vh.map02.private-two-replay-raster.v1"


def _observations(path: Path) -> list[dict]:
    obj = json.loads(_read_regular(path, MAX_MANIFEST))
    if not isinstance(obj, dict) or not isinstance(obj.get("observations"), list):
        raise ValueError("malformed private image manifest")
    return obj["observations"]


def _raster_key(data: bytes) -> tuple[int, int, bytes]:
    # Parent verified bounded IDAT, CRC, headers and SHA-256 first.
    # Pillow additionally reconstructs filters and actual displayed pixels.
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as image:
            image.load()
            if (image.format != "PNG" or not 1 <= image.width <= 8192
                    or not 1 <= image.height <= 8192
                    or image.width * image.height > 20_000_000):
                raise ValueError("invalid captured raster dimensions")
            rgba = image.convert("RGBA")
            # Include dimensions, not just packed RGBA pixel bytes.
            value = hashlib.sha256(
                f"{rgba.width}:{rgba.height}:RGBA:".encode("ascii")
                + rgba.tobytes()
            ).digest()
            return rgba.width, rgba.height, value


def compare(
    inspection: Path,
    first_markers: Path, first_manifest: Path, first_images: Path,
    second_markers: Path, second_manifest: Path, second_images: Path,
) -> dict:
    # No run can reuse the other run's *same* private manifest/log/root path.
    for a, b in ((first_markers, second_markers),
                 (first_manifest, second_manifest),
                 (first_images, second_images)):
        if Path(a).resolve(strict=True) == Path(b).resolve(strict=True):
            raise ValueError("both claimed replays reuse one evidence source")

    first = verify_visual(inspection, first_markers, first_manifest, first_images)
    second = verify_visual(inspection, second_markers, second_manifest, second_images)
    if (first["integrity_checked_png_count"] !=
            second["integrity_checked_png_count"]):
        raise ValueError("different number of frame observations")
    frames_a = _observations(first_manifest)
    frames_b = _observations(second_manifest)
    if len(frames_a) > MAX_SHOTS or len(frames_b) != len(frames_a):
        raise ValueError("unexpected screenshot count")
    matched = 0
    for a, b in zip(frames_a, frames_b):
        triple_a = (a["emulator_counter"], a["movie_input_candidate"], a["label"])
        triple_b = (b["emulator_counter"], b["movie_input_candidate"], b["label"])
        if triple_a != triple_b:
            raise ValueError("replays have unequal input-frame or scene labels")
        raster_a = _raster_key(read_png_private(first_images, a["png_file"]))
        raster_b = _raster_key(read_png_private(second_images, b["png_file"]))
        if raster_a != raster_b:
            raise ValueError("decoded PNG pixels differ across claimed replays")
        matched += 1
    if first["manual_candidate_interval_counter_exclusive_inclusive"] != (
            second["manual_candidate_interval_counter_exclusive_inclusive"]):
        raise ValueError("candidate intervals differ")
    return {
        "schema": SCHEMA,
        "paired_frames": matched,
        "decoded_rgba_rasters_equal": True,
        "manual_frame_labels_and_markers_equal": True,
        "two_distinct_private_evidence_paths": True,
        "png_idat_streams_checked": True,
        "repeatability_of_provided_images": True,
        "independent_emulator_runs_authenticated": False,
        "movie_to_video_sync_authenticated": False,
        "original_ps1_game_authenticated": False,
        "map02_scene_frame_identified": False,
        "ps1_gpu_vram_parity_proven": False,
        "owner_images_or_private_hashes_uploaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inspection_json", type=Path)
    parser.add_argument("--first-markers", type=Path, required=True)
    parser.add_argument("--first-manifest", type=Path, required=True)
    parser.add_argument("--first-images", type=Path, required=True)
    parser.add_argument("--second-markers", type=Path, required=True)
    parser.add_argument("--second-manifest", type=Path, required=True)
    parser.add_argument("--second-images", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compare(args.inspection_json, args.first_markers,
                         args.first_manifest, args.first_images,
                         args.second_markers, args.second_manifest,
                         args.second_images)
    except (ValueError, TypeError, KeyError, OSError, UnidentifiedImageError):
        parser.error("private two-replay raster consistency not demonstrated")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
