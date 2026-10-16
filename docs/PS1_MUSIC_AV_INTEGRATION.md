# PS1 SEQ/VAB + native Switch graphics integration

This feature branch combines two previously separate, tested prototypes:
the libnx 1280x720 tactical-grid framebuffer and the native PS1-format
SEQ/VAB/SPU music pipeline. It is not yet the original playable game.

## Startup and content policy

The NRO attempts to load exactly three **user-owned** files from
`sdmc:/switch/vandal-hearts-remake/audio/`: `music.seq`, `music.vh`,
and `music.vb`. The complete file set is validated and decoded before
the sound worker starts. No copyrighted music is embedded in the binary
or GitHub. The files are neither uploaded nor modified.

The NRO checks whether libnx has already mounted `sdmc` and mounts it
itself only if necessary, without unmounting another subsystem's existing
mount. It unmounts its own mount after stopping the audio worker and releasing
all borrowed sample pointers. If the SD device cannot be mounted, it
**does not** treat inaccessible files as absent: audio is disabled and
the separate source indicator turns amber.

Only if SD access succeeds **and all three files are absent** does the NRO
use a generated SEQ/VAB/VAG fixture for asset-free CI. A partial or
malformed set fails closed, with red source and audio indicators;
it cannot silently substitute the fixture in place of owned data.

The main thread handles the gamepad, simple tactical demonstration and
framebuffer. A separate libnx thread generates 512 frames of 44.1kHz
SPU stereo PCM per music block, applies Gaussian interpolation and
the existing STUDIO_C reverb path, then resamples to 48kHz for `audout`.
Every call supplies at most 640 stereo output frames in a fully allocated
4KiB-aligned audio page. Music banks are released **after** the sound
thread is joined and the audio service is stopped.

## Display indicators and limitations

The upper-right green status means audout startup returned successfully
and no synchronous worker error has been recorded; red indicates failure
or device unavailability. Its separate source marker below it has
**four meanings**: green = user-owned SEQ/VH/VB accepted, gray =
mounted SD with no files (generated fixture), red = incomplete/invalid
file set, amber = SD could not be mounted. The screenshot validator
reports the actual observed marker and CI specifically requires the
gray synthetic source: inability to mount SD is not a passing audio
fixture test. No status indicator establishes that music is audible
or proves the original source files are authentic.

The animated blue heartbeat and tactical-grid marker support an
independent emulator screenshot check of ongoing framebuffer updates.
Audio timing, fidelity of VAB mappings, audible playback on physical
Switch hardware and integration with original Vandal Hearts gameplay
are not established by a successful synthetic CI run.

## Building and regression tests

From this feature branch, with devkitPro/libnx installed:

```sh
make test-audio-stream
make ps1-music-av-probe
```

The `native-ps1-music-av.yml` GitHub Actions workflow also runs a
UBSan-checked long-duration synthetic SEQ/SPU/reverb/resampler soak,
builds the NRO without SDL2/pacman downloads, and exercises the
framebuffer in NeXium. All CI tests use synthetic audio assets.
Full Switch functionality still requires local hardware validation.

## First NeXium run of the combined SEQ/VAB/SPU + framebuffer NRO

