# Vandal Hearts Remake — Stage305: buffered Plus/PCM onset fence

## Confirmed starting evidence

The Stage304 NeXium smoke test (GitHub Actions run `39134382535`)
passed and source-verified a terminal digital-zero run of **282231**
stereo PCM frames at 48 kHz. In that capture, the original buffered
file-length snapshot before actual Plus keydown contained **0 frames**
of that terminal run. The snapshot after Plus keyup already contained
**10066 frames** of the same terminal run. At the end of the optical
exit sequence the observed terminal overlap reached 214771 frames.

These are source-file-position observations, *not* proofs of guest
input or audio callbacks occurring on sample boundaries. Association
with an exit command is not proof of a defective or audible drop-out.

## New independent audit

`tools/audit_nexium_pcm_plus_fence.py` reproducibly replays all original
source receipts from Stages 299 through 304, then independently scans
every exact-zero stereo PCM run from the *same original recording*.

It assigns an EOF-censored zero onset one of four statuses:

- `present_by_before_plus_snapshot`
- `between_buffered_plus_snapshots`
- `later_than_after_plus_snapshot`
- `ambiguous_partial_stereo_frame_boundary`

Unlike naive timestamp interpolation, classification uses bounds from
both floor and ceiling of host file-size snapshots divided by 4 bytes
per stereo frame. A partially written frame cannot prove an exact
guest event timestamp.

The audit independently recomputes zero and nonzero stereo frames in
three source intervals: the unambiguously complete frames between
Plus-down and Plus-up buffered snapshots; the 500 ms source sample
interval immediately before Plus-down; and the 500 ms source sample
interval after Plus-up. Every interval is frame-conserved.

It reports the difference between recorded PCM frame-count change
and the number suggested by host-wall time as an **observation**, not
a guest or audio sync failure. No threshold is imposed because
buffered file snapshots can lag audio callbacks.

The report is written to
`runtime-evidence/pcm-plus-onset-fence-stage305.json`.

Host suite:
`python3 -m unittest discover -s tests -p 'test_audit_nexium_pcm_plus_fence.py' -v`

## Boundaries

This is not a physical Nintendo Switch sound test, an original
soundtrack identification, a guest SPU callback trace, or proof of an
audible defect. It does not alter music synthesis, audout, or gameplay.
The Stage305 report must never classify *temporal overlap* as causal
audio shutdown.
