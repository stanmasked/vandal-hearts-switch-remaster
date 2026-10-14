# Switch audio feasibility probe results

## Scope

These checks investigate whether a generated test tone can be built and scheduled through candidate audio APIs. They do not implement the game's soundtrack and do not prove audible output on a Nintendo Switch.

## SDL2 audio probe

The SDL2 probe requests a 22,050 Hz, mono, signed 16-bit audio device and queues a generated square wave. It reports whether the device opens and whether the audio callback is observed.

- The NRO build target is `make sdl2-audio-probe`.
- The SDL2 feasibility workflow packages `sdl2-audio-switch-probe.nro`.
- NeXium run [38610398658](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38610398658) reached the runtime stage, but the host audio backend reported that ALSA's default PCM device was unavailable (`Unknown PCM default`).
- This is an inconclusive audio-output result for that CI environment. It is not evidence that audio fails on a Switch, nor does a successful NRO build prove audible sound.

The follow-up workflow change in commit [ff3e89b](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/ff3e89b35044585e716eaac130eb9aefbc44fa1d) was committed, but follow-up run [38610973016](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38610973016) did not reach the probe: its package-install step again received HTTP 403 for `dkp-linux.db` and `dkp-libs.db` after five attempts. Build and runtime steps were skipped, so this run neither validates nor invalidates the workflow's audio-result classification.

A second attempt changed pacman's external downloader to `curl` with a pacman-style User-Agent in commit [a3a55e2](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/a3a55e2b234739a3be3280fb6878ed7f496cd5f4). SDL2 workflow run [38611796465](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38611796465) still received HTTP 403 from the package database endpoint on all five attempts. The workaround is therefore **not effective in this CI environment**; compilation and runtime were skipped again. The main libnx prototype toolchain workflow independently passed at [38611751198](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38611751198).

## OpenAL Soft probe

The OpenAL Soft generated-tone probe is separate from the SDL2 audio test. Recent attempts [38609239427](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38609239427), [38609257257](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38609257257), and [38609709753](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38609709753) failed while retrieving devkitPro package database files with HTTP 403 responses. The build/runtime stage was not reached, so these runs do not establish whether OpenAL Soft works on Switch.

## Current conclusion

- Graphics and input probes have passed their documented NeXium checks; see the [SDL2 feasibility workflow](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/sdl2-probe.yml).
- Audio library compilation, audio-device availability in a headless CI runner, audible playback in an emulator, and audible playback on physical Switch hardware are distinct questions.
- Audio remains unverified until a supported runtime produces evidence of audible output. The physical-console test remains outstanding.

A later OpenAL runtime attempt, [run 38645987677](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38645987677), did reach NeXium and captured a 1280×720 status screenshot. The sampled pixels were white, matching status stage 13 in `probes/openal_smoke.c`: the guest had rendered the checkpoint immediately after `alSourcePlay()` returned. The workflow classified this as a failed run because it did not capture the later green success status. **This is not evidence that audio playback failed**: white only establishes that the screenshot saw the post-call checkpoint, while the intended green state would additionally require the subsequent OpenAL error check and guest cleanup path to advance. The run therefore remains inconclusive about OpenAL playback, and certainly does not verify audible output.

Next diagnostic step: make the runtime evidence distinguish the transient white checkpoint from a final status frame, and preserve the guest log/screenshot together. Do not treat the white checkpoint as either proof of audio success or proof of audio failure.

