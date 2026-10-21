# MAP02 — owner-private visual candidate integrity handoff

This protocol follows Draft PRs #390 (original BK2 input reader), #392
(emulator counter markers), #396 (bounded movie-input handshake) and #399
(executable Lua mock regression tests).

**It does not run the PlayStation game.** It does not recognize MAP02 in
images. It merely validates locally retained PNG file envelopes and hashes,
and compares manually reported screenshot frame numbers with previously
captured movie-PLAY marker counters. Scene labels are the observer's
unverified impressions, not assertions accepted by GPU/VRAM parity tests.

## Prerequisites (private computer, never public CI)

1. Start exact owner-private Vandal Hearts (USA) BK2 playback in a compatible
   BizHawk Octoshock setup; confirm original game/BIOS and movie sync locally.
   Use the established Lua marker script to record a counter when capturing
   each screenshot of the previous scene, possible MAP02 transition and later
   scene. The script's counter-to-input convention remains a *candidate*.
2. Keep screenshots, marker console log and BK2 inspection report in an
   access-restricted directory **outside the GitHub checkout**.
3. Make a private JSON manifest listing only manually observed screenshots
   whose emulator counters match the marker log. Compute file SHA-256 locally
   with: shasum -a 256 frame-before.png

Example local manifest (numbers are **synthetic, not actual MAP02 offsets**):

    {
      "schema": "vh.map02.private-visual-candidates.v1",
      "observations": [
        {
          "emulator_counter": 100,
          "movie_input_candidate": 99,
          "label": "pre_map02",
          "png_file": "frame-before.png",
          "sha256": "REPLACE_WITH_REAL_64_CHAR_LOWERCASE_HEX_DIGEST"
        },
        {
          "emulator_counter": 200,
          "movie_input_candidate": 199,
          "label": "map02_candidate",
          "png_file": "frame-candidate.png",
          "sha256": "REPLACE_WITH_REAL_64_CHAR_LOWERCASE_HEX_DIGEST"
        }
      ]
    }

Capture real scene images and fill hashes **only locally**.
Accepted labels: pre_map02, map02_candidate, post_map02.
Image names must be plain PNG basenames; paths, symlinks, invalid
or duplicate files are refused. Manifest needs an earlier pre_map02
and a later map02_candidate. Counters must match PR #392's observed
PLAY markers. The accepted interval is never a proven scene boundary.

Run from an owner-local checkout:

    umask 077
    python3 -m tools.verify_map02_private_visual_candidates \
      /private/vh-bk2/inspection.json \
      /private/vh-bk2/markers.txt \
      /private/vh-bk2/private-observations.json \
      --image-root /private/vh-bk2/screenshots

The report contains counters, an *unverified candidate* bracket and only
booleans for PNG container CRC and SHA-256 checks. It never prints
screenshot filenames, paths, image bytes or hashes. Valid PNG structure
is not the same as decoded/rendered PS1 pixels; success cannot attest that
an image depicts the claimed gameplay moment.

**Required before true MAP02 proof:** original-disc/BIOS authentication,
genuine deterministic PS1 playback, independently calibrated
movie-to-video frame relation, confirmation of scene by observable game
state, source/native GPU/VRAM evidence connected by existing witness tools.

GitHub CI uses tiny invented 1x1 PNGs and fake frame counters **only**.
The owner's BK2, original inputs, disc, BIOS, screenshots and raw marker
logs must not enter CI or public GitHub. Keep this work Draft.
