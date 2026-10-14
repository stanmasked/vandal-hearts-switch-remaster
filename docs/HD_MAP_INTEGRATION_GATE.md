# HD map integration gate — seam, UV, and palette checks

**Status:** test plan; runtime validation has not yet been performed.  
**Scope:** the 25 extracted 320×240 map backgrounds and their 3× comparison variants.  
**Goal:** preserve the original PS1 look while preventing edge seams, palette drift, UV shifts, and accidental replacement of unresolved texture records.

## Required inputs

- Original map backgrounds (read-only).
- Candidate 3× nearest-neighbor and 3× Lanczos images.
- A scene/frame showing the candidate asset in its intended renderer.
- If textured geometry is involved: source texture dimensions, UV coordinates, sampler/filter settings, and the texture-slot mapping used by that scene.

Do not commit copyrighted game assets to this repository. Keep them in a local working directory or a separately controlled artifact.

## Gate A — source integrity

1. Verify all 25 expected source files are present.
2. Record dimensions, mode, alpha range, unique RGBA colors, file size, and SHA-256.
3. Treat the source files as immutable. Never overwrite the originals with an upscale.
4. For nearest-neighbor 3× output, downsample with exact 3× block selection and require a zero-pixel mismatch against the source.
5. For Lanczos output, record interpolation differences; do not describe new intermediate colors as recovered detail.

**Pass:** every source has a manifest entry; nearest-neighbor round-trip has zero mismatches; any Lanczos differences are reported rather than hidden.

## Gate B — tile and texture seams

For every pair of assets that actually touches in a scene:

1. Identify the shared edge from scene/model metadata, not from similar filenames.
2. Compare the edge pixels after applying the renderer's real UV mapping and sampling mode.
3. Record edge color discontinuity at the join, including alpha where applicable.
4. Inspect at native output size and at 2× zoom. Check both static screenshots and any camera movement that could expose sampling seams.
5. Repeat with nearest-neighbor and Lanczos candidates. Do not add bleed pixels or alter edge colors until the original asset layout and sampler behavior are understood.

**Pass:** no new visible seam or one-pixel gap appears relative to the original reference. A numeric edge difference alone is not a failure if the source itself contains that boundary.

## Gate C — UV and dimensions

- Confirm texture width/height and atlas origin used by the loader.
- Confirm UVs are normalized against the correct image dimensions.
- Confirm crop rectangles remain inside the source image.
- Confirm any half-texel, clamp, wrap, or filtering rule matches the target renderer.
- Confirm that a 3× asset is paired with correspondingly scaled UV/crop coordinates, or is resampled back to the expected runtime dimensions. Do not mix these two strategies implicitly.
- Test the corners and center of every diagnostic textured face; compare expected source texels to sampled output.

**Pass:** no offset, stretching, crop overflow, or unintended texture bleeding is observed.

## Gate D — unresolved map 02 records

Texture-table slots 641 and 643 are documented as unresolved. Do not copy values from another map solely because the slot numbers match. First compare raw source bytes and loader interpretation, then compare against an original-game reference. Keep these records unchanged until the evidence establishes intended behavior.

## Required evidence bundle

For each tested scene, retain:

- scene/map identifier and asset variant;
- source and candidate SHA-256 values;
- renderer settings (filtering, wrap/clamp, scale, output resolution);
- screenshot before/after;
- machine-readable edge/UV findings;
- pass/fail result and a short explanation for every failure.

## Current status

- **Source dimensions / palette / alpha audit:** reported complete for 25 backgrounds.
- **Nearest-neighbor round-trip:** reported pass for 25/25 backgrounds.
- **Lanczos comparison:** generated, but it is interpolation and not neural detail restoration.
- **Runtime seam and UV checks:** pending; no pass is claimed.
- **Neural restoration:** not run.
