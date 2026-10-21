# MAP02 BK2 — private pre-existing animation filter

An experimental **raster witness**, stacked on [Draft #422](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/422). It does not identify the original game's MAP02 scene. Its purpose is to avoid mistaking **pre-existing animated screen regions** for a new stable screen appearing at a manually labelled candidate.

## Private input protocol

Supply two separately saved, owner-local BizHawk Octoshock replay datasets. Both sets must have **at least four** chronological observations with manually assigned labels:

1. Earlier `pre_map02` — the preceding visual baseline.
2. Later `pre_map02` — the *last* pre-candidate image, at most **120 emulator counters** after the earlier pre-image.
3. First `map02_candidate` — at most **120 counters** after the last pre-image.
4. First following `post_map02` — at most **120 counters** after the candidate.

All frames must be strictly after the known Start capture ending at counter 1663 and within the inspected 933,949-frame BK2. Identical labels, input counters and decoded RGBA rasters must be observed in both separately supplied evidence sets. The upstream #422 validator additionally requires at least 1% of stable changed candidate-to-post pixels across four screen tiles, before this extra test runs.

The new test excludes **every pixel that already changed** between the two pre-candidate images (including alpha-only changes). Only pixels with the **same complete RGBA value in both pre images**, that change at the candidate, and remain **exactly equal candidate→post**, are counted. The remaining pixels must cover at least 1% of the entire screenshot (minimum 16 pixels) and at least four tiles of a 4×4 screen grid.

For instance, 16 stable new pixels across four or more tiles can pass despite a moving cursor elsewhere. A fully animated background or a frame where only 15 newly stable pixels survive cannot pass.

Use Python + Pillow on the owner's private machine:

```bash
umask 077
python3 -m pip install 'Pillow>=10,<12'
python3 -m tools.verify_map02_private_animation_baseline \
  /private/vh-bk2-inspection.json /private/vh-start-report.json \
  --first-markers /private/run1/candidate-markers.log \
  --first-manifest /private/run1/candidate-manifest.json \
  --first-images /private/run1/images \
  --second-markers /private/run2/candidate-markers.log \
  --second-manifest /private/run2/candidate-manifest.json \
  --second-images /private/run2/images
```

The output contains only boolean test results and a stable schema identifier, not screenshot bytes, BK2 movie contents, paths, hashes or specific candidate counters.

## Interpretation and limits

**Passing proves only that the supplied images meet this particular temporal/spatial heuristic.** The pre-existing animation mask is sampled twice, so it cannot rule out an animation that happens to be still during both baseline snapshots, a stable menu overlay, fade, unrelated full-screen screen or scene. It may reject genuine MAP02 if the background is already moving. No start-of-MAP02 classifier, source PS1 game execution, movie-to-video timing, independent emulator-process proof or GPU/VRAM witness exists here. Original movie, owner game/BIOS and screenshots stay private.

GitHub Actions uses only invented 16×16 PNGs and fake log data on Ubuntu Python 3.9/3.11 and Intel macOS Python 3.11. Keep this and parent PRs in Draft; **do not merge** or modify `main`.
