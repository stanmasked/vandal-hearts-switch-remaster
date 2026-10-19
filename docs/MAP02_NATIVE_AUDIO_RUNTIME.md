# MAP02 + native music worker: first combined Switch NRO

**Scope:** an experimental opt-in Switch build that combines the existing
`main` MAP02 software-rendered tactical framebuffer with the staged native
SEQ → 20-voice SPU → STUDIO_C reverb → libnx `audout` worker.

The source base is Draft PR #194 (`cf952050`). This follow-up does **not**
modify the default `Makefile`, original PS1 resources, MAP02 renderer or
graphics algorithms.

## Build

```sh
make -f Makefile -f Makefile.map02-audio map02-audio-nro
```

Output: `build/map02-audio/vandal-hearts-map02-audio.nro`. This NRO defines
`VH_MAP02_AUDIO_EXPERIMENT=1` and defaults to `VH_GAME_AUDIO_WET_TAIL=0`,
so the legacy inter-cue reverb reset behavior remains the default. To
investigate the opt-in STUDIO_C tail, use a **different** build directory:

```sh
make -f Makefile -f Makefile.map02-audio \
  MAP02_AUDIO_BUILD=build/map02-audio-wet \
  MAP02_AUDIO_WET_TAIL=1 map02-audio-nro
```

Normal `make verify-nro` still builds the original graphics-only
`build/vandal-hearts-prototype.nro`. Nothing in this experimental target
replaces its filename or dependencies.

## Gameplay and audio lifecycle

- The original `source/main.c` remains the source of all tactical state,
  input behavior and MAP02 visual rendering.
- A single preprocessor-controlled block starts the already-tested audout
  worker after framebuffer setup. Audio startup failure is nonfatal: MAP02
  still displays and responds to input, even without a music device.
- Only real gameplay state changes (A select, B cancel, A commit movement)
  may send a new desired music scene to the worker; cursor movement without
  a mode change cannot trigger redundant posts. The gameplay thread never
  renders PCM or waits on `audoutPlayBuffer`.
- HOME/resume notifications feed the existing audio focus/recovery mailbox;
  a per-frame focus refresh handles missing suspend callbacks. On exit
  the hook is removed and the worker is joined **before** framebuffer close.
- The debug label `AUDIO ACTIVE` means the guest audio worker reports a
  running state, not confirmed speaker output or latency.
- All fallback cues in this project are generated. No copyrighted SEQ/VAB
  sound banks are added to GitHub. The player may supply their own local SD
  audio bank privately; that is outside the scope of this build.

## Verification gates

`.github/workflows/map02-audio-runtime.yml` independently exercises:
1. The A/B, cancel, selection, movement and exit-to-scene state contract
   with a new synthetic host C regression.
2. Both GCC and Clang ASan/UBSan for the input/audio and pre-existing audio
   host test suites, plus unchanged MAP02 graphics tests.
3. Separate original and audio-enabled NRO builds on devkitA64, NRO header
   validation, nonempty audio binary and distinct output bytes.
4. The resulting build artifacts are retained for **actual** NeXium checks.
   The dedicated `.github/workflows/map02-audio-nexium.yml` reuses the
   existing working MAP02 screenshot/input smoke test against the combined
   NRO, verifies the recorded same-run SHA256, and requires an on-screen
   blue `AUDIO ACTIVE` marker emitted when the guest audout worker reports
   its playing state. This optical marker is NOT a virtual PCM measurement.

A successful build is not a successful emulator run, a sample-aligned
A/B experiment, or a physical hardware-audio result. The optical NeXium gate
can establish co-execution of MAP02 graphics/input with a *running guest
audio worker*, but it cannot establish sound generation or audibility.
Actual PulseAudio monitor PCM capture and physical speaker testing remain
separate evidence gates; they must not be inferred from the blue marker.

**Draft only / DO NOT MERGE** until the NRO CI and emulator evidence are
reviewed. Parent Draft PRs #171, #177, #187 and #194 are unchanged.
