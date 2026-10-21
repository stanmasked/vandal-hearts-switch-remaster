# MAP02 — private review shortlist from human categories and two BK2 PNG capture sets

This optional tool is a follow-up to [Draft PR #438](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/438) and its owner-private manual annotation CSV, prepared after the visual contact sheet of [Draft #435](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/435).

**Goal:** Produce an owner-only, conservatively worded shortlist of screenshot groups that deserve **actual PS1 game-state investigation**. It does NOT authenticate MAP02, actual emulator playback, controller-to-display timing, source GPU/VRAM or original disc/BIOS.

## Private owner-local use

First capture two separate read-only BizHawk Octoshock playbacks with the **owner-held game and BIOS** and the canonical plan generated from the original owner-local `vandalhearts.bk2`. Store the plan, source BK2, two Lua marker logs, and two screenshot directories outside any public Git repository. Generate the comparison PNG contact sheet (Draft #435), and fill the private `review_group,frame_role,run_1_label,run_2_label` CSV (Draft #438).

Then run, entirely on the owner's computer:

    umask 077
    python3 -m tools.map02_private_reviewed_scene_candidates \
      /private/vandalhearts.bk2 \
      /private/vh-map02-review-plan.txt \
      /private/run1-console.log /private/run1-png \
      /private/run2-console.log /private/run2-png \
      --private-annotations /private/vh-map02-manual-review.csv \
      --private-report-output /private/vh-map02-reviewed-candidates.json

Use the same optional neutral-window bounds that produced the source capture plan.

After the shortlist is created, you can optionally render a second, smaller
private contact sheet containing only groups marked
`requires_game_state_witness`. The contact-sheet tool revalidates both full
capture chains and checks the report's exact `source_plan_sha256` before
filtering; a report for another plan, an owner-readable-by-others file, or an
empty candidate set is rejected. For example, repeat the same six source
arguments and use:

    --reviewed-candidates /private/vh-map02-reviewed-candidates.json \
    --owner-private-output /private/vh-map02-shortlisted-contact-sheet.png

This is a convenience for prioritizing review, **not** an independent
game-state witness or MAP02 authentication. Keep both files local.

The script first independently verifies **both complete source BK2→canonical capture plan→Lua log→PNG envelope/CRC/IDAT→decoded RGB capture chains**, just as Draft #429 does. Then it checks every human category for every canonical group/role (Draft #438), and only afterwards considers a group a possible *manual-screen-review* transition.

One group gets the state `requires_game_state_witness` **only when every corresponding screenshot's decoded RGB matches across the two supplied capture bundles**, both label columns agree, the first `before` image is manually marked non-tactical, and both later `middle` and `after` images are manually marked `tactical_board`. **Additionally, the decoded RGB within the first run must actually differ from `before` to both `middle` and `after`, with unchanged screenshot dimensions across the group**. Matching manual labels alone are insufficient: when the supplied snapshots do not show this visual change, the result is `no_observed_intra_group_pixel_change` and the group cannot be shortlisted. The group is **not** marked MAP02 and is not claimed to be a tactical battle; it merits a separate authenticated PS1 game-state/VRAM observation.

All other groups remain in one of five explicit states: `requires_pixel_replay` (cross-bundle image mismatch), `awaiting_manual_classification` (uncertain/unreviewed), `human_labels_disagree` (categories conflict), `no_observed_intra_group_pixel_change` (manual pattern but no matching observed pixel transition), and `not_candidate_in_selected_frames` (no before→two-board pattern). This ordering gives discrepancies higher priority than apparently agreeing labels. A repeated menu or wrong-scene image may still be labelled tactical, so even a group passing the pattern can be false.

The resulting owner-only JSON uses schema `vh.map02.private-reviewed-scene-candidates.v3`, with counts, group numbers and conservative classifications. It includes `source_plan_sha256`, the SHA-256 of the exact canonical capture-plan bytes, so a stale shortlist cannot silently filter a different plan. It contains **no actual BK2 frame/input indices, paths, screenshots or image hashes**, and is written to a new, exclusive `0600` file outside Git. Never upload this private report, CSV, original movie, PS1 disc/BIOS or screenshots to GitHub or public CI.

## Boundaries of evidence

Two file directories do **not** authenticate two distinct emulator runs. Two matching category labels do **not** establish two independent human observers. Decoded RGB matches do not establish original PS1 gameplay, frame synchronization, scene identity or source/native GPU parity. The known first Start input at movie index 1661 is **not** a confirmed MAP02 start. All provenance flags remain `false`.

Public CI uses only invented two-pixel RGB screenshots, fake movie/log paths, mock chain audits and made-up human labels. It cannot validate original MAP02 gameplay. Parent PR #438, other Drafts and `main` remain unmerged and unchanged.
