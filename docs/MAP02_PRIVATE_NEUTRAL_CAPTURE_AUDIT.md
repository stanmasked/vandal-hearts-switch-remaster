# MAP02 — owner-local audit of BK2 capture-plan, Lua log and screenshots

Draft follow-up to PR #421 (private capture-plan and read-only BizHawk
screenshot helper). The audit **does not start BizHawk** or infer scene
content. It only tests the consistency of files that the owner provides.

## Why this audit exists

A capture script can produce console log lines without having completed
all captures; an old plan may be paired with a different source BK2; a
screenshot filename may be missing or replaced; or a frame counter in a
log may be shifted by one. The capture stage itself does not verify
every PNG's zlib data after writing. This tool refuses those cases
rather than reporting an unqualified screenshot success.

## Private operation

Keep the owner BK2 movie, plan, raw console log and PNG directory
**outside the repository and public CI**. A plausible local sequence is:

1. Generate the frame plan from the owner's private BK2 with
   tools/map02_private_bk2_capture_plan.py (Draft PR #421).
2. Play that movie from power-on, read-only, in the owner's local
   BizHawk/Octoshock setup. Load
   tools/map02_bizhawk_private_neutral_capture.lua before the first
   planned frame and keep its complete console output locally.
3. Audit all files together:

       umask 077
       python3 -m tools.verify_map02_private_neutral_capture_chain \
         /private/vandalhearts.bk2 \
         /private/vh-map02-review-plan.txt \
         /private/vh-map02-console.log \
         /private/vh-map02-review-png \
         > /private/vh-map02-chain-report.json

   If the plan was generated with different quiet-span settings,
   pass the same values on the audit command:

       --min-neutral-frames 180
       --max-neutral-frames 1800
       --after-input-frame 1663
       --before-input-frame 933949

The script re-reads the **full source BK2** via the earlier bounded
inspector and reproduces the exact, canonical ASCII plan with the same
selection settings. It requires that all expected Lua markers appear
once in the same order, every recorded counter equals the source movie
input index plus one, and exactly one completion marker follows the
last record. Unexpected capture ERROR markers are fatal.

For each expected frame it derives the filename from the plan rather
than trusting a name from the log. It refuses missing, symbolic-link,
hard-linked-to-another-capture, or nonregular images; checks each PNG
signature/chunk CRC, bounded IDAT zlib stream and scanline structure;
and reads its SHA-256 bytes without exporting that digest.

The final JSON contains **counts and Boolean integrity indicators**,
but no image bytes, filesystem paths, raw button states, BK2 input
events, screenshot filenames or frame-specific hashes. The user should
not publish even this owner-specific report without checking its
contents.

## What passing the audit means—and does not mean

A passing audit shows that *provided files* agree on a bounded
**zero-based movie input** capture plan and carry structurally valid
PNG bytes. Lua's counter mapping of emu.framecount()-1 to BK2 input
remains uncalibrated as a **display timing** relationship.

The report explicitly does **not** authenticate a genuine BizHawk or
Octoshock execution, an original PlayStation disc/BIOS, PS1 execution
of the recorded controls, true screenshot provenance, a displayed
GPU/VRAM frame, a scene transition or MAP02 identification.
Identical image content at different input frames can be legitimate
(e.g., a long still image); such images are not discarded merely
because their pixel bytes match. Reusing the **same underlying file
inode** at multiple capture paths, however, is refused.

All GitHub Actions data for this stage are wholly invented: arbitrary
plan offsets, fake Lua console records and synthetic 1x1 RGB PNG
fixtures. Tests mock the source BK2 planner; no original private BK2,
disc/BIOS, raw controller inputs or actual screenshots enter CI.
Keep this PR Draft until owner-local observations are available.
