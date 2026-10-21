# MAP02: two owner-private capture bundles — RGB repeatability

This follows Draft PR #427. It compares **the same BK2 movie-input positions
across two separately supplied local capture bundles**, using decoded RGB
pixel values rather than relying on PNG file bytes or PNG metadata.

**Purpose:** expose differences between two screenshot sets that purport to
contain the same movie-input indices. Repeated identical screenshots are
useful for reproducibility, but neither two folders nor two matching logs
prove two actual Octoshock/PlayStation executions.

## Owner-local procedure

Keep the original movie, PS1 disc/BIOS, private plan, logs and PNG files
outside the GitHub repository. Run the capture Lua script from PR #421
twice, separately from power-on with **fresh private output directories**,
and identical BizHawk display settings, read-only PLAY movie and Octoshock.
Do not simply copy the first capture folder into another directory.

With source artifacts stored privately, run:

    umask 077
    python3 -m tools.map02_private_dual_capture_rgb_repeatability \
      /private/vandalhearts.bk2 \
      /private/vh-map02-review-plan.txt \
      /private/vh-map02-run1-console.log /private/vh-map02-run1-png \
      /private/vh-map02-run2-console.log /private/vh-map02-run2-png \
      --private-report-output /private/vh-map02-dual-rgb-report.json

If the movie-input review plan used different selection bounds, specify
the original --min-neutral-frames, --max-neutral-frames,
--after-input-frame and --before-input-frame values. By default the
per-pixel RGB difference threshold is **zero**, because this checks
repeatability rather than scene change. A positive threshold changes
only the numeric fraction-above-threshold metric, not the strict
pixel-equality verdict.

The verifier performs the full direct-owner-BK2 source → plan → Lua marker
→ PNG envelope/IDAT integrity audit from PR #424 **once per supplied
capture bundle**. It checks distinct log paths and distinct image roots,
and refuses screenshot symlinks/nonregular files or underlying file
inodes reused across the two bundles, including across different movie
input positions.

For each of up to 30 planned screenshots (10 groups of before, middle,
after), it decodes the image to RGB using PR #427's fail-closed PNG
decoder. It requires equal screenshot dimensions across paired capture
sets and compares pixel values, not file compression or PNG metadata.

The resulting **owner-private** JSON reports aggregate exact RGB match
count, byte-identical PNG count, count of RGB discrepancies and a
per-position list ranked by largest changed-pixel fraction. A screenshot
with different tEXt PNG metadata but identical decoded pixels counts
as a pixel match and a PNG-byte mismatch. The report includes review
group numbers/role but **no screenshot file paths, raw movie-input frame
numbers, image bytes, hashes or decoded RGB buffers**. It is saved only
to a new owner-only file (0600) outside the Git checkout; overwriting
an existing file is refused.

## Evidence limitations

This is **not** a cryptographic proof of two independent emulator
executions. An adversary or faulty tool could construct two perfectly
consistent sets of logs and PNGs. It does not establish actual PS1
controller delivery, source/native GPU or VRAM pixels, movie-to-displayed
frame timing, game scene identity, MAP02, or a tactical battle state.
All those report flags remain false. Differing RGB values can come
from OSD, frontend filters or genuine emulation nondeterminism. Even
exact pixel equality could be an unchanging screen shown at the wrong
movie position.

If the two sets differ, inspect that local group and the BizHawk display
settings; do not automatically infer a scene transition. The tool also
refuses indexed-color, 16-bit, interlaced or transparent PNG because
the decoder deliberately does not implement their display compositing.

CI creates only **fictional tiny PNGs and filenames, mocked BK2 audits
and mock log paths**. Never upload your original BK2/PS1 disc/BIOS,
private plans, real PNGs or console logs to GitHub or GitHub Actions.
Keep this pull request Draft until genuine owner-local emulator
observations can support stronger conclusions.
