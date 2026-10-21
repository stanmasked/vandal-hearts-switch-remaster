# MAP02 — owner-only contact sheet for Octoshock screenshot review

**Purpose:** Turn two owner-local BK2 capture bundles into one readable PNG
sheet **on the owner's computer**. This is a practical aid for a human to
compare what BizHawk appears to show at proposed review intervals. It does
not classify or authenticate a MAP02 scene.

This adds a human-review output to the existing capture chain in
[Draft #429](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/429),
which inherits source-BK2 validation, a bounded capture plan, read-only
Lua capture and PNG CRC/IDAT/RGB pixel integrity from Drafts #418–#427.
This branch is **parallel to**
[Draft #430](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/430)
(three-pre raster heuristics); these branches are not merged.

## Private local use on Intel Mac or Linux

First follow docs/MAP02_PRIVATE_NEUTRAL_CAPTURE_HANDOFF.md to make a
capture plan from the owner's own private BK2. Use the owner-held PS1
game/BIOS in BizHawk Octoshock for **two** read-only PLAY captures
from power-on, keeping video settings equal. Keep both private Lua logs,
screenshot directories and movie outside any Git checkout.

With Pillow installed only on the owner's machine:

    umask 077
    python3 -m pip install 'Pillow>=10,<12'

    python3 -m tools.map02_private_owner_rgb_contact_sheet \
      /private/vandalhearts.bk2 \
      /private/vh-map02-review-plan.txt \
      /private/vh-map02-run1-console.log /private/vh-map02-run1-png \
      /private/vh-map02-run2-console.log /private/vh-map02-run2-png \
      --owner-private-output /private/vh-map02-owner-review.png

Use the same optional input-range bounds that created the original
capture plan, if different from the default arguments.

The tool **first revalidates both complete source chains** using PR
#429: owner-private BK2, canonical capture plan, Lua log, screenshot
CRC/IDAT and decoded RGB values. It refuses reused source objects,
hardlinked screenshots, unsupported/corrupt PNGs and bad frame plans.

By default it assembles **before, neutral middle and after** screenshots for
each of up to 10 review groups, two runs each. All six panels per group
are marked with their run number, exact decoded-RGB MATCH or DIFF,
and a **private** movie-input index. A prominent banner states
UNVERIFIED / NOT MAP02 PROOF.

Optionally, pass the owner-private v3 shortlist created by
Draft #445 using `--reviewed-candidates /private/vh-map02-reviewed-candidates.json`.
The report must be an owner-only regular file outside Git and its
`source_plan_sha256` must match the exact canonical capture-plan bytes being
revalidated in this run. The renderer then shows only groups marked
`requires_game_state_witness`; stale/malformed reports and reports with no
eligible groups fail closed. The source audit still checks all supplied frames
before filtering. The sheet remains an unverified human-review aid, not proof.

**The output contains actual screenshot copies and private frame
coordinates.** Never upload the output PNG to GitHub, a GitHub issue,
Actions artifact or a public message. It is saved only to a new
absolute PNG path in an existing non-symlink directory outside Git,
with exclusive create and owner-only 0600 permissions. Existing files, directly symlinked output directories, symlink targets,
and Git directories are rejected. Standard macOS system ancestry such as
/var resolving to /private/var is accepted, but the full canonicalized
ancestry is also checked for Git checkouts, so that alias cannot be used
to write private screenshots into a repository. Public CI tests
only invented 2×1 PNGs and does not publish even those image fixtures.

Use the private sheet for a human to label intervals as menus, dialogue,
travel, tactical board or uncertain, then decide which genuine gameplay
state observations would be useful. **Do not publish a precise MAP02
start frame from contact-sheet appearance alone.**

## Explicit evidence limits

This tool does NOT authenticate separate genuine PS1 emulator processes,
input-to-displayed-frame offset, the original game disc/BIOS, a MAP02
scene, gameplay state, original PS1 GPU/VRAM, or physical Nintendo
Switch execution. Differences may come from frontend rendering,
video filters, UI or animation. Matching PNGs might be repeated
wrong-frame screenshots. All report provenance booleans remain false.

Keep this and all other PRs Draft; no merges or changes to main are
authorized by synthetic results.
