#!/usr/bin/env python3
"""Assert NeXium truly rendered the optional MAP02 battle mode and inputs.

Only newly designed asset-free battle pixels are compared. The test is
independent from synthetic PS1 PCSX MIPS/VBlank logs and never claims the
original retail MAP02 was executed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops

WIDTH, HEIGHT = 1280, 720
HERO = (86, 190, 244)
ENEMY = (235, 89, 98)
GRID_X, GRID_Y, CELL = 352, 100, 72


def load_screenshot(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    if image.size != (WIDTH, HEIGHT):
        raise ValueError(f"{path.name}: wrong NeXium screenshot dimensions {image.size}")
    return image


def count_pixels(image: Image.Image, color: tuple[int, int, int],
                 x: int, y: int, width: int = 38, height: int = 38) -> int:
    # Captured windows may have minor GPU byte-quantization variations.
    return sum(
        1 for rgb in image.crop((x, y, x + width, y + height)).getdata()
        if max(abs(a - b) for a, b in zip(rgb, color)) <= 10
    )


def hero_pixels(image: Image.Image, x: int, y: int) -> int:
    return count_pixels(image, HERO, GRID_X + CELL * x + 17,
                        GRID_Y + CELL * y + 17)


def enemy_pixels(image: Image.Image, x: int, y: int) -> int:
    return count_pixels(image, ENEMY, GRID_X + CELL * x + 17,
                        GRID_Y + CELL * y + 17)


def region_diff(first: Image.Image, second: Image.Image,
                bounds: tuple[int, int, int, int]) -> int:
    diff = ImageChops.difference(first.crop(bounds), second.crop(bounds))
    return sum(
        1 for rgb in diff.getdata()
        if max(rgb) > 30
    )


def audit(evidence: Path) -> dict[str, int]:
    original, battle, moved, enemy_turn, reset = (
        load_screenshot(evidence / (name + ".png"))
        for name in ("original", "battle", "moved", "enemy", "reset")
    )
    # The original prototype title is "VANDAL HEARTS", whereas optional
    # playable mode renders "MAP02 BATTLE DEMO" using the same tiny font.
    title_changed = region_diff(original, battle, (65, 20, 760, 76))
    title_after_reset = region_diff(battle, reset, (65, 20, 760, 76))
    # Small text/GUI differences can vary between frames under Lavapipe.
    # A reset to the original legacy screen differs by >1000 pixels, while
    # correctly restored battle titles can differ by a few hundred.
    print(f"NeXium battle mode title changed={title_changed}, reset_delta={title_after_reset}")
    if title_changed < 1000 or title_after_reset > 450:
        raise ValueError(
            f"NeXium did not enter/stay in standalone MAP02 battle screen "
            f"(changed={title_changed}, reset_title_diff={title_after_reset})"
        )
    first_hero = hero_pixels(battle, 1, 2)
    moved_old = hero_pixels(moved, 1, 2)
    moved_new = hero_pixels(moved, 2, 2)
    after_reset_hero = hero_pixels(reset, 1, 2)
    if not (first_hero > 500 and moved_old < 200 and moved_new > 500
            and after_reset_hero > 500):
        raise ValueError(
            f"NeXium A/Right/A or Y reset did not move/restore hero "
            f"(initial={first_hero}, old={moved_old}, "
            f"new={moved_new}, reset={after_reset_hero})"
        )
    first_enemy = enemy_pixels(battle, 5, 2)
    after_end_enemy = enemy_pixels(enemy_turn, 5, 2)
    reset_enemy = enemy_pixels(reset, 5, 2)
    if not (first_enemy > 500 and after_end_enemy < 200 and reset_enemy > 500):
        raise ValueError(
            f"NeXium X end-turn or Y reset did not advance/restore enemy "
            f"(initial={first_enemy}, turn={after_end_enemy}, reset={reset_enemy})"
        )
    return {
        "title_changed_pixels": title_changed,
        "hero_move_pixels": moved_new,
        "enemy_before_pixels": first_enemy,
        "enemy_after_pixels": after_end_enemy,
        "reset_hero_pixels": after_reset_hero,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    stats = audit(args.evidence_dir)
    print(
        "VH_MAP02_NEXIUM_BATTLE_PASS "
        "mode_switch=1 ally_move=1 enemy_turn=1 deterministic_reset=1 "
        "original_retail=0"
    )
    print(
        "Runtime screenshot counts (non-sensitive): " +
        " ".join(f"{key}={value}" for key, value in stats.items())
    )


if __name__ == "__main__":
    main()