GitHub Actions [run #38865008839](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38865008839)
successfully compiled the new NRO and ran the SEQ/SPU/reverb/resampler
host regression and UBSan test. The separate NeXium runtime stage also
passed: the synthetic tactical grid and hero marker were observed;
**8,138 pixels changed** between the two frame samples, and
`audout_status` was `initialized`. The build artifact and raw NeXium
screenshots/log are retained in that CI run.

These results **do not** confirm audible music playback, correct
hardware sample timing, fidelity to the original game, or successful
loading of an actual user-owned `music.seq/music.vh/music.vb` set.
CI includes no proprietary audio files and exercises the synthetic
fixture only. A separate on-device recording is required for those claims.

## Synthetic guest-SD end-to-end cases

The integration workflow now uses a dedicated `NEXIUM_DATA_ROOT` for each
emulator run, matching NeXium's upstream `sdmc/` filesystem mapping.
The generator `tools/generate_ps1_music_sd_fixture.py` creates a tiny
**original-free** `pQES` sequence and `pBAV` bank in that isolated root.
Neither this generated sample nor any proprietary SEQ/VH/VB is committed
or included with the finished NRO artifact.

The three independent runtime cases are:

- `empty`: mounted SD with all three music files absent -> local
  built-in fixture chosen; green audout, gray source marker
- `full`: all three generated format-valid files -> SD file loader
  selected; green audout and green source marker (not original music)
- `partial`: only generated `music.seq` -> fail closed; red audout
  and red source marker, never silently substituted with fixture playback

Each case records two NeXium images, reports independently detected source
and audout status, and requires an animated framebuffer heartbeat.
The test asserts no observed content proves the identity of original
music or actual audible sound on a Nintendo Switch.
Host tests also ensure this CI fixture generator does not overwrite
existing audio files and rejects symlinked output directories.

## Additional guest audio processing progress gate

The runtime now shows a third independent rectangular status marker:

- Green: guest SEQ/SPU/resampler generated at least **16 stereo PCM blocks**
  and at least **16 calls to `audoutPlayBuffer` have returned**.
- Amber: audout started but there is not yet evidence of 16 completed
  PCM and audout-return iterations; a stalled audio output may remain here.
- Red: audio pipeline was not started or recorded an error.

Counts are atomic and updated by the audio worker, separate from the
main-thread framebuffer. The NeXium CI checks this third status for
all three synthetic SD variants, preventing an initialized-but-stalled
audio service from being counted as healthy playback. A green marker
proves **software audio buffer processing**, not audible audio through
speakers or parity with original PS1 timing.

## Transactional scene switching (host-tested, not wired into gameplay)

The native SEQ/SPU layer exposes
`vh_native_seq_switch_scene(&seq, next_seq, next_seq_size, &spu,
vh_native_vab_resolve, &next_bank, 0)`.

This routine validates the incoming SEQ before touching the current
sequencer or SPU. Invalid SEQ input leaves the current scene running,
with its existing PCM voice references and reverb intact. Successful
switching releases the old bank's voices, removes every old PCM pointer,
and retains the STUDIO_C delay/FIR history and configuration. The caller
owns the resampler, so its 44.1-to-48-kHz clock is not reset. A mismatched
SPU instance is rejected.

**Lifetime and thread requirements:** Load and validate the *next* VH/VB
bank and its decoded PCM storage before switching; retain its storage
until its voices have finished or been cleared. Perform the SEQ switch
only when the native audout worker is paused/joined or otherwise
synchronized, never concurrently with the DSP render callback. Any
already-submitted audout page must be handled separately; the SEQ
function does not resend, drain, or replay those pages.

The A/B/A/B synthetic bank regression exercises the successful and
invalid-SEQ paths, old-bank pointer removal, different-SPU rejection,
wet-tail preservation and uninterrupted resampling. All of these
are host-side tests. The combined NRO currently loads one bank and does
**not yet** invoke this transition API from the game's scene controller.

## Recovering failed native audout submissions

The standalone `audout-audio-probe` uses the portable
`vh_audio_output_submit_recover` transport helper. It renders and
resamples one stereo page **before** submitting it; a failed
`audoutPlayBuffer` cannot cause the helper to run SEQ/SPU or the
44.1-to-48-kHz resampler again. Recovery stops and recreates the
native audio service, then attempts to send exactly the same PCM page,
with a limit of two service restarts. A permanent error stops the probe
with a nonzero result rather than advancing music blindly.

The host `tests/test_vh_audio_output_recovery.c` fault-injects rejected
pages, exhausted retries, stop/open/start failures and HOME-resume
handling. It asserts stable SEQ note counts, SPU frame counts and
resampler phase during retries, and verifies the retried PCM pointer
and sample bytes are unchanged. The test is included in
`make test-audio-stream` and the PCM diagnostics workflow.

**Scope and limitations:** The recovery helper is now wired into both
the standalone native audout probe and the combined graphics/audio
NeXium/NRO audio worker. The combined worker starts its service before
launching the music thread; its retries occur exclusively in that
thread; and the main thread waits for it to exit before final teardown
and unloading user-owned PCM banks. A recovered submit increments the
completed-buffer counter once, not once per failed attempt.

A failed device call may have produced an *ambiguous* amount of audible
output before the failure; restarting audout may therefore truncate
sound or produce a discontinuity. The host tests guarantee software
clock preservation, **not** glitch-free or exactly-once sound on
Nintendo Switch hardware. Real Switch audio capture remains necessary.

## Synthetic music-scene transitions in the combined NRO

With a complete SD music bank, the combined NRO leaves the user-owned
`music.seq/.vh/.vb` playing and does **not** cycle cues. With **no** music
files present on a mounted SD, the fixture-only audio worker alternates
two generated pQES songs every **64 successfully submitted 512-frame**
SPU blocks. The transition uses `vh_native_seq_switch_scene` on the
audio-owning thread; it validates the next SEQ, clears old voice PCM
references and preserves STUDIO_C reverb. The independent 44.1→48-kHz
resampler is not reset. Both fixture songs resolve into the same
generated VAB; neither contains original game music.

A fourth framebuffer indicator at x=1000, y=325 changes from amber to
green once **two** fixture scene transitions have each produced and
successfully returned their first PCM page from audout. It is neutral
gray for user-owned music and invalid/partial sources. The synthetic
guest-SD NeXium run checks this indicator in addition to previously
verified music-source identity, audio-buffer processing and animated
framebuffer. This establishes **software switching progress only**,
not correct audibility or the original game's music cue rules.

## EON wet/dry differential and resampling-phase investigation

The synthetic 16-scene A/B bank test `tests/test_vh_native_bank_switch.c`
uses a VAB tone with `VagAtr.mode` bit 2 **unset**. Thus, although
STUDIO_C remains enabled, it receives no voice send and cannot explain
the late increasing PCM seam in that specific test. Its baseline dry
max across 15 transitions is **1367 PCM16**.

A separate host regression, `tests/test_vh_native_bank_switch_reverb.c`,
sets `VagAtr.mode` bit 2 and runs matched **wet STUDIO_C** and
**fully dry** SEQ/SPU/resampler paths through the same 16 synthetic
scenes. On the recorded CI run, **280,621 stereo sample values**
differed between these outputs; the peak 48-kHz adjacent-sample
changes were **1269 PCM16 wet** versus **1367 dry**. Reverb can alter
individual seams in either direction, but a wet tail is **not needed**
to reproduce the rising dry 48-kHz seam values.

Tracing the source *before resampling* isolates the pattern:

| Source and output | A→B seams | B→A seams |
| --- | --- | --- |
| Dry SPU at 44,100 Hz | 194 (repeats) | 2429 (repeats) |
| Dry output at 48,000 Hz | 112, 125, 139, 152, 165, 179, 14, 27 | 365, 532, 699, 866, 1033, 1200, 1367 |
| EON wet output at 48,000 Hz | 109, 210, 187, 191, 205, 227, 104, 110 | 523, 585, 649, 792, 950, 1109, 1269 |

The identical alternating 44.1-kHz source discontinuities and
changing 48-kHz seam values correspond to a **changing fractional
resampler boundary position** (the test logs this position for each
scene). This explains the measured synthetic pattern without
requiring a random DSP discontinuity or lost PCM clock. It does
**not** prove that an audible click is absent, nor that the actual
PlayStation original makes the same transitions.

The differential regression asserts that the source-level A→B and
B→A magnitude bands remain separate, that wet seams stay within the
measured synthetic safety envelope, that the dry/wet outputs differ,
and that continuous resampler clocks are identical. ASan/UBSan and
repeated-execution comparisons run in PCM WAV diagnostics.

**Decision:** Do not add automatic crossfades or modify reverb merely
to suppress these diagnostic numbers. Future work needs a genuine
user-supplied SEQ/VH/VB comparison and capture on a physical Switch
before selecting a perceptual artifact fix.
