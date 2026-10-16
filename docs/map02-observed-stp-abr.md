# MAP02: observed PutPixel STP/ABR matrix

The optional `gpu-putpixel-ot.json` and private `putpixel-native-events.jsonl`
must pass the existing SHA-bound frame, DrawOTag ordinal, pixel continuity,
and per-primitive VRAM endpoint validations **before** any counters are emitted.

The verifier now reports `observed_semi_putpixel_by_accuracy_and_abr`
as a two-by-four matrix: outer index 0 is the ordinary PC raster path and
1 is the accurate path; inner index is ABR 0, 1, 2, or 3. Each cell counts
observed calls, same-color results, changed words, front/after equality,
and rising/falling output bit 15. Opaque writes are counted separately
by raster mode. An absent optional observer is reported as `null` by the
source DDA join, **not** as evidence of zero semitransparent writes.

These bins describe the exact event fields `before`, `front`, `after`,
`semi`, `accurate`, and `abr`. The observer's `semi` flag is a request
at PutPixel, not independent proof of CLUT texel STP or PS1 mask behavior.
A changed pixel word is not automatically attributed to BlendG1.
No unrecorded pixel, missing call, STP bit choice, or per-primitive DDA
coordinate can be reconstructed from these aggregates.

## Next verification

1. Instrument **original PC** `WritePixel` / `BlendG1` entry and exit
   using a private bounded trace and capture chosen ABR, accurate flag,
   and actual intermediate words. Preserve the existing frame and ordinal
   binding and fail closed on dropped or malformed events.
2. Compare those original-PC traces with this PutPixel matrix. Require
   direct observation at the same coordinate and primitive before claiming
   that a result came from `BlendG1`. Compare ordinary and accurate paths
   independently; do not silently pool them.
3. Check a real MAP02 frame separately from synthetic fixtures. Even a
   successful original-PC match would **not** prove PS1 hardware raster
   equivalence or authentic game capture.

Synthetic regressions live at `tests/test_map02_observed_blends.py`.
