# Switch audio feasibility probe results

## Scope

These checks investigate whether a generated test tone can be built and scheduled through candidate audio APIs. They do not implement the game's soundtrack and do not prove audible output on a Nintendo Switch.

## SDL2 audio probe

The SDL2 probe requests a 22,050 Hz, mono, signed 16-bit audio device and queues a generated square wave. It reports whether the device opens and whether the audio callback is observed.

- The NRO build target is `make sdl2-audio-probe`.
- The SDL2 feasibility workflow packages `sdl2-audio-switch-probe.nro`.
- NeXium run [38610398658](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38610398658) reached the runtime stage, but the host audio backend reported that ALSA's default PCM device was unavailable (`Unknown PCM default`).
- This is an inconclusive audio-output result for that CI environment. It is not evidence that audio fails on a Switch, nor does a successful NRO build prove audible sound.

The follow-up workflow change in commit [ff3e89b](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/ff3e89b35044585e716eaac130eb9aefbc44fa1d) distinguishes a missing host audio device from a genuine probe failure where possible. Follow-up run: [38610973016](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38610973016).

## OpenAL Soft probe

The OpenAL Soft generated-tone probe is separate from the SDL2 audio test. Recent attempts [38609239427](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38609239427), [38609257257](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38609257257), and [38609709753](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38609709753) failed while retrieving devkitPro package database files with HTTP 403 responses. The build/runtime stage was not reached, so these runs do not establish whether OpenAL Soft works on Switch.

## Current conclusion

- Graphics and input probes have passed their documented NeXium checks; see the [SDL2 feasibility workflow](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/sdl2-probe.yml).
- Audio library compilation, audio-device availability in a headless CI runner, audible playback in an emulator, and audible playback on physical Switch hardware are distinct questions.
- Audio remains unverified until a supported runtime produces evidence of audible output. The physical-console test remains outstanding.
