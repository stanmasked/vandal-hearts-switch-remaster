# MAP02 v189 — replay adversarial mutations against actual PCSX/Unai native logs

## Scope

[MAP02 v188](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/219) is fully green (82/82 workflows). Both native pinned GCC and Clang PCSX/Unai jobs emitted the exact 10-mode, 21-snapshot v188 receipt-sequence pass. v188 asserts VBlank and snapshot order and verifies valid positive/refusal contents, but deliberately ignores their relative position to the event timeline. In particular, a REFUSED marker moved before the bad numeric RAM snapshot, or reordered positive success markers, might pass v188's presence checks.

This patch keeps native emulation, original guest EXE and all prior checks untouched. It adds a **read-only adversarial replay** step that reads the same ten genuine PCSX native run logs from private CI directories **after** v188 validates them. Their contents are copied in memory only; no on-disk log mutation, asset export, emulator source patch or private data disclosure.

For each native log it generates 12 universal mutations covering removed/duplicated VBlank or RAM entries, inconsistent event and frame numbers, zero waiting loops, corrupted RAM word or VBlank ordinal, reversed snapshot/VBlank order and malformed records. Clean mode 0 has three extra mutations (missing, duplicated or reordered positive pass markers); each of nine negative modes receives four extra mutations (missing/incorrect refusal field, forbidden positive marker or refusal placed *ahead of the very faulty RAM snapshot*).

Total = 12*10 + 3 + 4*9 = **159 independent hostile transcript mutations**. All must be rejected. The strengthened oracle also checks the exact chronological order of VBlank, snapshot, RAM refusal, and staged success markers for the original ten logs. If any corrupted transcript passes, native CI fails. A separate synthetic fixture audit under both GCC and Clang verifies that each of the 159 mutations fails and explicitly reproduces the chronological weaknesses of v188.

Required native marker:

VH189_NATIVE_LOG_REPLAY_PASS modes=10 snapshots=21 mutations=159 chronology=1 rejected=159 original_retail=0

These are synthetic PS1 guest tests only. They are not evidence of a rendered retail Vandal Hearts MAP02 scene or physical Nintendo Switch output. Keep as Draft, main unchanged.
