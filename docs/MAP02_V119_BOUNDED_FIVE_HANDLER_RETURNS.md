# MAP02 v119 — bounded five-handler exact sampled-value returns

Stacked after [v118 Draft PR #109](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/109).

## Why this step exists

v118 compares exact post-handler samples at 24 fixed 16-bit Unai VRAM
locations over up to four consecutive observed GPU callbacks. The
original v82 canonical private JSONL holds event metadata and sampled
change *counts* only, so no offline reconstruction of pixel equality
is possible.

v119 extends the native-only observer to five consecutive handlers
(A, B, C, D, E) with an **absolute bounded lookback** of exactly four
previous 24-point arrays. E is assigned to precisely one category in
order of recency:

- E == D (unchanged since the previous observation);
- E != D and E == C (return to two back);
- E != D,C and E == B (return to three back);
- E != D,C,B and E == A (return to four back);
- E differs from all four previous selected-value arrays.

The label 0–4 represents actual recorded **VBlank callbacks between
A and E**, never CPU/GPU timing, hardware scanout or frame state.
Every consecutive five-handler window belongs to exactly one
exclusive class. Its required population is
`max(0, observed_Unai_handlers - 4)`; sliding windows legitimately
overlap.

The process holds at most four old arrays of 24 values each (192 bytes
of old sampled pixel values). Transient current sample values are
wiped after recording, and all four prior arrays are securely
cleared by the existing native reset. The observer exports only
integer category counts. No GPU opcode, raw pixel, pixel hash,
VRAM address, screenshot, private JSONL or game assets are made public.

The old v115–v118 C APIs and the private JSONL schema remain unchanged.
The new native getter reconciles all 25 counters to the number of
recorded handlers and refuses malformed state, counter overflow,
excess VBlank callbacks and unsupported input. An independent private
log verifier checks the exact per-gap populations against the original,
strictly verified Unai/VBlank append sequence, first revalidating
the v118 native four-handler report.

GCC and Clang regressions cover A–B–C–D–A, returns to each
intermediate state, recency precedence, no return, overlapping
five-handler windows, gaps with 0–4 VBlank callbacks, refusal of
a fifth callback, abnormal sample inputs, legacy ABI and erasure
of all old sample arrays. The full pinned PCSX synthetic renderer
workflow independently rechecks the private runtime log and emits only
`proof/public/v119-quintuplet-summary.json`.

## Limits

This is an equality witness for 24 selected post-handler VRAM values
in a **synthetic pinned emulator** only. It is not proof of whole-VRAM
stability, physical PS1 scanout, GPU completion timing, original retail
MAP02, or Nintendo Switch HD renderer equivalence.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

The stacked Draft PR does not alter `main`.
