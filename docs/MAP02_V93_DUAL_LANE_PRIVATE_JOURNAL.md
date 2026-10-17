# MAP02 v93 — independent native renderer/detail and GPU aggregate journals

v92 on the pinned PCSX ReARMed software renderer successfully
reproduced real queue pressure, one insufficient-space GPU DMA
fallback, exact 131,072 native 16-bit writes, zero undrained
queue words and **4,055 / 4,096** private event slots in both
GCC and Clang. Continuing to append stage aggregates into
that single buffer would threaten lossless evidence retention.

## Physical lane isolation, not lossy summarization

v93 changes the *diagnostic observer only*, not the emulator's GP0
renderer or Nintendo Switch HD path. The old bounded v80 event
array is explicitly retained as a **4,096-record detailed lane**
for actual VBlank, GP1 MMIO, DMA2 submission, Unai command dispatch,
24-point VRAM sampler and pixel-store counter records (kinds 1–7).

A second **256-record GPU aggregate lane** is created for independent
stage totals from v86–v93 (kinds 8–78). These are already bounded
aggregates from authentic software paths, including native
asynchronous DMA worker counters, synchronous fallbacks, copy masks
and worker ordering; they are not raw pixels or retail game data.
Both arrays have their own strict capacity checks; neither can
overwrite events from the other. Exceeding either limit increments
the existing fail-closed `dropped` counter and prevents private
publication. Invalid kinds and a 32-bit sequence overflow are
likewise refused.

Every call to `vh80_record` retains the original increasing
**global 32-bit event sequence**. When the private journal is
exported *after original `GPUfreeze` and GPU worker shutdown*,
`vh80_events` merges both monotone physical lanes in a linear
pass into a bounded 4,352-record read-only snapshot. The original
JSONL schema `kind/seq/value/cycle/frame` and global event
ordering remain unchanged. The strict v82 verifier still rejects
nonconsecutive sequences, fabricated CPU/frame fields, missing
four emulator VBlank transitions and bad GP1 evidence.

## Bounded native capacity proof

After all original four emulator VBlank callbacks and 2,380
synthetic MIPS oracle VRAM readbacks, and after all previous
v86–v92 host-only GPU checks have passed, the test sends just
12 extra untextured 16×16 host-generated GP0 sprites into the
**real pinned Unai renderer**. Those native handler events
increase the combined private journal above the former global
4,096-record ceiling, without overflowing either physical lane.

Only after successful GPU synchronization, the smoke fixture
appends three more aggregate-only counters: physical detailed
records, physical aggregate records (including these counters),
and merged total records. It refuses if the total did not exceed
4,096, either lane is full beyond its capacity, drops occurred,
the merged counter sum differs, or a sequence is not the exact
consecutive integer expected. The independent Python verifier
recounts event kinds and proves all three published counts agree
with *actual serialized private JSONL*, still verifying every
v80–v92 predecessor observation.

Extra isolated GCC/Clang native C tests populate **all 4,096
detailed and all 256 aggregate slots**, confirm correct merge
ordering through all 4,352 events, export all records into a
bounded buffer, and independently prove an attempted excess
in either lane is refused rather than silently discarded.
The private file still uses mode 0600, exclusive hard-link
publication, fsync and byte-for-byte reopen verification,
with duplicate export refusal. GitHub Actions uploads only
aggregate PASS summaries, never raw GPU event traces or
copyrighted game assets.

### Scope boundaries

The extra sprites are **host-submitted diagnostic controls**, not
authentic retail Vandal Hearts MAP02, and VBlank edges observed
inside PCSX are not physical PS1 timing measurements. This
diagnostic capacity improvement does **not** approve enabling
HD replacement, claim accuracy of the real game, or affect
Nintendo Switch production rendering. The PR remains Draft,
stacked on v92, and leaves `main` unchanged.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
