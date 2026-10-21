# MAP02 — independent BK2 CSV vs private Start screenshot input states

This stage closes a specific gap in Draft PR #407: the old screenshot
repeatability validator checked the first Start onset (at input index
1661) but did **not** compare the button state at the third captured
index (1662) against the original movie. Two matching console logs could
therefore both report a **wrong** third-frame Start state and still pass.

The correct state of Start at movie input index 1662 must be **read from
the owner's BK2**, not assumed to be a release. In particular, the first
onset at 1661 does not imply that Start was released at 1662.

## Owner-local instructions

1. Generate a local sanitized inspection JSON and its private events CSV
   covering zero-based BK2 input indices 1659..1663. Do this outside
   the public GitHub checkout and use access-restricted permissions.

       umask 077
       mkdir -p /private/vh-start-source
       python3 -m tools.inspect_map02_private_bk2 \
         /private/vandalhearts.bk2 \
         --start-frame 1659 --window-frames 5 \
         --private-events-csv /private/vh-start-source/events.csv \
         > /private/vh-start-source/inspection.json

2. Follow the owner-local two-run procedure in
   docs/MAP02_PRIVATE_START_ANCHOR_SCREENSHOTS.md to collect the three
   PNGs at counters 1661, 1662, 1663 and their console logs, **in two
   separately retained local directories**. This requires a compatible
   BizHawk/Octoshock setup with the owner's original BK2 and PS1 assets.

3. Cross-check the exact 3 Start button states in each Lua log against
   the **independently exported** source BK2 CSV:

       python3 -m tools.verify_map02_private_start_anchor_against_bk2_csv \
         /private/vh-start-source/inspection.json \
         /private/vh-start-source/events.csv \
         /private/run-1.log /private/vh-start-run1 \
         /private/run-2.log /private/vh-start-run2

This checker rejects mismatched source movie length, missing Start at
index 1661, incomplete CSV frame coverage, inconsistent pressed/released
edges, malformed Lua markers, inconsistent third-frame button state,
corrupted screenshot PNGs and mismatched PNG bytes between runs.

It reports only sanitized status booleans and fixed, **known** frame
counters; it does not print the private CSV, frame-state detail, image
bytes, hashes, user paths or original BK2 contents. It never accesses
the original game or BIOS and does not create network traffic.

## Limitations

A PASS demonstrates only that *two supplied local capture bundles*
agree in their recorded movie-input labels (including index 1662) with
one supplied BK2 CSV, and that their screenshots are byte-identical,
syntactically valid PNGs. A user or process could still create those
logs and screenshots without running the PS1 core. Two local folders
do not independently authenticate two genuine emulator runs.

Even with real Octoshock playback, front-end screenshots may lag or
contain postprocessing. The observed Start input index does not by
itself establish the input-to-visible-frame offset. This first Start
is **not** the MAP02 boundary. Scene identification, real emulator
execution, source/native GPU/VRAM evidence and true display timing
remain unverified.

GitHub Actions tests use fully invented BK2 CSV events, tiny synthetic
PNG bytes and fabricated Lua logs, **never** owner BK2, PS1 disc/BIOS,
screen captures or raw private controller inputs. Keep Draft.
