# Vandal Hearts Remake — Stage316: repeat last audout PCM return across two independent guest runs

## Verified starting evidence

- The experimental **Stage313 NeXium** run [39144389184](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39144389184)
  captured the last successfully returned original audout PCM
  buffer at **23.212605 milliseconds** after in-game observed Plus.
  It occurred **after** the guest requested audio stop, but **before**
  the worker entered cleanup. The separate bounded exit taper returned.
  That original run retained its capture-time Stage313 source-validated
  JSON and optical frame, but did **not** preserve original guest
  audout page CSV bytes.
- The subsequent **Stage314 NeXium** run [39145082758](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39145082758)
  captured the last original audout PCM buffer at **18.693125 ms**
  after in-game observed Plus, also after stop request and before
  worker cleanup. Its bounded taper buffer also returned.
  Stage314 preserved **both original guest-created CSV files** and
  their source SHA-256 receipts.
- A completely separate **Stage315** workflow [39145673203](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39145673203)
  independently reread the original Stage314 guest exit and audout
  last-page CSV source bytes, recomputed both source SHA-256 values,
  independently checked the original CRC-protected optical PNG, and
  exactly reproduced the Stage307/308/310/313/314 source receipts.
  All fourteen source attack unit tests passed.

## Stage316 independent comparison

The standalone workflow
`.github/workflows/stage316-two-last-audout-release-runs.yml`
fetches the original NeXium runtime artifacts for Stage313 and
Stage314 **by explicit workflow run IDs**, plus the original Stage315
independent source-byte replay witness. A newly checked-out decoder
independently verifies both guest optical CRC scene packets and their
guest observed Plus/exit chronology.

`tools/compare_nexium_guest_last_page_two_runs.py` requires each
capture to have a distinct workflow ID, original optical PNG SHA-256,
guest exit source SHA-256 and last-page source SHA-256. It reconstructs
the guest software class of the last original PCM buffer return
relative to Plus, stop request and worker cleanup, including the
already-existing bounded exit taper. It explicitly refuses to claim
that the **older** Stage313 original guest audout CSV bytes were
re-audited: they were not archived.

The **newer** Stage314 capture must pass independent Stage315 replay
of its *actual original guest-created CSV bytes* and original optical
CRC packet; the published independent Stage315 receipt must exactly
match the newly calculated result. This prevents a derived JSON
report from standing in for a missing original file.

The output contains both original guest software timestamps and
their minimum, maximum and range, with distinct provenance tiers.
No single run is required to match another run's measured interval
exactly; variation is recorded as evidence, not hidden or called
a failure by itself.

Output:
`independent-stage316-evidence/two-original-last-audout-pages-stage316.json`.

Thirteen adversarial unit tests run in both Host SPU and the
standalone original-capture comparison workflow.

## Interpretation and limits

A buffer return means that `audout` released its buffer lease back to
the guest software owner. This is **not** an actual last audible PCM
sample, virtual sink playback timestamp, hardware DAC endpoint, or
proof that the button caused a sound defect. These guest timestamps
are not calibrated against the host's buffered PCM-file snapshots,
so a guest software interval cannot be interpreted as measured
last audible sound. Neither SPU synthesis, NRO gameplay logic,
music assets, audout buffer scheduling nor stop behavior is modified.
