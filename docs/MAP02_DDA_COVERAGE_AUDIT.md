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
umask 077
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

Once a local *instrumented executable* exists, optionally fingerprint that
exact file before launch:

```sh
python3 -m tools.preflight_map02_private_dda_capture \
  --executable /absolute/path/to/your/instrumented-pcport \
  > "${HOME}/map02-private-preflight.json"
```

Replace the executable path with the actual locally built native PC-port
program. This additional read-only check records its byte length and SHA-256,
rejecting symlinks, non-executable or changed binaries. **A SHA-256 does not
prove which source files were compiled, that the instrumented callbacks
exist, or that retail game resources were loaded.** Keep the fingerprint
report private and recheck it against the executable actually launched.

Frame 411 and X/Y 30/30 are **illustrative only**, not measured MAP02
values. The preflight refuses missing/out-of-range/non-decimal selectors,
frame or output-directory disagreement, pre-existing files, symlinked
directories, unsafe POSIX permissions, and paths too long for the C
recorders' fixed file buffers. It does not create or modify the directory,
run the executable, prove the binary contains diagnostic hooks, or read
copyrighted game data. Output omits private path and sample X/Y.
The path-length check uses the actual environment string received by the C
recorder (not only the normalized directory path), preventing misleading
success for aliases with many path components.

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

### Optional synchronous capture launcher

Once you have built the **opt-in native PC-port executable** with
matching GPU capture, pixel-scope and both DDA observers, the following
local-only launcher performs a fresh preflight, launches the user-supplied
binary exactly once, then validates the captured private GPU/VRAM/DDA
journals when the process exits successfully:

```sh
python3 -m tools.run_map02_private_native_capture \
  --executable /absolute/path/to/your/instrumented-pcport \
  --preflight-report "${HOME}/map02-launch-preflight.json" \
  --summary-report "${HOME}/map02-launch-summary.json"
```

Use the **same exported environment variables** and an empty private
capture directory as in the previous section. The two receipt files must
not already exist and must be outside the capture directory. Both are
created with owner-only permissions and never overwritten. Any executable
arguments (including game resource selectors) may follow `--`; they
are passed directly to the process without a shell and are never saved
in the report. The launcher discards process stdout/stderr rather than
uploading or echoing copyrighted game data. It records launch status,
exit code, executable SHA-256 and verified journal hashes. On errors it
preserves private files for local diagnosis and returns nonzero.
If the local game may remain running, an optional `--timeout-seconds N` limit
will terminate the launched process and produce an unverified failure
receipt rather than misrepresenting a timed-out run as a complete capture.

The process **is actually spawned** by the launcher when preflight
succeeds. This narrows the origin gap compared with an offline hash-only
check, but still does not prove that a particular game scene was rendered,
which game resources were loaded, or physical PS1/Switch fidelity. The
native recorder must be fully linked in the local program: CI checks
compilation of the original PC GPU, not a retail-game run. Neither the
launcher nor its reports enable HD replacement.
### Replay a completed private process receipt

After a *completed, structurally validated* local launch, its private
summary JSON can be replay-checked against the current raw data without
starting the executable again:

```sh
python3 -m tools.verify_map02_private_capture_receipt "$capture_dir" \
  --receipt-file "${HOME}/map02-launch-summary.json" \
  --preflight-report "${HOME}/map02-launch-preflight.json" \
  --executable /absolute/path/to/your/instrumented-pcport \
  > "${HOME}/map02-replay-check.json"
```

The verifier requires the original process receipt to record an actually
started process, exit code zero and a successful structural capture. It
rechecks the same executable fingerprint, private native DDA journals,
original PC GPU event log and **every 1-MiB VRAM before/after snapshot**.
If any hash, event count, observation class or derived report has changed
since the saved process receipt, replay fails. It also rejects a modified
or malformed success receipt. This is a comparison to an **unsigned**
local report: a coordinated rewrite of both report and data is not
detectable, nor does it establish original MAP02 scene authenticity.

### Verify the captured session against the preflight binary

After a locally instrumented game has produced a private capture, compare
the preflight file to the **same** executable path and validate the recorded
GPU snapshots/DDA journal identities together:

