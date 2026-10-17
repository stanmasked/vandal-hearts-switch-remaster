# MAP02 independent DDA interval audit

The pure offline function `tools.map02_dda_coverage.classify` is a
**synthetic arithmetic validator**, not a producer of GPU evidence.

It uses the DDA half-open X span `[x_start, x_bound)`, an inclusive
drawing-area clip, and an explicit selected pixel. It distinguishes
unclipped X coverage, clipped coverage and vertical row rejection.

**Critical precondition:** Caller must separately establish that the X
endpoints were actually observed from the same original DDA primitive,
at this row and frame. The existing PR #52 reason codes 4–7 do not
supply such endpoints. Therefore no reason 4–7 event is automatically
upgraded to confirmed triangle coverage, no source data is modified,
and there are no new event reason codes.

Run: `python3 -m unittest discover -s tests -p test_map02_dda_coverage.py -v`.

No original MAP02 capture, physical PS1 GPU mask/STP/ABR parity, or
Nintendo Switch gameplay is verified by these arithmetic tests.
HD replacement remains disabled pending separately validated evidence.

## Strict synthetic row/event join

`tools.map02_dda_span_join.reconcile` joins an independently supplied
row span to each reason 4–7 event via exact `(frame, primitive_ordinal, y)`.
It rejects duplicate spans, duplicate rejection events, mismatched Y
clip-direction predicates, noncontiguous steps, wrong-frame joins,
invalid types and the full 64-event (possibly truncated) cap.
It does **not** claim genuine DDA span provenance: an independent
executed-`dda_part` span recorder remains to be developed and validated.

Run: `python3 -m unittest discover -s tests -p 'test_map02_dda_span_join.py' -v`.
The 11 new regression tests use fabricated data; no retail or Switch
playback has been established.

## Optional actual entered-span observation (experimental)

`tools.instrument_map02_dda_span.instrument_span` composes on top of the
source-pinned native raster-skip observer. At an *executed* `dda_span`
entry only, it records the actual arguments `x_start/x_bound` and
drawing-area clip bounds into a bounded private JSONL journal when
`VH_MAP02_DDA_SPAN_TRACE` and all four dependent flags are enabled.

This source transformation is now included in the **source-pinned
original PC GPU compile/link CI**, including baseline instruction/relocation
comparison and GCC/Clang opt-in checks. See [successful upstream run
39025294123](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39025294123).
That establishes that the instrumented original source **compiles and partially
links**, not that it ran with retail MAP02 resources or that the Nintendo
Switch display was verified. The original GPU sources remain untouched.

The recorder never logs rows rejected *before* `dda_span`. A second,
opt-in native observer creates `dda-rejected-edge-candidates.jsonl` for
those branches, but its X bounds are only **candidate edge snapshots**,
not executed spans. They must never be supplied as if they were original
executed spans to `map02_dda_span_join.reconcile`.

## Preflight a fresh private capture

Before launching the locally compiled **opt-in original PC GPU** with
your own lawfully obtained game resources, prepare a new private output
directory using `mktemp -d` in your home folder. Do not reuse a
directory from any earlier run or publish native logs/VRAM snapshots.

For a single chosen DrawOTag frame and VRAM pixel, configure the two
recorders to target the **same** directory and frame:

```sh
capture_dir="$(mktemp -d "${HOME}/map02-dda-XXXXXX")"
chmod 700 "$capture_dir"
export VH_MAP02_GPU_CAPTURE_DIR="$capture_dir"
export VH_MAP02_GPU_CAPTURE_FRAME=411
export VH_MAP02_PUTPIXEL_DIR="$capture_dir"
export VH_MAP02_PUTPIXEL_FRAME=411
export VH_MAP02_PUTPIXEL_X=30
export VH_MAP02_PUTPIXEL_Y=30
python3 -m tools.preflight_map02_private_dda_capture > "${HOME}/map02-private-preflight.json"
```

Frame 411 and X/Y 30/30 are **illustrative only**, not measured MAP02
values. The preflight refuses missing/out-of-range/non-decimal selectors,
frame or output-directory disagreement, pre-existing files, symlinked
directories, unsafe POSIX permissions, and paths too long for the C
recorders' fixed file buffers. It does not create or modify the directory,
run the executable, prove the binary contains diagnostic hooks, or read
copyrighted game data. Output omits private path and sample X/Y.
A successful preflight is **configuration readiness only**: to collect
both journals the locally built binary must also contain matching
opt-in native GPU, pixel-scope, DDA span and rejected-edge instrumentation.
Do not enable any HD replacement based on this result.
## Independent journal intake (no inferred coverage)

When an actual run produces one or both private journals, preserve the
raw bytes and execute from the remaster repository root:

```sh
python3 -m tools.audit_map02_independent_dda_journals /private/dda-capture \
  > /private/dda-journal-audit.json
```

For stronger **structural** cross-checking, use the same private directory
containing the native GPU capture (including full VRAM snapshot files):

```sh
python3 -m tools.audit_map02_independent_dda_journals /private/dda-capture \
  --native-frame 411 > /private/dda-gpu-cross-check.json
```

The strict frame option first calls the existing source-pinned native GPU
capture validator on its **actual before/after VRAM snapshots**. It then
requires that each supplied DDA record uses this DrawOTag frame, references
a draw-primitive ordinal present in the bounded GPU event stream, and (for
entered spans, which record a type) matches the native GPU packet type.
If the GPU recorder hits its 64-record cap, the strict cross-check refuses
to claim sufficient ordinal visibility. Neither mode proves capture
origin, an unmodified game binary, or visual MAP02 equivalence.

A **joint** audit now requires all records to belong to exactly one
(frame, privately configured sampled Y) envelope. It rejects mixed-run
journals, contradictory drawing-area clip windows for a primitive,
and a primitive/row claimed both as a vertically rejected candidate
and as an entered `dda_span`. These consistency checks are applied
even without `--native-frame` and do not disclose the selected Y in
the report. `single_sample_envelope_consistent=true` describes only
internal agreement, **not** authenticated common origin or an actual
retail MAP02 rendering. Capture each selected Y into its own empty
private directory; do not append observations from separate sessions.

The audit separately validates `dda-native-spans.jsonl` and
`dda-rejected-edge-candidates.jsonl`; rejects malformed CRLF records,
duplicate fields, noncanonical/saturated journals and symlinked inputs;
and records SHA-256, counts, shared frame identifiers and shared
primitive/row *keys*. A missing file is reported as **unobserved**, never
as evidence of zero raster events. A shared key likewise is not a proof
that the rejected row entered `dda_span` (it did not).

The audit unconditionally reports `journal_origin_authenticated=false`,
`retail_map02_frame_verified=false` and
`hd_replacement_authorized=false`. A successful audit only supports
structural checks on provided files. An independent capture origin and
actual original MAP02 frame comparison remain mandatory; the HD
replacement is still OFF.
