# MAP02 v112 — consecutive observed Unai writes with unchanged sampled VRAM

Stacked on v111 [Draft PR #102](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/102).

## Motivation

v111 identified an important false inference: an instrumented Unai C++
16-bit pixel-store assignment may have occurred even when all 24 selected
VRAM readback positions had identical before/after values. Separately
summarized VBlank buckets do not preserve *consecutive qualifying Unai
callback* order. v112 makes that relationship explicit, including what
happens when observed host event order crosses emulator VBlank callbacks.

## What v112 proves in the synthetic fixture

The independent read-only analyzer accepts the same validated **private**
pinned PCSX ReARMed native JSONL stream. A qualifying Unai handler is a
strict adjacent 4-event group with:
- a GP0 handler event;
- exactly zero changed readback sample locations;
- a positive instrumented native Unai store-attempt count;
- a same-value native assignment count no greater than total assignments.

Runs are formed from consecutive *observed Unai callback groups*, ignoring
the presence of GP1 inputs or VBlank callback records in between. An
intervening nonqualifying Unai handler terminates a run. This does **not**
assert that all machine instructions or GPU work between the two callbacks
were observed.

For each run, v112 audits:
- qualifying handler count, run count, multi-handler runs and longest run;
- per-VBlank interval counts and native 16-bit assignment totals by coarse
  GP0 command family;
- adjacent qualifying pairs within one interval versus pairs spanning
  one or more VBlank callbacks;
- exact number of observed VBlank callback *edges*, not elapsed time,
  crossed by consecutive qualifying observed Unai handlers;
- class-to-class transitions of those qualifying adjacent handlers;
- four cumulative pre-VBlank checkpoints reconciled to v111's native
  sample/store counts and v110's all-store upper bound.

Native GCC and Clang tests include a valid three-handler chain spanning
VBlank, an otherwise empty interval with two VBlank callbacks, a
nonqualifying Unai callback that breaks a run, and a pair of fixtures with
identical v109/v110 aggregate results but distinct v112 outcomes. Invalid
sample counts, native store counters, timestamps and split 4-event groups
are refused. Empty-run traces are accepted when valid.

The full pinned PCSX synthetic-host emulator CI runs the audit against
the **original private** V104_RENDERER_EVENTS.jsonl and emits only
`proof/public/v112-unchanged-sample-runs.json` with coarse aggregate
counts. Neither raw GP0 headers, VRAM values, private event records nor
game data are published.

## Strict evidence limits

Zero changed *sampled* locations never establish whole-VRAM invariance.
A crossing between two observed Unai callbacks around a VBlank marker
does **not** prove the intervening VRAM contents persisted to the next
hardware frame. No emulator GPU CPU-cycle completion time is inferred,
and instrumented C++ stores do not cover all GPU/assembly/DMA paths.
Nothing in this phase verifies original retail MAP02, physical PS1 output,
or Nintendo Switch HD rendering equivalence.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
`main` unchanged.
