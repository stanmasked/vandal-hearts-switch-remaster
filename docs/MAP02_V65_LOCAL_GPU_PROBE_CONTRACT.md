# Map02 v65 — local GPU observation hooks, not retail authentication

## Milestone

v64 introduced an ordered GP0 DMA2 / GP1 journal, but the six event
records in its tests were directly synthesized in Python. v65 adds a
**working C11 producer hook API** and an **independent offline consumer**
for the exact GPU stream observed at those hooks, compared against the
separately captured RAM slice and v60 DMA2 linked-list manifest.

Crucial distinction: this is the **interface to instrument an emulator**,
not an integration with a named emulator or actual retail capture. In CI
the C producer is invoked by a synthetic test driver that replays known
RAM. No authentic GP1 hardware writes or real MAP02 gameplay are claimed.

## What is provided

- `tools/map02_v65_gpu_probe.h`: minimal C11 producer methods
  `vh65_probe_begin(FILE *, source_class)`,
  `vh65_probe_gp1_write(FILE *, tick, before_frame, word)` and
  `vh65_probe_dma2_submit(FILE *, tick, frame, head, words, count)`.
  The caller must invoke these **at genuine GPU-port instrumentation
  points**. Calling them from a toy test program creates only a toy
  capture, not an observed emulator or hardware event.
- `tools/ingest_map02_v65_gpu_probe.py`: privacy-preserving consumer for
  newline-delimited JSON records. It checks the exact GPU FIFO words
  from the observation stream, not just a declared count or SHA, against
  a separate raw RAM image and ordering-table traversal. Source SHA
  integrity, GP1 sequence, strictly increasing producer ticks, DMA heads
  and frame order are verified before deriving a v64 journal in memory.
- `tests/map02_v65_synthetic_probe_driver.c`: **synthetic-only** C11
  smoke driver. It traverses a generated RAM image to exercise the hook
  ABI end-to-end. It is not a real emulator, DMA controller or GPU.

### Required events and timing

The first JSONL line is a header:

```json
{"kind":"CAPTURE_BEGIN","schema":"map02-v65-local-gpu-probe-jsonl-v1","source_class":"user-supplied-unverified","clock":"producer-monotonic-counter","initial_state":"power-on-assumed"}
```

One event is recorded when an instrumented DMA2 submission is sent to
the GPU:

```json
{"kind":"GP0_DMA2","tick":101,"frame":0,"head":4096,"words":[3858759683]}
```

The `words` example above is only illustrative, **not** a real
submittable DMA command sequence. An actual event must hold the
complete ordered 32-bit GPU FIFO stream for the DMA2-linked-list.
Frames must equal the separately supplied manifest's ordered
`entry_points`; partial, truncated or absent frames fail closed.

At the GPU control-port MMIO write hook:

```json
{"kind":"GP1_WRITE","tick":102,"before_frame":1,"word":0}
```

Only GP1(00) full reset and GP1(01) FIFO reset are understood.
For the v65 bounded validation profile, GP1 events must immediately
precede the subsequent DMA submission. Unknown, out-of-order or
interleaved GPU control operations **refuse closed**, rather than
silently declaring the recording to be equivalent to retail PlayStation
GPU behavior. A more general GP1 control trace requires new rigorously
specified parser handling.

The `tick` field is a monotonically increasing counter assigned at
the two hook sites by the **same capture producer**. It does not prove
real-time hardware timing or independence. Existing v64 digest-chain
checks are also not a provenance signature.

## Private local operation

On a machine with the project package in the working directory:

```bash
python3 -m tools.ingest_map02_v65_gpu_probe \
  --ram /private/dma2_capture_ram.bin \
  --manifest /private/dma2_capture_manifest.json \
  --probe /private/observed_gpu_mmio.jsonl \
  --output /private/gpu_safe_aggregate.json
```

If the project directory is named `remaster`, run
`python3 -m remaster.tools.ingest_map02_v65_gpu_probe`
from its parent directory.

The **probe log contains raw GPU words** and may disclose game assets
or other proprietary details. It must stay local, private and **never
be uploaded as a GitHub Actions test artifact**. Reports contain only
aggregate counters and safety gates, not GPU payloads, DMA addresses,
textured vertices, register words, file paths or game screenshots.

For an opt-in local v64-format journal containing GPU head addresses
and GP1 words, supply `--private-journal-out /private/event_log.json`.
This journal is sensitive and must not be treated as a public artifact.

Input limits: 4 MiB DMA RAM, 16 KiB manifest, 8 MiB JSONL log,
512 events, 65536 words per DMA submission, 1048576 words total.
Duplicate JSON keys, symlinks, special files, non-integer words,
unsupported GP1 values, altered GP0 pixel/geometry payloads, wrong
head address, duplicate frames, malformed ticks, missing terminal
newline and unauthorised provenance metadata are refused. Reports
never include input contents in error messages.

## Reproducible synthetic-only native integration test

The v65 CI builds the reusable C hook and test driver using
`gcc -std=c11 -Wall -Wextra -Werror -pedantic` and Clang equivalently.

It uses the existing *synthetic* v63 PS1 GPU RAM fixture:

- four DMA frames and their original-format linked-list RAM;
- two simulated GP1 writes, full reset before frame 2 and FIFO-only
  reset before frame 3;
- literal C hook output containing the actual words traversed by the
  synthetic driver;
- Python byte-for-byte comparison of all submitted GP0 words with
  the separately loaded RAM and v64 second-stage journal verification;
- adversarial corruption of one GP0 payload word (**must fail**) and
  substitution of GP1(00) with GP1(01) (**may pass structural checks,
  but must NEVER be declared a verified hardware-origin event**).

39 additional Python unit tests exercise malformed logs, private-output
rules and falsified provenance, in both compiler matrices. The full
original public PC-port GPU/PRS/VHT1 and earlier v45–v64 suites run
unchanged, and no original retail files are published.

## Remaining proof gates

A real emulator integration is a **future independent task**, requiring
appropriate per-emulator code hooks, source revision pinning and trusted
capture-method documentation. That would improve **observability**, not
automatically establish retail provenance or hardware-exact output.

The following flags remain deliberately closed:

- `producer_instrumentation_actually_installed=false`
- `independent_capture_provenance_verified=false`
- `gp1_write_proven_to_originate_from_hardware=false`
- `retail_gp0_provenance_verified=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

This is a stacked, unmerged draft PR based on v64, not a release.
Do not enable HD texture replacement or claim native Switch gameplay
until authentic privately held assets and independent hardware reference
tests are completed.
