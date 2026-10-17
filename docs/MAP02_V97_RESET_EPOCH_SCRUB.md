# MAP02 v97 — reset epochs, erased diagnostic memory and clean private JSONL reuse

v96 green pinned PCSX ReARMed observed all four emulator VBlank callbacks
and 2,380 original synthetic-MIPS VRAM samples; dual-lane GP0 diagnostics
proved 4,125 ordered events, bounded zero-loss export, and isolated
fail-closed capacity overrun. v97 hardens **the next observer lifetime**.

## Reset generations and resident data erasure

`vh80_reset()` now explicitly scrubs all three fixed resident event arrays:

- 4,096 detailed renderer events,
- 256 GPU stage aggregate events,
- and the 4,352-record globally merged snapshot cache.

Erasure uses volatile byte stores so the C compiler cannot simply
eliminate writes to logically unused previous records. The single
reset operation also clears counts, stale snapshot validity and
the pre-existing native store/sampler controls. A monotonically increasing
32-bit observer epoch distinguishes consecutive lifetime generations;
epoch exhaustion is **fail closed** rather than silently wrapping to an
older lifetime identifier. The `vh97_buffers_erased()` diagnostic
checks all three physical arrays, independently of logical event counts.
As with previous `GPUfreeze` checks, reset must be called **only after
all asynchronous native GPU writers have stopped**.

Returning a C pointer to the internal array cannot retroactively
invalidate copies already made by another process or caller. The
scope of this change is clearing resident observer storage under
an exclusive/quiescent owner, not guaranteeing erasure of unrelated
memory, disks, or previously published logs.

## Never leak bytes from a previous longer JSONL serialization

The real v81 JSONL formatter now clears the **entire output capacity**
provided by its caller, before performing any validation or
serialization. This applies to success, invalid generation and
fail-closed overflow attempts. A re-used 524,288-byte buffer therefore
cannot retain a tail of prior longer private JSONL content beyond the
new valid-length result. The existing mode-0600 exclusive v82 publisher
still writes only the exact returned length, performs fsync and
readback verification and rejects duplicate publication.

The full pinned-emulator v97 host smoke preserves all preceding
four-emulator-VBlank/MIPS and v86–v96 GPU tests. It intentionally
**does not reset the live original journal** because doing so would
erase the observation to be audited. Instead it records the current
observer epoch; fills two separate private process-memory JSONL
buffers with different nonzero sentinels; invokes the original C
formatter twice; verifies both valid prefixes are byte-identical,
all bytes **after** the valid length are zero, and then appends three
bounded private aggregate metrics. Their distinct checkpoint is
revalidated by v97's strict Python verifier, without exposing any
raw events as public CI artifacts.

## Destructive independent native C tests

GCC and Clang separately compile and run the real v80/v81 C
diagnostics and deliberately call `vh80_reset()` between generations.
Tests verify:

1. Every old detailed, aggregate and merged event array byte has been
   erased and the prior cached pointer now reads zero; a stale
   snapshot is refused until a fresh append/merge.
2. The epoch advances and new events start again at sequence 1,
   retaining only new values and the required emulator VBlank framing.
3. A reused buffer containing a previously *longer* JSONL export has
   no old trailing data after a subsequent shorter export.
4. Overflow or invalid-kind refusal wipes the supplied destination
   even on failure; reset is the only legitimate way to start a new
   uncontaminated observer generation.
5. Several consecutive resets produce different valid event streams
   and cannot reuse older event bytes in the new generation.

Independent Python audit refuses missing/duplicate/reordered epoch,
buffer-scrub and replay values, forged CPU or emulated frame ownership
and missing v80–v96 provenance. The pinned full-emulator GCC+Clang
matrix retains the earlier protected private-file checks.

**Scope:** synthetic host-submitted GPU controls after a pinned
software-emulator oracle. This does not establish original retail
Vandal Hearts MAP02 correctness, physical PS1 timing, concurrent
uncoordinated memory-writer safety, or production Switch HD accuracy.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

Draft stacked on v96; `main` untouched.
