# MAP02 v95 — repeated verified snapshot replay and byte-exact prefixes

The pinned native PCSX ReARMed v94 software GPU previously passed full
GCC and Clang validation for cached dual-lane event snapshots, including
128 stable O(1) reads, explicit native source-to-view integrity checks
and rejection of deliberately modified cached entries.

v95 exercises **eight consecutive event append / stale-view rejection /
single rebuild / source integrity check / twice serialised private JSONL**
cycles. This covers repeated reuse of the cache and private formatter
across successive updates without weakening v80–v94 provenance.

## Native test scope

The host executes all earlier synthetic MIPS oracle work (four actual
emulator VBlank callbacks, 2,380 VRAM readback checks), pinned Unai
rendering and v86–v94 asynchronous GPU worker diagnostics first. The
worker is drained through original `GPUfreeze`; this new probe
does **not** run against concurrent writers.

The **original** C `vh80_record` produces eight successive bounded
aggregate records with unique ordered kinds and consecutive values
1–8. After each successful append, `vh94_snapshot_check` must reject
the stale view. Only one new full dual-lane merge is accepted before
the following cache read. The merged output pointer remains stable
because the underlying fixed 4,352-record array is unchanged.

Two static **in-memory-only** JSONL buffers (each limited to 524,288
bytes, matching v82 private export) are used. For each round:

1. Format the current complete journal using the **real** native v81
   serializer, which already invokes the v94 source-to-view integrity
   check before returning.
2. Require the newly formatted bytes to begin with **every byte of the
   previously verified journal**. This rejects unexpected mutation,
   truncation, or reordering of earlier records.
3. Serialize again into the other buffer and require the **entire
   output to be byte-identical**. This rejects nondeterministic
   serialization of a stable snapshot.

Eight rounds yield eight successful prefix checks, 16 independent
in-memory serializations, exactly eight rebuilds, eight stale-view
refusals and eight stable cached pointer reads. Five additional
aggregate proof records are appended afterward. The actual v82
private file is still published **once only**, using exclusive
non-overwriting mode 0600, fsync, byte-exact reopened readback and
private SHA-256 validation.

## Independent regression and security

The new Python verifier requires the eight unique event kinds
`append_round_1` through `append_round_8`, their exact ordered
values, and the five final aggregate metrics. It rejects unexpected
interleaved/duplicate/missing events, cycle or frame forgery and
missing predecessor v94 evidence. The v94 checkpoint verifier now
accepts a later v95 suffix while continuing to require its own three
metrics immediately after the v93 checkpoint.

The isolated native GCC and Clang C tests independently perform all
eight original C serializer cycles, assert that the full prior JSONL
is a prefix of the next export, and prove that tampering with a
cached entry causes refusal. Pinned PCSX native CI runs the complete
v80–v95 verification chain, and publishes only non-sensitive PASS
summaries, **not** raw event streams, pixel samples or game assets.

No part of this demonstrates authentic retail Vandal Hearts MAP02,
physical PlayStation GPU timing, all possible concurrent memory
interleavings or Switch HD renderer correctness.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

Draft PR only, stacked on v94; `main` is not modified.
