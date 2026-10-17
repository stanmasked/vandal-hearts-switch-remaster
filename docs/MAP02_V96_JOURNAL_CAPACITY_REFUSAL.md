# MAP02 v96 — native dual-lane capacity boundaries and fail-closed publication

This Draft stage builds on the green pinned PCSX ReARMed v95 snapshot
and event exporter. It retains the original synthetic four-emulator-VBlank
MIPS oracle (2,380 VRAM readback samples) and all GPU worker, GP0
copy/masking, queue-pressure and cached-journal regressions.

## What is exercised

The v93 observer has two fixed non-overwriting physical lanes:

- **4,096** original detailed renderer/MIPS/VBlank observations
  (event kinds 1–7)
- **256** GPU and test-control aggregates (kinds 8+)

Every successful append receives a new globally ordered event number.
The v94 cache remains valid between writes and is rebuilt just once
after a successful append. The v81 serializer independently verifies
all five event fields against the original two source lanes before
the v82 exclusive mode-0600 publication is permitted.

The pinned full-emulator v96 host smoke runs **only after** all
v80–v95 successful checks and original `GPUfreeze` barrier. It
measures remaining free slots separately from the actual detailed and
aggregate lane counters, confirms the near-full detailed lane is
not over capacity, then appends three aggregate measurements. A
stale cache must be refused. One rebuild and exactly two independent
in-memory native private JSONL serializations must preserve **every
previously verified byte** of the v95 snapshot, match each other
byte-for-byte and retain a contiguous global sequence. Independent
Python audit derives remaining capacities from the actual serialized
event types rather than trusting the counters themselves.

## Exact-capacity C ABI and deliberate overflow

**Crucial separation:** deliberately overflowing the live emulator
private journal would correctly mark it damaged and refuse publication.
Therefore deliberate overflow is performed **only in isolated native
GCC/Clang tests** calling the real C observer and serializer functions:

1. Fill all 4,096 detailed records, leaving the aggregate lane
   available; attempt a 4,097th detailed record.
2. Fill all 256 aggregate records while the detailed lane remains
   available; attempt a 257th aggregate record.
3. Approach both limits simultaneously (4,088 detailed plus 248
   aggregate), alternately append 8 detailed and 8 aggregate records,
   and serialize/check the **entire previous JSONL as an identical
   prefix** after each pair. This fills all 4,352 records. Then attempt
   an extra append into **each** fully occupied lane.
4. Attempt an invalid event kind to verify validation failures are
   equally fail closed.

For every denied append the tests require that the *old* global
sequence and the original bytes of the cached snapshot are not
modified, counts do not increase, and an unnecessary merge does not
take place. The failure increments `dropped`, which causes
`vh94_snapshot_check` and real `vh81_format_jsonl` to refuse the
private file **even if the pre-failure array bytes remain unchanged**.
There is no silent recovery without a legitimate observer reset and
no partial private file published.

All native tests compile with warnings-as-errors under both GCC and
Clang; the full pinned PCSX runs the v96 host smoke under both toolchains
after the historical MIPS and GPU paths, with only bounded aggregate
proofs published by CI. Private raw event JSONL, game assets and VRAM
contents are never uploaded as CI artifacts.

## Limitations

The near-limit full-emulator work and isolated full-capacity tests use
**synthetic host controls**, not authentic retail Vandal Hearts MAP02
or physical PlayStation hardware. A bounded refusal test is not
a proof of correctness for concurrent unsynchronized GPU writers or
a replacement for hardware PS1 comparison. The Switch HD path is not
enabled and `main` is unchanged.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
