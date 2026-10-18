# Vandal Hearts Remake — Stage317: when audio worker actually sees the stop flag

## Evidence motivating this measurement

Stage316 [Actions #39147896137](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39147896137)
independently compared two original NeXium captures. Both confirmed
the last successfully *returned* normal audout PCM page after the main
thread requested stop, but before the audio worker entered cleanup:

- Stage313 source run 39144389184: 23.212605 ms after in-game observed Plus
- Stage314 source run 39145082758: 18.693125 ms after in-game observed Plus

The later original guest CSV bytes were independently re-audited in
Stage315; the older capture has capture-time validated source JSON
and optical evidence only. Both bounded normal-exit taper page returns
were confirmed.

However, neither timestamp says precisely when the **audio worker
reads running == 0** in its mailbox. A page return after the main
thread's stop request is consistent with an already-blocked audout
call finishing; it is not by itself evidence the worker continued
rendering after it observed stop.

## Stage317 source instrumentation

The audio worker originally executed:

`while (vh_game_music_mailbox_running(&mailbox)) { ... }`

It now performs the **identical single atomic running() check once per
loop**, and only when that check returns false, stamps
`armTicksToNs(armGetSystemTick())` in a one-shot C11 atomic slot.

This does not add polling, a new queue message, a mutex, allocation,
filesystem write, sleep, audio buffer, sample rendering, or change
the meaning of the mailbox running flag. If the worker exits for a
separate error, the stop-observed slot remains zero rather than
claiming a cooperative stop was seen.

After the normal audio join the main thread exclusively writes a
**separate** guest-original
`sdmc:/switch/vandal-hearts-remake/audio-exit-worker-stop-000.csv`:

```csv
event,guest_monotonic_ns
worker_stop_observed,114000
```

The example timestamp is synthetic, not a runtime measurement.
The canonical Stage307 five-row original exit CSV and Stage313
five-row last returned buffer CSV remain unchanged. The new optional
export failure cannot affect the already completed application exit.

## Authentic source verification

`tools/audit_nexium_guest_worker_stop_observed.py` independently
re-reads the isolated original NeXium guest SD root, Stage307 guest
exit source and Stage313 last returned buffer source. It requires:

`stop_requested <= last_normal_buffer_return <= worker_stop_observed <= worker_cleanup_entered < audout_closed < worker_joined`

and verifies the last-page CSV SHA is bound to the exact exit source
SHA. A timestamp of zero explicitly means stop observation was not
recorded, not success. Missing guest SD is reported separately.

The tool preserves the **original guest-created worker-stop CSV
bytes** exclusively under
`runtime-evidence/audio-exit-worker-stop-000.csv`, re-reads the copy,
and emits
`runtime-evidence/guest-worker-stop-observed-stage317.json` with
a source SHA-256 and three guest software timing intervals.

The NeXium smoke job requires actual, source-proven, fully ordered
events rather than accepting missing data as a verified result.

## Tests

- Native C11 test of one-shot/zero/CSV semantics on GCC and Clang:
  `tests/test_vh_audio_exit_worker_stop_witness.c`.
- 11 independent Python source/ordering controls, including
  duplicated, altered, symlinked, missing, reversed, noncanonical
  original guest files:
  `tests/test_audit_nexium_guest_worker_stop_observed.py`.
- Host SPU and Switch toolchain regressions, Nintendo Switch NRO build
  and real NeXium runtime smoke.

## Strict scope

This event measures one **guest software loop boundary**. It is not
the physical keyboard event, a hardware audio cancellation, a PCM
buffer's last DAC sample, speaker output, proof of an audible
dropout, or proof of fidelity to the original PS1 soundtrack.
Guest monotonic nanoseconds remain uncalibrated against buffered host
PulseAudio PCM frame positions. No SPU, gameplay, queue ownership,
audout scheduling, music assets or shutdown control changed.
