# MAP02 — private Start frame screenshot anchor (before MAP02)

This supplements the BK2 movie-input inspector (Draft PR #390), Lua movie
handshake (#396/#399), and private image integrity validator (#402/#403).

The first owner BK2 Start **press onset** is at movie input index 1661
(zero-based). BizHawk commonly exposes that input as
movie.getinput(emu.framecount()-1, 1). This convention is supported by
BizHawk's bundled Input_Display.lua, but remains a **candidate mapping
of movie index to displayed screenshot**, not independent proof that
the PS1 core applied an input on the same displayed frame.

## Owner-local two-run protocol (original game/BK2 remain private)

Prerequisites: a compatible original Vandal Hearts (USA) PS1 disc/BIOS,
Octoshock and the user's original BK2. Movie should replay from power-on
in PLAY mode with read-only enabled. Ensure the movie is not simply
seeking after a savestate. Configure identical screenshot resolution,
scaling, OSD visibility and video filters for both independent runs.

1. Create two **separate, access-restricted** directories outside the
   GitHub working tree. Do not commit screenshots or console logs.
2. Before starting the first replay, set the environment variable
   VH_PRIVATE_PNG_DIR to the **absolute path of the first directory**.
   For a POSIX shell, e.g.:

       umask 077
       mkdir -p /private/vh-start-run1 /private/vh-start-run2
       export VH_PRIVATE_PNG_DIR=/private/vh-start-run1

   Start BizHawk from that same environment, open the original movie
   and start it from the beginning. Load the Lua script
   tools/map02_bizhawk_private_start_anchor_capture.lua **before**
   input index 1660. Do not load it from an already advanced state.
3. The script verifies the loaded movie length (933949 frames), mode
   PLAY and read-only state. It checks the Start button is released
   at index 1660 and pressed at index 1661. At emulator counters
   1661, 1662 and 1663 it requests local client.screenshot(path).
   It verifies a PNG file header after each write and emits a bounded
   marker with both counter and candidate BK2 input index. Preserve
   the original console log **locally** as run-1.log.
4. Restart a fresh second power-on replay, using the second private
   capture directory (VH_PRIVATE_PNG_DIR=/private/vh-start-run2);
   preserve its console output privately as run-2.log.
5. Prepare a private BK2 inspector JSON, e.g.:

       python3 -m tools.inspect_map02_private_bk2 \
         /private/vandalhearts.bk2 > /private/vh-inspection.json

   Never supply the movie or screenshot files to GitHub Actions.
6. Compare the two **private** capture runs:

       python3 -m tools.verify_map02_private_start_anchor_reruns \
         /private/vh-inspection.json \
         /private/run-1.log /private/vh-start-run1 \
         /private/run-2.log /private/vh-start-run2

The verifier requires the exact three frame counters, the Start onset
at movie index 1661, two distinct log paths and two distinct image
directories; checks PNG structure/CRC, bounded decoded image data and
byte-exact SHA-256 consistency between runs. The output never contains
filenames, user paths, raw screenshot bytes or hashes. It does not
need (or upload) original game data, and never triggers network access.

**Limitations:** The script records emu.framecount() at the instant
client.screenshot() is called. Emulator frontend rendering may lag the
core, include overlays/filters, or use a different frame convention.
Byte-identical PNGs across two runs are a strict repeatability test,
not a visual scene recognition result, input-to-video offset
measurement, gameplay-state proof or MAP02 scene identification.
PNG equality can also fail because screenshot settings or metadata
differ even if the underlying emulated pixels are identical.

This known Start anchor occurs **long before MAP02** and must never be
labelled as a MAP02 candidate. Identifying MAP02 later requires genuine
owner-local replay observations and comparison with source/native GPU
or VRAM witnesses. All CI checks use fabricated movie input and
1x1 PNGs; actual BizHawk replay has not been run by CI.
