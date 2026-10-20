# MAP02 — integration order for the 26 Draft PRs (planning only)

This document describes a **reviewable integration order**, not permission to
merge. The current Nintendo Switch MAP02 asset-free 4v4 prototype and its two
authentic NeXium cold-boot replays are established independently of the retail
PS1 game. No physical Nintendo Switch test or PS1 asset verification is claimed.

## Frozen input and evidence

- Pin exact upstream PR SHAs from `data/map02_full_stack_snapshot.json`.
  PR #352 is the current `HEAD` so that new safety-check commits do not
  invalidate their own manifest. Any upstream head drift must **fail closed**.
- Require `tools/audit_map02_full_stack.py` and
  `.github/workflows/map02-full-stack-integration.yml` to pass on the exact
  candidate SHA. Verify all 26 PR heads, 25 edges, root `main` ancestry,
  four protected original fixture files, no added binary/retail images, and
  zero Git branch or worktree merges.
- In the **same integration CI**, inspect authenticated GitHub Actions
  `pull_request` workflow history for the **exact 25 pinned upstream
  commit SHAs**. Require at least one completed-successful run on each SHA;
  an observed completed failure or timeout blocks the audit. Exclude #352's
  current HEAD from this upstream history requirement to avoid a circular
  dependency on the still-running CI; its own native/NeXium jobs form a
  separate required check. Record each evidence run URL in the report.
  API errors, missing runs, or incomplete result pages block integration.
- In the **same CI run**, query GitHub's authenticated read-only pull-request
  API for all 26 PRs. Require every PR to remain open, unmerged and Draft,
  with pinned head/base branch names, head SHAs, source repository and base
  SHAs. For #265, its base SHA is the historical merge-base of #262/#265,
  not the later #262 head. Any network failure or metadata mismatch blocks
  the audit; stored history alone is insufficient evidence of PR state.
- Require `.github/workflows/map02-cold-restart.yml` on the exact candidate:
  adversarial Python tests; source-pinned devkitPro/libnx NRO; two genuinely
  terminated NeXium processes and 24 PNGs; exact board/HUD comparisons; and
  the separate saved-artifact `--audit-only` pass.

## Proposed *upstream-to-downstream* review batches

Each item is a PR number; every dependency must be individually reviewed.
The numbered order below is identical to the committed 26-PR manifest, not an
instruction to merge them as a batch.

1. **Baseline tactical encounter and data:** #241 → #243 → #247 → #250 →
   #251 → #252.
2. **Rosters and optional 4v4 battle:** #253 → #256 → #259 → #262 → #265 →
   #270 → #273.
3. **Second arena and actor abilities:** #281 → #284 → #289 → #295.
4. **Source-preserving integration and artifact identity:** #302 → #305 →
   #314 → #318.
5. **Complete behavioral and regression evidence:** #322 → #325 → #333 →
   #347 → #352.

The full ordered list has **26 PRs**. The final #352 branch currently sits
above all of them but is a Draft stacked on #347, not directly on `main`.
All previously approved fixtures and the existing legacy arena must survive.

## Critical historical divergence: #262 → #265

These are **not** a linear ancestor pair. #265 branched before two historical
#262 commits and independently reproduced their script/oracle fixes. A normal
GitHub green mergeable flag or a conflict-free `git merge-tree` is
insufficient: a conflict-free merge could silently reintroduce older-only
content into #265.

The full-stack audit now verifies both:

- The existing 11-PR audit confirms the common-source content and that
  `git merge-tree --write-tree <#262 SHA> <#265 SHA>` has no conflicts.
- The **resulting simulated tree SHA is required to equal the exact tree SHA
  of #265 itself**. If they differ, halt and reconcile/review the differences
  in a separate throwaway branch; do not rewrite reviewed branches, force push,
  or claim that the two history versions are equivalent.

Even identical trees do **not** mean the Git histories are identical; the
historical divergence remains explicitly recorded.

## Full-chain virtual integration rehearsal (object-only)

Before any real merge, `tools/rehearse_map02_full_stack.py` simulates the
complete sequence of **26 individual merges** starting from the pinned
`origin/main` commit, in precisely the manifest order. Each intermediate
`git merge-tree --write-tree` must have no conflicts **and** produce the
exact same Git tree SHA as the reviewed downstream PR at that step. This
prevents silent reintroduction of older-only files even if Git sees no conflict.

The tool then creates an **unreferenced temporary Git commit object** using
`git commit-tree` to model the parents of the following merge. This writes
objects only to the ephemeral CI runner's local Git object database; **no
branch, tag, worktree, index, remote repository, or PR is changed**. The final
simulated tree must equal the checked-out PR #352 tree, byte for byte.

The required CI produces `virtual-merge.json` listing all 26 source commits,
their expected/rehearsed tree hashes, and ephemeral commit hashes. The report
also records **every intermediate changed path** (added, modified, deleted or
type-changed) from each simulated merge, not just the final merged tree.
Added/modified/type-changed retail ROM, game-image, archive, audio or screenshot
paths are rejected **even if a later PR deletes them**. Thus a final-tree-only
scan cannot hide transient unwanted content. Eight synthetic tests cover
linear/copied-history replay, detached CI checkouts, conflicts, revived files,
incorrect final heads, temporary retail assets, and per-step deletions.
A successful rehearsal is an integration *safety proof for the pinned
snapshot*, not a claim that any branch was merged, or that its tests passed
after a real merge.

## Human-gated integration procedure

For each PR, beginning at #241:

- Confirm its head SHA, actual base, Draft status, diff, review decisions,
  required CI and candidate metadata before changing any Git ref.
- Prepare and inspect a *disposable* branch based on the current protected
  integration target, simulate the intended merge, review exact tree/path
  changes, then run native tests and the relevant NeXium scenarios.
- At #262/#265, require the reconciliation-tree equality above; stop for
  explicit review if any tree content differs, even when Git reports no
  textual conflict. Do not silently skip old commits.
- After any real merge decision, repeat ancestry/source-identity checks and
  take a **new** baseline screenshot/artifact. The previous NRO and screenshot
  receipts belong to their original immutable source commits, not to a newly
  rewritten branch.
- Never automatically move `main`, publish copyrighted game data, or
  convert a Draft to ready-for-review from this audit workflow.

## Stop conditions and remaining gates

**Stop** if any pinned upstream PR lacks completed-successful Actions evidence,
if a known failed/timed-out workflow applies to its exact SHA, or if the
workflow history cannot be verified completely.

**Stop** if a PR is closed, marked ready, retargeted, moved to another
repository or updated to an unpinned head/base SHA; if GitHub metadata cannot
be retrieved; if upstream refs move, `main` advances unexpectedly, any
reconciliation changes the #265 tree, protected fixtures change, source
receipts disagree, native tests fail, or genuine NeXium PNG comparison fails.
The existing artifact-free playable demo is **not** evidence for retail PS1
compatibility. Hardware loading on a physical Switch and licensing/source
rights remain independent gates before any public distribution.

No actual merge, rebase, cherry-pick, branch rewrite or release is performed
by either the full-stack audit or this plan.
