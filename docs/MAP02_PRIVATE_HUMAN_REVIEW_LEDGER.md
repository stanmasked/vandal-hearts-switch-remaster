# MAP02 — owner-local manual scene review ledger

This Draft extends [PR #435](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/435), which produces a private PNG comparison sheet from two purported BK2 replays. This step helps a human annotate that sheet. It is NOT automated MAP02 recognition.

Both modes run the full, earlier, owner-local BK2 → capture-plan → Lua logs → PNG CRC/IDAT/SHA → decoded-RGB comparison audit again, before reading or writing labels. Never copy private assets into GitHub.

## Prepare

On the owner's local machine, with movie, plans, logs and PNGs outside Git:

    umask 077
    python3 -m tools.map02_private_human_review_ledger prepare \
      /private/vandalhearts.bk2 /private/vh-map02-review-plan.txt \
      /private/run1-console.log /private/run1-png \
      /private/run2-console.log /private/run2-png \
      --private-annotations /private/vh-map02-manual-review.csv

The new owner-only CSV has exactly these columns:

    review_group,frame_role,run_1_label,run_2_label

Each role is before, middle or after; both run-label cells begin as
unreviewed. Inspect the local PNG contact sheet and edit only the label
cells. Choose exactly one of these for each:

- unreviewed — not inspected
- uncertain — visual category ambiguous
- menu — title or menu
- dialogue — conversation or text
- travel — navigation/world
- tactical_board — observer thinks a tactics grid is visible
- transition — fade, loading or visual cut
- other — no category fits

There is deliberately NO MAP02 class. Do not insert commands, formulas,
private frame numbers, comments or free-text notes into the CSV.

## Audit

Run the same command with mode audit and the additional option:

    --private-report-output /private/vh-map02-observations-report.json

The verifier requires every group and role from the canonical private
source plan, forbids extra/missing/duplicate positions or unexpected
labels, and counts uncertain, agreement, disagreement and manually
matched tactical_board labels. Neither disagreement nor uncertainty is
hidden; partial reviews are allowed and counted as pending.

The resulting new 0600 JSON file contains only aggregate counts and
conservative flags, not frame coordinates, private filenames or pixels.
Output overwrites, direct symlink targets/direct output-folder symlinks,
and output inside Git checkouts are refused; standard macOS /var ->
/private/var canonical ancestry works, but canonical and lexical Git
checkout ancestry are both blocked.

Important limits: two equal manual labels are not two independently
authenticated human reviewers; two image directories are not two proven
PS1 emulator processes. Human tactical_board classification is not a
verified MAP02 start. Actual original game disc/BIOS, original gameplay,
input-to-screen frame alignment, source GPU/VRAM and physical Nintendo
Switch remain unauthenticated. All such fields are FALSE.

GitHub Actions tests only invented CSVs and fabricated capture metadata.
Never upload the original BK2, game/BIOS, private PNGs, Lua logs, manual
CSV or report to the public repository. Keep all PRs Draft; main is
unchanged.
