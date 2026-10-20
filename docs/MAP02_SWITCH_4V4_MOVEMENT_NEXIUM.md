# MAP02 — optional 4v4 real NeXium movement and opponent pursuit

This isolated follow-up is **stacked on Draft PR #262** but changes no renderer, input mapping, authored map JSON, current battle engine, or previous four-attack NeXium smoke. The parent PR's CI can finish without being restarted by this stage.

## Independent genuine-controller route

With the independently authored 4v4 capacity map loaded in the Switch NRO:

1. Capture original two-map legacy demo before entering the 4v4 mode via simultaneous **L+R**.
2. Confirm four allied and four opposing units appear at their authored locations.
3. Select the fourth ally at (0,3) using actual D-pad/A events. Try to move to blocked tile (3,2); it must **not** move and the selection stays available.
4. Move that same ally one tile to the unoccupied square (0,4). Its original square must empty and its new position must show the spent-action color.
5. Press actual **X** once: three adjacent enemies attack their neighboring allies, visibly decreasing HP; the fourth opponent follows the open path into (0,3), with no duplicate unit position.
6. Confirm the moved ally's action flag is cleared after the enemy phase. Press **Y** to restore original 4v4, then L+R and L to restore original map 1 exactly.

The oracle asserts tile colors, health-bar pixel counts and unchanged board screenshots rather than trusting log strings or process exit alone. NeXium screenshots/logs are uploaded as evidence from the real GitHub Actions job.

## Self-test and build checks

- `tests/run_map02_nexium_4v4_movement.py`: real X11/NeXium buttons, screenshot capture, and strict runtime image verification.
- `tests/test_map02_nexium_4v4_movement_oracle.py`: ten independently generated positive/negative screenshots to reject wall teleporting, missing legal move, absent opponent pursuit, missing damage, un-reset acted-state, wrong map, bad reset and wrong size. **These synthetic screenshots are not proof of running the game.**
- `.github/workflows/map02-nexium-4v4-movement.yml`: independent GCC-independent screenshot-oracle test job, canonical two-map JSON/header checks, actual devkitA64/libnx NRO build, and a real NeXium headless screenshot job.

## Limits

This remains an original, asset-free tactical demonstration on an 8x6 board with up to four units per faction. This is not a capture of the retail PlayStation MAP02 or a claim of full remake completion. A valid 4v4 NRO build cannot substitute for a successful emulator run. Keep Draft until host tests, the NRO gate and actual NeXium image proof succeed.
