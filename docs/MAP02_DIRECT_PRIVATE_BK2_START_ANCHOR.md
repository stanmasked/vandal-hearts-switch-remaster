# MAP02 — direct source BK2 inspection for private Start anchor

This is an optional stricter follow-up to Draft PR #412. Previous checks
compared two screenshot bundles against a **separately supplied CSV/JSON**
that had originally been derived from the owner's movie. The caller could
accidentally pass an unrelated or stale CSV. This tool instead scans the
**private BK2 archive directly**, end-to-end, at owner-local execution time.

## Owner-local workflow

The original game disc, PS1 firmware, and movie must remain private.
This script does not launch BizHawk and does not access original PS1
game/BIOS content. Use two **separately captured** read-only Octoshock
runs from the previous Stage #407, recorded to owner-local PNG directories
outside the checkout.

Example, when both private screenshot runs already exist:

    umask 077
    python3 -m tools.verify_map02_direct_private_bk2_anchor \
      /private/vandalhearts.bk2 \
      /private/run-1.log /private/vh-start-run1 \
      /private/run-2.log /private/vh-start-run2

No CSV export, inspection report, temporary raw input dump, screenshot
manifest, or hash output is created by this tool.

### Verification boundaries

1. Reject nonregular/symlink BK2 archives, excessive compressed member
   sizes and unexpected ZIP entries; read the full input stream so the
   ZIP CRC is verified. Require Vandal Hearts (USA), PSX, Octoshock,
   original one-controller/no-memory-card synchronization settings and
   the exact 17-button LogKey ordering.
2. Recompute the recorded input aggregate known from earlier **private**
   BK2 inspection: **933949 frames**, **20152 button-state change
   frames**, **13150 new button-press onsets**, **zero nonneutral analog
   frames** and the **first Start press at zero-based index 1661**.
   These counts are a recording fingerprint only; the archive header
   and events could be forged, and this is NOT a security identity proof.
3. Recover actual Start-held states directly at BK2 indices **1660,
   1661 and 1662**. In particular, never guess whether Start was
   released at 1662 merely because it was pressed at 1661.
4. Independently parse the two Lua console logs and their locally
   captured PNG folders. Check the exact counters (1661–1663),
   recorded Start states, unique bundle paths, structurally valid PNGs
   including bounded IDAT zlib and SHA-256 byte equality between runs.

The result only reports fixed frame numbers and sanitized boolean
status. It never emits raw controller states, an owner-specific source
digest, private file paths, PNG bytes, actual screenshot hashes or
original movie archive content.

**A PASS does not prove real PS1 emulation.** The supplied Lua logs,
screenshots and BK2 headers could still have been manufactured. It also
cannot independently calibrate the relationship between movie input
and an actual displayed PS1 video frame, establish the game's scene,
identify MAP02, or prove any GPU/VRAM observation. This Start occurs
well before MAP02.

GitHub CI tests this code using an explicitly **fictional** BK2 with
933949 synthetic frames, invented button-event aggregates and tiny
fabricated RGB PNGs. The user's original BK2, disc, BIOS, controller
input files, raw logs and screenshots must NEVER be uploaded to public
GitHub or GitHub Actions. All changes remain in a Draft PR.