```sh
python3 -m tools.verify_map02_private_capture_session "$capture_dir" \
  --frame 411 \
  --preflight-report "${HOME}/map02-private-preflight.json" \
  --executable /absolute/path/to/your/instrumented-pcport \
  > "${HOME}/map02-private-session-check.json"
```

All values are examples and must be replaced with your actual local
configuration. The verification refuses preflight reports lacking a checked
executable SHA-256, a modified binary, inconsistent target frame, missing
VRAM evidence, contradictory DDA journal entries and incomplete capture
records. It returns hashes and aggregated checks only; no pixel arrays,
sample X/Y or private capture paths are included in the report. The
`vram_snapshot_sha256_list_sha256` field commits to the ordered SHA-256
fingerprints of **all validated native VRAM snapshots** (not just the GPU
JSONL journal). `native_gpu_pairs_verified` reports the number of
validated before/after operation pairs. The `dda_observation_mode` field
distinguishes `entered_only`, `rejected_only` and `both`, and
`all_dda_journal_classes_observed` remains false if one observer produced
no journal. Missing means **unobserved, not zero GPU events**. The hash
chain helps detect later file changes against the recorded report; it
still does not authenticate capture origin or establish GPU stream
completeness.

For native GPU `LoadImage` commands, the verifier now also fingerprints
each **actually saved post-upload binary payload**. It records
`upload_payload_sha256_list_sha256` over the ordered payload SHA-256
digests, plus `load_pairs_with_verified_payload` and
`load_pairs_without_payload`. The source-pinned C hook **must** write
a post-upload payload for positive `LoadImage` rectangles where **both**
width and height are at most 128; the validator now refuses a missing
payload for these bounded transfers. For dimensions outside that range
the recorder deliberately omits the upload even when the product
`width × height` is small (e.g. 129×1). Such an omitted payload is
**unobserved, not empty/verified**. An invented payload filename outside
those limits is rejected as well. More importantly, the verifier now
reconstructs the **exact source-pinned 16-bit LoadImage copy** against
the post-operation native VRAM snapshot for every observed bounded
upload (including negative-XY and edge clipping). It checks the entire
1-MiB post-VRAM snapshot, so an altered word *outside* the rectangle is
also rejected. `load_pairs_with_verified_vram_effect` counts operations
where both payload bytes and their clipped BGR555 result were verified.
This is stronger than matching two independent hashes; it still does
not authenticate game origin or prove that omitted large uploads had
a correct VRAM effect. A successful private receipt replay rejects an
equal-length modified upload even when its JSON and VRAM evidence stays
unchanged. Only hashes and counts, not game bytes or pixels, are reported.

The pinned PC-port `MoveImage` path is now independently replayed as
source-ordered **in-place** 16-bit VRAM writes. Every source and
destination pixel must fall within 1024×512 VRAM, with original nested
row/column iteration preserved. Forward copy intentionally propagates
values when source and destination overlap; interpreting `MoveImage`
as `memcpy` or `memmove` produces wrong evidence in these cases. The
validator checks the **entire** post-operation snapshot, including
unchanged pixels outside the destination. It reports
`move_pairs_with_verified_vram_effect` in the native GPU audit,
private capture report and receipt replay. Even negative and large
offscreen rectangles must have the exact original no-op effect.
This remains a source-pinned **PC GPU** verification, not a physical
PlayStation hardware GPU comparison.

The original `ClearImage` path uses `FillRectRaw` in the separately
pinned `pc_raster.c`. The new source-specific verifier reconstructs
its native **BGR555** fill as `((b>>3)<<10)|((g>>3)<<5)|(r>>3)`,
leaving bit 15 clear and applying neither polygon dithering,
semi-transparency, masking nor drawing-area clipping. It intersects
the supplied RECT with the full 1024×512 VRAM dimensions, preserving
every byte outside the rectangle. `clear_pairs_with_verified_vram_effect`
reports native `ClearImage` pairs for which the **entire** post-operation
1-MiB VRAM snapshot matches the expected overwrite. Test cases cover
truncated 8-bit channels, RGB values within and across 5-bit buckets,
negative XY and bottom-right clipping, zero/negative dimensions,
offscreen no-ops and false changes outside the filled region. The
original hardware PS1 ClearImage behavior is **not** inferred from
this source-pinned PC-port check.

