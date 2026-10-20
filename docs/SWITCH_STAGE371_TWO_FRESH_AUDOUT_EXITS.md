# Stage371 — two new isolated NeXium guest audout exit observations

## New observation, not a recategorization of old evidence

The independently completed Stage369 replay [#39390450645](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39390450645)
verified a genuine **successful** original guest shutdown from NeXium
[#39388027581](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39388027581):
`audoutWaitPlayFinish Result=0`, reported release count `1`, pointer
matched submitted descriptor. The older genuine [#39325440778](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39325440778)
returned `0xEA01` but predates Stage368 and does **not** contain its
pointer/count snapshot. Those fields remain unknown.

Stage371 prepares **two new** independently observed guest sessions on
the **same newly compiled native NRO**, preserving original software
exit-tail receipts with no new audout service call or PCM modification.
The [dedicated CI workflow](../.github/workflows/stage371-two-fresh-guest-exits.yml)
builds the NRO once in the devkitA64 container and verifies a manifest
bound to that workflow's commit, run ID, attempt, size and SHA-256.

Both trials use independent, never-reused NeXium SD roots:

- trial a: `vh-nexium-stage266-RUN-a`, baseline dwell 6 seconds after
  the last observed music-scene screenshot;
- trial b: `vh-nexium-stage266-RUN-b`, dwell 12 seconds after the same
  screenshot.

Everything else in the original A/B transition and optical Plus+X
diagnostic sequence is unchanged. The existing
`tools/capture_nexium_scene_audio.sh` still defaults to its **old
guest directory and original six-second timing** when these optional
environment controls are absent. The tagged paths refuse an existing
guest root instead of reusing old captures.

## Independent original-source audit

`tools/audit_stage371_two_original_wait_trials.py` validates each
guest's *actual*, independently generated Stage351 reason, Stage357 raw
Result, Stage368 descriptor count and pointer identity using the
existing fail-closed Stage368 canonical CSV parser. It also requires
two distinct original root locators and a corresponding nonempty
1280×720 optical frame from each run (the pixels have not been decoded
as a semantic receipt, and do not establish speaker playback).
All three original CSV byte sequences and their SHA-256 digests are
preserved under separate `stage371-originals/a` and
`stage371-originals/b` directories. A failure preserves any partial
source files **as unverified evidence only**; no zero/empty queue,
returned descriptor count or success is fabricated.

If either new capture actually returns `0xEA01`, that will be a new
observation of a failed software wait with its real Stage368 tuple,
**not proof** that changing the dwell caused the result or that the
old failure had the same kernel event-wait callsite. This is a
repeatability probe, not a randomized causal study.

The isolated original guest tests (in
`tests/test_audit_stage371_two_original_wait_trials.py`) are entirely
synthetic negative controls; passing those tests alone cannot
establish an authentic runtime capture. A real CI run must upload the
source-bound result, and new Stage371 results must be separately
examined before claiming any newly observed exit.

**Safety bounds:** no user game/ROM assets are uploaded, raw PCM
samples are not included in the published Stage371 artifact, physical
Switch DAC/speaker sound is not tested, direct service queue depth at
exit is not read, and neither the 12-ms bounded tail wait nor the
release/lease policy is changed.
