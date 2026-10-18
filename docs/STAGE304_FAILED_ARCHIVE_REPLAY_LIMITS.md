# Stage304 prior failed NeXium: archive vs original host-control source

Original Stage322 NeXium
[run 39157976877](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39157976877)
**failed** at pre-existing Stage304 buffered host PCM snapshot validation.
This by itself does not identify an audout/SPU, sound quality, DAC or
speaker problem.

## Exact progression of original-source postmortem

1. Initial [archive replay #39160065284](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39160065284)
   mistakenly assumed its downloaded artifact extracted directly to
   the root of the requested output directory. It reported every
   pinned source missing. **That was a layout/locator error**, not
   evidence that all 12 source files were lost or were absent during
   the original execution.
2. The corrected [replay #39162119688](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39162119688)
   searched the archive's nested paths, required exactly one safe
   regular file per pinned input, and found **all 12 inputs with
   no duplicates**. The independent strict Stage304 original-source
   check still rejected the archived evidence.
3. [Replay #39162820354](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39162820354)
   reported the exact archived source failure invariant:
   `VirtualPcmEvidenceError: nonmonotone exit-control snapshots`.
   This means at least one of two events occurred between archived
   adjacent Plus-control snapshots: PCM file length decreased, OR
   host epoch milliseconds did not strictly increase.
   The original run's actual live failure **is not established as
   this identical cause**, since the archived replay is a separate
   audit of stored files.
4. The new source classifier
   `tools/classify_nexium_stage304_exit_control_order.py`
   independently inspects ONLY the original small host-control CSV,
   reporting adjacent file-size **deltas** and host-millisecond
   **deltas**. It does not expose absolute host epoch values, dump
   audio, or alter the strict Stage304 acceptance criteria.
   Seven synthetic negative/positive cases are included; new
   archival CI is pending.

## Strict separation of evidence

The postmortem workflow
`.github/workflows/diagnose-stage304-original-archive.yml`
has no authority to turn the old **failed** run into success. It
requires original pinned source inventory before strict re-audit;
missing or ambiguous inputs never count as a valid source replay.
It saves only a compact diagnostic JSON classification, **never raw
PCM/music**, PS1 game data, keys or firmware.

Later original Stage322 NeXium
[run 39159226320](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39159226320)
did **pass** Stage304 as well as the original bounded 16-call software
history. Independent Stage323
[run 39159251998](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39159251998)
replayed its original guest CSV bytes and CRC optical source successfully.
Stage324 [NeXium run 39162251380](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39162251380)
and separate
[source replay 39162959331](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39162959331)
also succeeded, establishing a **second original, distinct** software
call-history cohort.

No changes were made to SPU synthesis, PCM buffer content, audout
scheduling, gameplay, or physical Switch audio claims in this source
postmortem.
