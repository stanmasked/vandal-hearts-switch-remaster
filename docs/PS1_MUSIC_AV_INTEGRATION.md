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
