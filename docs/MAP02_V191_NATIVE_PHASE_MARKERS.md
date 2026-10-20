# MAP02 v191 — link native Unai pixel phase passes to RAM and real VBlank

Prerequisite: MAP02 v190 Draft PR #222, which SHA-256 and inode-checks each of the ten private synthetic PS1 process logs around the 159 in-memory fault transcript replays. v190 is not considered proven until its native GCC+Clang runs and full CI finish.

The v191 checker uses the same ten actual native PCSX ReARMed/Unai process logs, and confirms that every GPU 595-pixel pass (VH78_PHASE_PASS phase=N checked=595 guard=499) was produced after the genuine VBlank observation for that phase and before the next independent guest RAM snapshot. It must not have additional, missing, repeated, shifted, malformed, or hidden pixel phase success records.

For clean mode 0 the expected sequence is V0/P0, S1/V1/P1, S2/V2/P2, S3/V3/P3, then one authentic VH78_VBLANK_VRAM_PASS vblanks=4 phases=4 samples=2380 marker after all four pixel checkpoints. For modes 1–3 execution stops at the first corrupted pre-execution RAM snapshot (one previous pixel phase pass); for modes 4–6 there are exactly two previous pixel passes; for modes 7–9 exactly three previous pixel passes. No negative mode may claim the final four-phase 2380-pixel VRAM success marker.

Across the ten independent runs the checker therefore requires 22 chronologically valid pixel checkpoint receipts and 21 RAM snapshots, in addition to all 159 distinct adversarial modifications already proven by v189 and the SHA-256/inode evidence stability carried forward from v190. Original native log bytes, SHA-256 fingerprints and file identities are checked before and after v191's read-only phase analysis.

Required pass marker:

VH191_NATIVE_PHASE_MARKER_CHAIN_PASS modes=10 native_phase_passes=22 ram_snapshots=21 fault_modes=9 false_final_vram=0 original_retail=0

Independent GCC/Clang fixture tests inject missing/duplicated/out-of-order/incorrect pixel checkpoints, hidden prefixes, fake negative final success and absent final positive success.

Scope: only privately produced synthetic guest PS1 machine code, not an actual retail Vandal Hearts MAP02 scene, not physical Nintendo Switch output. Original retail ROM bytes and private native logs must not enter the public repository.
