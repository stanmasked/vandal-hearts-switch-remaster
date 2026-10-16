# MAP02 v64 — ordered GP0 DMA2 / GP1 capture-event correlation

## Scope

v63 accepted a GP1(00)/GP1(01) *user-authored sidecar*. This is useful
for testing register resets but does not show which GP1 commands were
actually sent to the control port, nor their order relative to each GPU
DMA submission. v64 adds an explicit **capture-adapter journal contract**:
sequence-numbered, monotonically ordered records of (a) submitted DMA2
head addresses and exact ordered GP0 payload-word digests, and (b) writes
to the GP1 control port. It joins those records against a separately
saved raw PlayStation-format RAM image.

This is an OFFLINE **consistency validator**, not a USB/FPGA adapter,
emulator patch, network collector, retail-scene recording or hardware
attestation service. The project does **not** yet possess an independently
captured real GPU port log. The v64 CI journal is deliberately **synthetic**.

### Input and the event grammar

Use the v60 manifest `ps1-dma2-linked-list-ram-v1`, a local raw RAM
snapshot, and a separate `map02-v64-ordered-gpu-event-journal-v1` JSON
journal. Events have strictly increasing `seq` and `tick`,
`previous` SHA256 hash-chain and SHA256 `digest` over the canonical
JSON of all event fields other than `digest`. `tick` is a strictly
monotonic **logical producer counter**, not a verified hardware clock.

Two event kinds are allowed:

- `GP0_DMA2`: `frame`, `head`, `gp0_word_count`,
  `gp0_sha256` over the exact little-endian sequence of all GP0
  payload words produced by following the original RAM's DMA2 OT chain.
  The validator walks those linked nodes again, enforces the supplied
  manifest's entry-point order, and recomputes the SHA256 from actual
  RAM rather than trusting the journal.
- `GP1_WRITE`: `before_frame` and `word`. Only the precise
  GP1(00)=`0x00000000` full reset and GP1(01)=`0x01000000`
  command-FIFO-only reset are supported. A write must occur immediately
  before exactly one DMA2 frame. No omitted, duplicate, out-of-order,
  unrelated, extra-data or post-last-frame GP1 events are accepted.

For each validated journal, v64 derives a separate v63-format GP1
reset sidecar **internally from the ordered events** and reuses v63's
original state interpreter, so full-vs-FIFO reset semantics run at
exactly the matching DMA frame boundary. This avoids maintaining two
potentially contradictory files.

### Local command

Run on your own computer, without uploading proprietary resources:

```bash
python3 -m tools.audit_map02_v64_event_journal \
  --ram /private/gpu_dma_ram.bin \
  --manifest /private/gpu_dma_manifest.json \
  --journal /private/ordered_gpu_events.json \
  --output /private/v64_sanitized_report.json
```

When the package directory is called `remaster` in the current
working directory, use
`python3 -m remaster.tools.audit_map02_v64_event_journal`.

The validator uses bounded normal-file reads and a 64 KiB journal
limit. JSON duplicate fields are refused. No network access is used.
Reports include only aggregate counts and Boolean gates, not raw GPU
words, per-pixel values, capture paths, DMA heads, ticks or game art.
Outputs cannot overwrite an input or follow a symlink.

### What a journal digest does NOT establish

SHA256 is an **integrity check**, not a hardware-signature or proof of
a trustworthy event producer. An adversary with write access can
change a GP1(00) record to GP1(01) and recompute all event hashes.
v64 has a deliberate adversarial test demonstrating that such a
rewritten journal remains structurally consistent but that the
reported hardware-origin claim **STAYS FALSE**.

A future actual emulator debugger / external logic-analyzer integration
would need to record GP1 MMIO writes at the originating port, DMA2
head submission and relative event order, with independent capture
method evidence and explicit external resets/interrupts. Even then,
the observational evidence would require separate trusted provenance
verification. Do not call a synthetic, self-authored or locally
re-signed event log an independent original PlayStation capture.

### Synthetic gate

The v64 fixture is entirely synthetic. It joins 4 RAM-based DMA2
submissions (19 total linked-list nodes, 13 E1–E6 register updates)
with a six-record journal: four GP0_DMA2 and two GP1_WRITE events
(one GP1(00) ahead of frame 2 and one GP1(01) ahead of frame 3).

Both GCC and Clang workflow variants run v64 adversarial tests,
the local-only CLI and all previous v45–v63 actual original-C GPU,
PRS, OT, VHT1 replay, frame-pixel, GP0 decoder and privacy gates.
They also require an altered GP1 journal hash to be refused, and a
*re-signed* forged journal to remain unable to claim genuine hardware
provenance. They never read or upload user-owned retail bytes.

These gates remain permanently false for this milestone:

- `gp1_write_proven_to_originate_from_hardware=false`
- `independent_retail_capture_authenticity_proven=false`
- `retail_gp0_provenance_verified=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

No game content is published; no Switch gameplay or hardware-exact
rendering is claimed. v64 is a stacked draft PR on v63, with no
changes to the default `main` branch.
