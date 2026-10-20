# Stage370 — three authentic, distinct NeXium audio-exit observations

## Scope

Stage370 compares **two independently audited reports of original
captures**, rather than pretending the old `0xEA01` run contains
new Stage368 descriptor telemetry.

- Stage365 had already re-downloaded and verified an original NeXium
  timeout (run [39325440778](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39325440778))
  and a **different** successful run
  ([39340120727](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39340120727)).
  Its original archival proof comes from
  [Stage365 run #39351366143](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39351366143),
  artifact `12233871696`.
- Stage369 independently re-downloaded the newer, third original
  [NeXium run #39388027581](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39388027581),
  verifying the original Stage351, Stage357, Stage368 CSV bytes, the
  same-run NRO SHA-256 and authentic GitHub job results. Its independent
  [Stage369 run #39390450645](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39390450645)
  saved artifact `12250010822`.

| | Old timeout | Earlier success | Newer success |
| --- | --- | --- | --- |
| Original run | 39325440778 | 39340120727 | 39388027581 |
| Existing bounded-wait `Result` | 59905 (`0xEA01`) | 0 | 0 |
| Stage368 released descriptor count | **unknown** | **unknown** | **1** |
| Stage368 pointer matches submitted | **unknown** | **unknown** | **yes** |
| Old pre-submit Stage360 queue sample | **not present** | recorded, but not an exit queue reading | not used for causal pairing |
| Direct queue at shutdown | **unknown** | **unknown** | **unknown** |

Stage365 additionally confirmed original software lease totals:
`1414/1413/1` (acquired/released/abandoned) for the timeout and
`1438/1438/0` for its separate earlier success.

## Independent Stage370 action

`.github/workflows/stage370-three-original-wait-cohorts.yml`
downloads **only** the original Stage365 and Stage369 archived reports,
reads both historical GitHub artifact metadata objects, checks their
precise original IDs, digest strings and originating workflow run IDs,
and invokes `tools/audit_stage370_distinct_original_wait_cohorts.py`.

The final report lists three different original runs. It checks SHA-256
source-proof presence, refuses the old CSV being substituted into the
new descriptor-source receipts, and preserves old descriptor count,
pointer match and probe status as JSON `null`.

The eight synthetic mutation tests reject wrong run IDs, erased
abandoned sessions, fabricated queue readings, phony `Result=0`,
altered archives, imaginary pointer matches, forged hardware or
causal claims.

**Important limitation:** Stage370 cross-checks *previously audited*
original-source verdicts. It does not itself reopen the original
Stage365 or Stage369 raw NeXium ZIPs again; those replays have their
own independently passing workflows and original checksums. It is
not a controlled experiment comparing a changed implementation, does
not identify the kernel event-wait subcall responsible for `0xEA01`,
and proves no acoustic output on physical Nintendo Switch.

The new Stage370 workflow must pass on its own before the three-way
report is declared independently verified. Nothing here modifies
libnx `audoutWaitPlayFinish`, the 12-ms bound, audio buffers, PCM
transport, or game render/input logic.
