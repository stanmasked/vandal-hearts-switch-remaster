# Vandal Hearts Remake — Stage308: shared guest software clock correlation

Stage306 revalidated three separate NeXium virtual PCM captures and
found a repeatable long terminal zero-run onset between host-buffered
Plus keydown/keyup file-size snapshots. It did **not** establish exact
guest timing or that Plus caused an audible dropout.

Stage307 introduced a new optional guest-monotonic exit timeline with
software milestones for observed Plus, stop request, audio-worker
cleanup, audout close and join. If NeXium's guest SD mirror is absent,
its auditor explicitly reports `NOT_OBSERVED_GUEST_SD_TRANSPORT`.

## Independent source comparison

Stage308 independently re-decodes the **original NeXium optical
screenshot**, including packet CRC32, guest event ordering, dropped
event count and four complete musical scene transitions. The same
in-game optical event producer uses `armGetSystemTick()` converted to
nanoseconds as the Stage307 guest exit milestones.

`tools/audit_nexium_guest_optical_exit_clock.py` re-audits both
sources and provides three non-interchangeable outcomes:

- `GUEST_OPTICAL_SCENES_PRECEDE_VERIFIED_GUEST_EXIT`: both original
  guest sources were observed, and every CRC-verified guest music-scene
  event occurred before the recorded guest-observed Plus event. The
  guest-software interval is reported in nanoseconds.
- `OPTICAL_SCENES_CONFIRMED_EXIT_GUEST_INCOMPLETE`: the optical
  source passed, but the actual guest SD exit CSV has missing events.
  No complete exit timing is claimed.
- `OPTICAL_SCENES_CONFIRMED_EXIT_SD_NOT_OBSERVED`: the optical
  source passed, but NeXium did not expose an authentic guest exit CSV.
  No guest exit timestamps or interval are fabricated.

Out-of-order complete guest events, missing optical CRC evidence, or
conflicting guest timing claims **fail closed**.

## Output and tests

Report: `runtime-evidence/guest-optical-exit-clock-stage308.json`.

Tests: `python3 -m unittest discover -s tests -p 'test_audit_nexium_guest_optical_exit_clock.py' -v`.

The host regression suite and full NeXium runtime smoke test integrate
this audit. Synthetic optical frames used by unit tests are test data
only, never runtime substitutes for real framebuffer pixels.

## Essential limits

A difference between two guest software timestamps is **not** a
guest-to-host clock calibration. The virtual PulseAudio monitor,
guest-input event, audout buffer return, actual DAC output and
physical sound remain separate sources. This correlation does not
prove original PS1 soundtrack equivalence, audible music, dropout,
or that the Plus handler caused a failure.

No change is made to the SPU synthesizer, music assets, gameplay
transition logic, output queue or shutdown ordering.
