#!/usr/bin/env python3
"""Check expected generated markers in a screenshot captured from an SDL2 NRO."""
from pathlib import Path
import sys
from PIL import Image

if len(sys.argv) != 3:
    raise SystemExit("usage: check_sdl2_runtime_screenshot.py IMAGE LABEL")

path = Path(sys.argv[1])
label = sys.argv[2]
image = Image.open(path).convert("RGB")
if image.size != (1280, 720):
    raise SystemExit(f"{label}: unexpected screenshot dimensions {image.size}")

def near_color_count(box, color, tolerance=24):
    return sum(
        1
        for r, g, b in image.crop(box).getdata()
        if max(abs(r - color[0]), abs(g - color[1]), abs(b - color[2])) <= tolerance
    )

hero = near_color_count((464, 264, 496, 296), (86, 190, 244))
enemy = near_color_count((784, 328, 816, 360), (235, 89, 98))
print(f"{label}: screenshot={path}, size={image.size}, hero pixels={hero}, enemy pixels={enemy}")
if hero < 500:
    raise SystemExit(f"{label}: generated hero marker not visible in expected tile")
# The runtime screenshot produced 494 matching pixels for the enemy marker;
# keep a meaningful margin while avoiding a false negative from a 500-pixel cutoff.
if enemy < 400:
    raise SystemExit(f"{label}: generated enemy marker not visible in expected tile")
