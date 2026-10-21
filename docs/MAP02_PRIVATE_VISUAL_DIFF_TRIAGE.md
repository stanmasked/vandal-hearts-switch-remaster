# MAP02: private visual-difference review after BK2 capture audit

This follows Draft PR #424. The prior stage validates the source BK2,
capture plan, Lua console markers and local PNG structure. The new stage
compares **decoded RGB pixels** of those PNGs, not mere file hashes.
This does **not** identify MAP02 or authenticate PS1 emulation.

## Owner-local execution

Keep the original Vandal Hearts USA BK2, disc, PS1 BIOS, capture plan,
raw log and screenshot files in private folders outside GitHub.
After actual owner-local read-only BizHawk/Octoshock playback using
the prior scripts, run:

    umask 077
    python3 -m tools.map02_private_visual_diff_triage \
      /private/vandalhearts.bk2 \
      /private/vh-map02-review-plan.txt \
      /private/vh-map02-console.log \
      /private/vh-map02-review-png \
      --private-report-output /private/vh-map02-visual-review.json

If the capture plan uses nondefault quiet-span limits, pass the same
--min-neutral-frames, --max-neutral-frames, --after-input-frame
and --before-input-frame values to this tool.

The complete BK2-to-PNG capture chain is verified **first**.
The tool then decodes before/middle/after screenshots, reconstructs
PNG filters 0–4 and compares RGB pixel values. It refuses corrupt PNG
CRC/zlib/scanline data, mismatched screenshot sizes and unsupported
pixel formats instead of inferring incorrect colors.

Supported formats: 8-bit noninterlaced grayscale, RGB, opaque
grayscale+alpha and opaque RGBA, at most 4 megapixels per screenshot.
Indexed, 16-bit, Adam7 and nonopaque images are intentionally refused,
because the code does not implement their precise display compositing.

Each local report gives the zero-based BK2 input indices for the three
frames, actual RGB mean absolute channel differences (0..255) and the
fraction of pixels with an average RGB difference strictly above 32
(adjustable via --pixel-change-threshold). It also labels a prominent
*unmasked pixel difference* if at least 25% of pixels exceed the
threshold and mean RGB channel difference reaches 24 for one adjacent
image pair. Groups are sorted by changed-pixel fraction, NOT by MAP02
probability.

The report is saved with 0600 permissions, only to an explicit new
absolute filename outside any Git checkout. No image bytes, filename
list or pixel data are copied into its JSON. Standard output contains
only counts of groups and prominent pixel differences. Do not upload
the report either: it contains private BK2-derived input coordinates.

## Interpretation and limitations

Pixel differences are **not** scene transitions. Animation, cursors,
menus, postprocessing, scaling and overlays can change large fractions
of a screenshot. A real scene boundary might be subtle or happen
between captured frames. Matching RGB pixels can also come from
different PNG file metadata. The program does not authenticate actual
Octoshock playback, PS1 input delivery, displayed-frame offset,
original game disc/firmware, MAP02, or source/native GPU/VRAM evidence.
The corresponding evidence flags remain FALSE on every result.

Only invented small PNGs, fake frame positions and mocked BK2 audit
data are used in GitHub Actions. Never send the owner's real BK2, PS1
disc/BIOS, screenshots, input logs, frame plans or report into public
CI. Keep all related PRs Draft until real owner-local observation.
