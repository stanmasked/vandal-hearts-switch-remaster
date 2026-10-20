# MAP02 — stacked integration without merging into main

This is a **read-only preparation stage**, following 11 independently authored Draft PRs that form the optional Nintendo Switch MAP02 tactical prototype. It does not itself merge, rebase, rewrite, push or publish any gameplay branch, and contains no licensed PS1 disc resources.

## Pinned and tested chain

`data/map02_pr_stack_snapshot.json` pins exact commit SHAs and base refs for Draft PRs:

`#253 → #256 → #259 → #262 → #265 → #270 → #273 → #281 → #284 → #289 → #295`

All were independently verified as open, mergeable and still Draft when the snapshot was recorded. The head of this audit branch must be a descendant of the final tested #295 commit; a shifted upstream PR head fails the audit instead of being silently approved.

## What the dry-run audit actually checks

`tools/audit_map02_stack.py` fetches only **read-only** `refs/pull/<PR>/head` references into local temporary remote-tracking names. All historical edges must be descendants of the preceding PR, with exactly one deliberately reviewed exception:

- **PR #262 → #265:** #265 is 2 Git commits behind #262, because earlier screenshot-oracle fixes were committed independently in the follow-up branch. The four overlapping files (`source/main.c`, original 4v4 NeXium script and oracle, and its workflow) have matching Git blob hashes. A `git merge-tree --write-tree` simulation must successfully produce an unconflicted tree object. This does **not** rewrite either branch or actually merge it. Future reviewers should still reconcile ancestry before integration.
- No other non-linear history is allowed. Every other edge must have the full earlier branch as an ancestor.

Four independently authored **original fixture** files are pinned against the already tested PR #262 and must match byte-for-byte at the latest audit branch:

`source/map02_battle_fixture.h`, `source/map02_roster8_smoke_data.h`, `source/map02_roster8.h`, and `data/map02_roster8_4v4.json`.

The latest code must still contain the ten required files for battle engine, roster selection, second arena, archer, medic, guard and visible guard HUD, and `source/main.c` must reference each tactical header. Newly added or modified ROM/disc/container/image/audio binary files relative to the first staged PR are rejected. This guard covers the **PR sequence**, not arbitrary historical files already present in the repository.

The audit creates `build/map02-stack-preflight/report.json` and publishes it as a CI artifact. Any failed invariant stops the job without altering refs or working files.

## Extra integration test

`tests/test_map02_stacked_integration.c` exercises six scene/roster combinations and, on the same independent second-arena encounter, a rejected out-of-range bow shot, actual deterministic enemy turns, a third-ally shield mitigating one attack, subsequent medic healing and reset, plus original arena attack/padding integrity. Both GCC and Clang run optimized and UBSan variants.

`tests/test_map02_stack_audit.py` verifies snapshot constraints, duplicate and unsafe-path rejection, detection of possibly proprietary game files, a successful simulated merge of independently committed identical changes, refusal of a true merge conflict and zero mutation of the working tree.

These host tests complement, **but do not replace**, the previous authentic NeXium screenshots from PRs #262 through #295. A successful dry-run report is not evidence that GitHub's default branch has received a game, that the retail PlayStation MAP02 has been reconstructed, or that the game was executed on physical Nintendo Switch hardware.

## Human-reviewed integration steps (not automatically executed)

1. Review the machine-readable dry-run report and each staged PR's existing CI record.
2. Reconcile the #262/#265 copied-history edge using a deliberate history operation; verify the four shared blobs and re-run relevant NeXium jobs if this changes a branch head.
3. Integrate **upstream to downstream**, one audited PR at a time, retaining both original approved maps, privacy controls and previously verified controller routes.
4. Before any default-branch merge, independently verify the final combined branch with native tests and real emulator/hardware testing and review licensing/privacy.

All PRs remain Draft and no automatic merge, release or upload of copyrighted retail images is authorized by this stage.