**Important:** Hash agreement identifies the bytes inspected before and
after the run, but cannot prove that those bytes were actually executed,
that diagnostic callbacks were linked, or that retail MAP02 was rendered.
The tool never runs the game or enables HD replacement.
### Adjacent native DrawOTag primitive continuity

The source-pinned `DrawOTag` walker dispatches primitive packets
sequentially in one native render pass. The opt-in C recorder samples
full VRAM and GPU texture-window/draw-mode globals both **immediately
before** and **immediately after** each visited packet. The strict
validator now requires the *post* snapshot of each recorded target-frame
primitive to equal the *pre* snapshot of its **next** recorded native
primitive, byte for byte, and requires the same texture-window/draw-mode
state across that boundary.

The fields `draw_boundary_vram_checks` and
`draw_boundary_gpu_state_checks` report the number of such validated
adjacent boundaries, not a claim of complete scene capture. Inside a
primitive pair only the original `DR_MODE` packet (source primitive type
`5`) may change the recorded mode/window globals; normal FT4, SPRT,
TILE and other packets must leave them unchanged.

**Critical exception:** this cross-event continuity is deliberately
**not** required between a preceding-frame `LoadImage`/`MoveImage`/
`ClearImage` and the first target-frame draw. An unrecorded previous
`DrawOTag` may legitimately have modified VRAM in between. Nor does
the continuity rule prove that every retail packet was captured:
the native recorder still has a strict 64-event cap and the private
capture remains unauthenticated until a real MAP02 gameplay run.

Native `DrawOTag` event metadata also follows the pinned
`platform/pc/include/PsyQ/libgpu.h` and generated original C hook.
The `POLY_FT4` primitive type is exactly `2`: each logged
before/after draw event with that type **must include** the actual
`ft4` tpage/CLUT/XY/UV packet, while other native primitive types
must not claim `ft4` payloads. Load/Move/ClearImage transfer
events must have primitive type `0`. Missing or fabricated packet
metadata is rejected, not interpreted as absent geometry. This
validates captured packet structure, **not** the correctness or origin
of retail MAP02 vertices or textured pixels.

### Source-keyed FT4 temporal word-change accounting

`tools/verify_map02_native_overdraw.py` revalidates the private
source-to-native FT4 join, OT ordering, and full before/after native
VRAM snapshots before counting any source-keyed FT4 changes. Each
**observed changed 16-bit BGR555 word** is classified exactly once as:

- `source_ft4_bit15_only_word_changes`: only bit 15 differs;
- `source_ft4_color_only_word_changes`: only the lower 15 bits differ;
- `source_ft4_color_and_bit15_word_changes`: both differ.

These three event-level counts sum to
`changed_vram_words_on_source_ft4_draws`. A word changed twice by
two different source-keyed FT4s contributes **two event-level changes**
but only **one distinct touched VRAM word**.

For each touched word, the checker privately retains the value
immediately before its **first** source-keyed FT4 change and the value
immediately after its **last** source-keyed FT4 change. It publishes
only aggregate counts:
`source_ft4_first_pre_equals_last_post_words`,
`source_ft4_first_pre_differs_last_post_words`, and
`source_ft4_repeatedly_changed_first_pre_equals_last_post_words`.
This detects cases where two observed changes cancel at these
endpoints, even though a first-vs-last-snapshot-only comparison would
miss both changes. It never publishes raw coordinates or color words.

These endpoints do **not** establish a complete frame history.
Unmatched DrawOTag primitives may also modify those words between
the selected FT4 events; identical endpoints do not exclude unseen
write-and-restore operations. Likewise, bit-15 changes are not proof
of a physical PS1 mask/STP decision, and screen-space FT4 bounding
boxes are only proxies, not precise raster coverage.

The pinned native PC `DR_MODE` dispatch only updates persistent
texture-window/draw-mode state. Unlike FT4 pixel draws, it cannot
change native VRAM; the strict verifier now rejects any `DR_MODE`
before/after VRAM change, including a forged change propagated
consistently to the next FT4 snapshot. These gates validate supplied
original-PC-format evidence, **not** authentic MAP02 gameplay,
PlayStation hardware equivalence or the Switch HD replacement.

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
